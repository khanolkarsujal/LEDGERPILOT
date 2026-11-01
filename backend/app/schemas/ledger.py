"""
Pydantic schemas for handwritten ledger extraction using Gemini 2.5 Flash.

Adheres strictly to the invariants in architecture.md:
- Never silently guess: unreadable/uncertain values are null or marked.
- Money represented as Decimal (or float/int in JSON conversion).
- Original Marathi descriptions preserved without translation.
- Income/expense distinguished only when explicit visual/textual evidence exists.
"""

from decimal import Decimal
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class LedgerEntry(BaseModel):
    """Represents a single handwritten transaction row or item on the ledger page."""

    entry_index: int = Field(
        description="Sequential index of the entry within its group or page (1-based)."
    )
    raw_marathi_text: Optional[str] = Field(
        default=None,
        description="Exact handwritten Marathi description transcribed verbatim without English translation. Null if completely illegible.",
    )
    amount: Optional[Decimal] = Field(
        default=None,
        description="Transaction amount in numerical form (e.g. 500, 1250.50). Null if unreadable or absent.",
    )
    entry_type: Literal["income", "expense", "credit", "debit", "unknown"] = Field(
        default="unknown",
        description="Classification (income/expense/credit/debit) ONLY if explicitly indicated by ledger headers (e.g., जमा / नावे, रोख, खर्च) or unambiguous context. If not explicitly certain, must be 'unknown'.",
    )
    uncertain_fields: list[str] = Field(
        default_factory=list,
        description="List of fields that are smudged, uncertain, cut off, or ambiguous (e.g. ['amount', 'raw_marathi_text']).",
    )
    flag_reason: Optional[str] = Field(
        default=None,
        description="Short reason if any field is uncertain or flagged for human review (e.g. 'amount digit smudged', 'unreadable Marathi character').",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, v):
        if v is None or v == "" or (isinstance(v, str) and (v.strip() == "" or v.strip().lower() in ("null", "none", "-", "—"))):
            return None
        return v


class TransactionGroup(BaseModel):
    """Represents a date section, column, or logical block on the ledger page."""

    group_id: str = Field(
        description="Unique identifier for this group or section (e.g. 'group_1', 'section_date_24_03')."
    )
    date_raw: Optional[str] = Field(
        default=None,
        description="Raw handwritten date string as written on the page (e.g. '२४/०३/२४', '24-3-24'). Null if omitted.",
    )
    date_iso: Optional[str] = Field(
        default=None,
        description="Standardized ISO 8601 date (YYYY-MM-DD) if determinable with confidence; otherwise null.",
    )
    entries: list[LedgerEntry] = Field(
        default_factory=list,
        description="List of transaction entries belonging to this group.",
    )
    recorded_group_total: Optional[Decimal] = Field(
        default=None,
        description="Subtotal or total explicitly written, underlined, or boxed at the bottom of this group. Null if not written.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Layout observations (e.g. 'left column', 'header in red ink', 'boxed total').",
    )

    @field_validator("recorded_group_total", mode="before")
    @classmethod
    def parse_group_total(cls, v):
        if v is None or v == "" or (isinstance(v, str) and (v.strip() == "" or v.strip().lower() in ("null", "none", "-", "—"))):
            return None
        return v


class LedgerPageExtraction(BaseModel):
    """Structured extraction of an entire handwritten ledger page."""

    page_summary: str = Field(
        description="Brief summary of the visual page layout, orientation, column structure, and handwriting clarity."
    )
    groups: list[TransactionGroup] = Field(
        default_factory=list,
        description="List of transaction groups/sections found on the page.",
    )
    recorded_page_total: Optional[Decimal] = Field(
        default=None,
        description="Grand total or final page balance explicitly written at the bottom of the page, or null if none.",
    )
    unreadable_sections_found: bool = Field(
        default=False,
        description="True if any unreadable text, heavy ink blots, torn edges, or obscure marks are present on the page.",
    )

    @field_validator("recorded_page_total", mode="before")
    @classmethod
    def parse_page_total(cls, v):
        if v is None or v == "" or (isinstance(v, str) and (v.strip() == "" or v.strip().lower() in ("null", "none", "-", "—"))):
            return None
        return v
