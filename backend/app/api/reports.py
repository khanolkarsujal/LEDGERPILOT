"""
API router for report generation (PDF and exports).

Endpoints:
- POST /api/reports/pdf: Generates and streams the Business Sales Statement PDF.
  Enforces mandatory human-review gate: every transaction must be confirmed,
  and any totaling discrepancies must be acknowledged.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.reports.pdf_generator import generate_pdf_report
from app.schemas.report import (
    PDFReportRequest,
    check_arithmetic_discrepancies,
    check_review_gate,
)

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.post(
    "/pdf",
    summary="Generate Business Sales Statement PDF",
    response_description="Binary PDF file stream",
)
def export_pdf_report(request: PDFReportRequest) -> Response:
    """
    Generates a professional Business Sales Statement PDF from
    the structured ledger records and human review confirmations.

    Enforces mandatory review gate:
    1. Every entry must have review_status == 'human_reviewed'.
    2. No missing descriptions or unconfirmed values.
    3. If handwritten subtotals differ from calculated totals,
       the user must explicitly acknowledge discrepancies.
    """
    # ── 1. Mandatory Review Gate ──
    gate = check_review_gate(request.extraction)
    if not gate.passed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "review_gate_failed",
                "message": "PDF generation blocked: not all entries have been reviewed.",
                "unreviewed_count": gate.unreviewed_count,
                "total_entries": gate.total_entries,
                "reviewed_count": gate.reviewed_count,
                "blocking_reasons": gate.blocking_reasons,
            },
        )

    # ── 2. Discrepancy Acknowledgment Gate ──
    discrepancies = check_arithmetic_discrepancies(request.extraction)
    if discrepancies and not request.acknowledge_discrepancies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "discrepancy_not_acknowledged",
                "message": (
                    "Handwritten subtotals differ from calculated totals. "
                    "You must acknowledge the discrepancies before generating the statement."
                ),
                "discrepancies": [
                    {
                        "section_index": d.section_index,
                        "section_label": d.section_label,
                        "written_subtotal": float(d.written_subtotal),
                        "calculated_total": float(d.calculated_total),
                        "difference": float(d.difference),
                    }
                    for d in discrepancies
                ],
            },
        )

    try:
        pdf_bytes = generate_pdf_report(
            extraction=request.extraction,
            business_name=request.business_name,
            business_address=request.business_address,
            nature_of_business=request.nature_of_business,
            statement_reference=request.statement_reference,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="Business_Sales_Statement.pdf"',
                "Content-Type": "application/pdf",
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF report: {str(e)}",
        )
