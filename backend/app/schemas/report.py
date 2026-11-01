"""
Schemas for PDF report generation requests.
"""

from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.ledger import LedgerPageExtraction


class PDFReportRequest(BaseModel):
    """Request payload for generating the Business Sales Statement PDF."""

    extraction: LedgerPageExtraction = Field(
        description="Structured extraction data from the current session, containing all groups and entries with human corrections."
    )
    business_name: Optional[str] = Field(
        default=None,
        description="Optional business trade name provided by the user (defaults to 'Not Provided' if omitted).",
    )
    business_address: Optional[str] = Field(
        default=None,
        description="Optional business address (defaults to 'Not Provided' if omitted).",
    )
    nature_of_business: Optional[str] = Field(
        default=None,
        description="Optional nature or trade category of business.",
    )
    statement_reference: Optional[str] = Field(
        default=None,
        description="Optional statement reference or identifier.",
    )

