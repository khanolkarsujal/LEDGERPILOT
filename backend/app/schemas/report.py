"""
Schemas for PDF report generation requests and review gate validation.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.schemas.ledger import LedgerPageExtraction, LedgerEntry, TransactionGroup


def get_effective_entry_description(entry: LedgerEntry) -> Optional[str]:
    """Returns human-corrected description if reviewed; otherwise raw recorded text."""
    if entry.review_status == "human_reviewed" and entry.corrected_marathi_text is not None:
        return entry.corrected_marathi_text
    return entry.raw_marathi_text


def get_effective_entry_amount(entry: LedgerEntry) -> Optional[Decimal]:
    """Returns human-corrected amount if reviewed; otherwise raw recorded amount."""
    if entry.review_status == "human_reviewed" and entry.corrected_amount is not None:
        return Decimal(str(entry.corrected_amount))
    if entry.amount is not None:
        try:
            return Decimal(str(entry.amount))
        except Exception:
            return None
    return None


def is_entry_unpriced_record(entry: LedgerEntry) -> bool:
    """Identifies entries where amount was not recorded on physical ledger."""
    if entry.review_status == "human_reviewed" and entry.corrected_amount is not None:
        return False
    if entry.review_status == "human_reviewed" and entry.corrected_amount is None:
        return True
    if entry.amount is None:
        return True
    s = str(entry.amount).strip().lower()
    if s in ("", "null", "none", "-", "—", "n/a", "not recorded"):
        return True
    if entry.flag_reason:
        r = entry.flag_reason.lower()
        if (
            any(
                kw in r
                for kw in (
                    "no amount",
                    "unpriced",
                    "not recorded",
                    "dash recorded",
                    "amount not explicitly written",
                )
            )
            and "amount" in (entry.uncertain_fields or [])
        ):
            return True
    return False


def calculate_group_effective_sum(group: TransactionGroup) -> Decimal:
    """Sums valid priced amounts in a section using effective values."""
    total = Decimal("0")
    for e in group.entries:
        if not is_entry_unpriced_record(e):
            amt = get_effective_entry_amount(e)
            if amt is not None:
                total += amt
    return total


class ReviewGateResult(BaseModel):
    """Result of the mandatory review gate check."""

    passed: bool
    unreviewed_count: int = 0
    pending_count: int = 0
    total_entries: int = 0
    reviewed_count: int = 0
    blocking_reasons: List[str] = Field(default_factory=list)


def check_review_gate(extraction: LedgerPageExtraction) -> ReviewGateResult:
    """
    Validates that EVERY remaining transaction has been explicitly reviewed and confirmed
    by a human before PDF generation is allowed.

    Blocks PDF generation if even ONE remaining transaction is:
    - Unreviewed (review_status != 'human_reviewed')
    - Pending confirmation / ambiguous
    - Missing a required unresolved value (e.g. empty description)
    """
    all_entries = [e for g in extraction.groups for e in g.entries]
    total = len(all_entries)

    if total == 0:
        return ReviewGateResult(
            passed=False,
            total_entries=0,
            blocking_reasons=["No transactions found. Cannot generate a statement with zero transactions."],
        )

    reviewed_count = 0
    unreviewed_count = 0
    pending_count = 0
    blocking_reasons: List[str] = []

    for g_idx, group in enumerate(extraction.groups):
        group_label = group.date_raw or f"Section {g_idx + 1}"
        for e_idx, entry in enumerate(group.entries):
            sr = entry.entry_index if entry.entry_index is not None else e_idx + 1

            # Check 1: Must be explicitly human reviewed
            if entry.review_status != "human_reviewed":
                unreviewed_count += 1
                blocking_reasons.append(
                    f"Entry #{sr} in '{group_label}' has not been confirmed by a human reviewer."
                )
                continue

            reviewed_count += 1

            # Check 2: Missing required description
            eff_desc = get_effective_entry_description(entry)
            if not eff_desc or not eff_desc.strip():
                blocking_reasons.append(
                    f"Entry #{sr} in '{group_label}' is missing a description. Please enter a description or delete this entry."
                )

    return ReviewGateResult(
        passed=len(blocking_reasons) == 0,
        unreviewed_count=unreviewed_count,
        pending_count=pending_count + unreviewed_count,
        total_entries=total,
        reviewed_count=reviewed_count,
        blocking_reasons=blocking_reasons,
    )


class DiscrepancyDetail(BaseModel):
    """Details of an arithmetic discrepancy between written and calculated totals."""

    section_index: int
    section_label: str
    written_subtotal: Decimal
    calculated_total: Decimal
    difference: Decimal


def check_arithmetic_discrepancies(extraction: LedgerPageExtraction) -> List[DiscrepancyDetail]:
    """
    Identifies any sections where the handwritten subtotal does not equal the calculated item sum.
    """
    discrepancies: List[DiscrepancyDetail] = []
    for g_idx, group in enumerate(extraction.groups):
        if group.recorded_group_total is not None:
            rec_str = str(group.recorded_group_total).strip().lower()
            if rec_str in ("", "null", "none", "-", "—"):
                continue
            try:
                rec_dec = Decimal(str(group.recorded_group_total))
                calc_dec = calculate_group_effective_sum(group)
                if rec_dec != calc_dec:
                    discrepancies.append(
                        DiscrepancyDetail(
                            section_index=g_idx + 1,
                            section_label=group.date_raw or f"Section {g_idx + 1}",
                            written_subtotal=rec_dec,
                            calculated_total=calc_dec,
                            difference=rec_dec - calc_dec,
                        )
                    )
            except Exception:
                continue
    return discrepancies


class PDFReportRequest(BaseModel):
    """Request payload for generating the Business Sales Statement PDF."""

    extraction: LedgerPageExtraction = Field(
        description="Structured extraction data from the current session, containing all groups and entries with human corrections."
    )
    business_name: Optional[str] = Field(
        default=None,
        description="Optional business trade name provided by the user. Omitted from PDF if empty.",
    )
    business_address: Optional[str] = Field(
        default=None,
        description="Optional business address. Omitted from PDF if empty.",
    )
    nature_of_business: Optional[str] = Field(
        default=None,
        description="Optional nature or trade category of business.",
    )
    statement_reference: Optional[str] = Field(
        default=None,
        description="Optional statement reference or identifier.",
    )
    acknowledge_discrepancies: bool = Field(
        default=False,
        description="Required to be True if handwritten subtotals differ from calculated totals.",
    )
