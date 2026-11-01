"""
API router for report generation (PDF and exports).

Endpoints:
- POST /api/reports/pdf: Generates and streams the Business Financial Records Report PDF.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.reports.pdf_generator import generate_pdf_report
from app.schemas.report import PDFReportRequest

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
    """
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

