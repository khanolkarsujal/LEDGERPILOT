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


def is_high_confidence_entry(entry: LedgerEntry) -> bool:
    """
    Determines if an extracted transaction has sufficiently high confidence:
    - Non-empty description.
    - Valid positive numerical amount.
    - Zero uncertainty flags.
    - Zero flag reasons.
    High-confidence entries are automatically accepted and do NOT require human confirmation.
    """
    desc = get_effective_entry_description(entry)
    amt = get_effective_entry_amount(entry)

    has_valid_desc = bool(desc and desc.strip())
    has_valid_amt = amt is not None and amt > 0
    has_no_uncertainty = len(entry.uncertain_fields or []) == 0
    has_no_flag_reason = not bool(entry.flag_reason and entry.flag_reason.strip())

    return has_valid_desc and has_valid_amt and has_no_uncertainty and has_no_flag_reason


def requires_human_attention(entry: LedgerEntry) -> bool:
    """
    Returns True ONLY if an entry has genuine ambiguity, missing required values,
    or unresolved flags that have not been reviewed by a human.
    """
    # If already reviewed and confirmed by human:
    if entry.review_status == "human_reviewed":
        # Description must still be present
        eff_desc = get_effective_entry_description(entry)
        if not eff_desc or not eff_desc.strip():
            return True
        return False

    # For entries that haven't been reviewed by a human:
    # 1. Missing or unreadable description
    eff_desc = get_effective_entry_description(entry)
    if not eff_desc or not eff_desc.strip():
        return True

    # 2. Missing or unpriced amount (e.g. dash on notebook)
    if is_entry_unpriced_record(entry) or entry.amount is None:
        return True

    # 3. Explicit uncertainty flags or flag reason
    if (entry.uncertain_fields and len(entry.uncertain_fields) > 0) or (
        entry.flag_reason and entry.flag_reason.strip()
    ):
        return True

    # 4. Invalid or non-positive amount
    amt = get_effective_entry_amount(entry)
    if amt is None or amt <= 0:
        return True

    # Otherwise, it has clean description and positive amount with zero flags -> Auto-accepted!
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
    """Result of the review gate check."""

    passed: bool
    unresolved_count: int = 0
    total_entries: int = 0
    accepted_count: int = 0
    blocking_reasons: List[str] = Field(default_factory=list)


def check_review_gate(extraction: LedgerPageExtraction) -> ReviewGateResult:
    """
    Validates that all genuine uncertainties, missing values, or suspicious entries
    have been resolved before PDF generation is allowed.

    High-confidence entries are automatically accepted and do NOT block export.
    Blocks PDF generation if any remaining entry requires human attention:
    - Missing description.
    - Missing / unpriced amount not explicitly confirmed.
    - Ambiguous or flagged entries not reviewed.
    """
    all_entries = [e for g in extraction.groups for e in g.entries]
    total = len(all_entries)

    if total == 0:
        return ReviewGateResult(
            passed=False,
            total_entries=0,
            blocking_reasons=["No transactions found. Cannot generate a statement with zero transactions."],
        )

    unresolved_count = 0
    blocking_reasons: List[str] = []

    for g_idx, group in enumerate(extraction.groups):
        group_label = group.date_raw or f"Section {g_idx + 1}"
        for e_idx, entry in enumerate(group.entries):
            sr = entry.entry_index if entry.entry_index is not None else e_idx + 1

            if requires_human_attention(entry):
                unresolved_count += 1
                reason = (
                    entry.flag_reason
                    or ("Missing amount" if entry.amount is None else "Uncertain reading")
                )
                blocking_reasons.append(
                    f"Entry #{sr} in '{group_label}' requires review: {reason}. Please resolve, edit, or delete it in Step 2."
                )

    return ReviewGateResult(
        passed=len(blocking_reasons) == 0,
        unresolved_count=unresolved_count,
        total_entries=total,
        accepted_count=total - unresolved_count,
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
