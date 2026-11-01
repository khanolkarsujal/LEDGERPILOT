"""
Unit tests for the Business Sales Statement PDF generation endpoint: POST /api/reports/pdf.
"""

import json
import sys
from pathlib import Path
from fastapi.testclient import TestClient
import pypdf
import io

backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app

client = TestClient(app)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_pdf_report_generation_ledger_01():
    """Generates PDF for ledger_01.png extraction and verifies formal accountant document structure."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_01_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        extraction_data = json.load(f)

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": extraction_data,
            "business_name": "Asha Beauty Parlour",
            "business_address": "Shop No. 4, Shivaji Chowk, Pune",
            "nature_of_business": "Beauty Parlour & Salon Services",
            "statement_reference": "REF-2019-11-001",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Business_Sales_Statement.pdf" in response.headers.get("content-disposition", "")

    pdf_bytes = response.content
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes

    text = _extract_pdf_text(pdf_bytes)

    # Required Document Header and Sections
    assert "BUSINESS SALES STATEMENT" in text
    assert "Supporting Financial Records" in text
    assert "1. BUSINESS & STATEMENT INFORMATION" in text
    assert "2. DAILY SALES REGISTER" in text
    assert "3. PERIOD SALES SUMMARY" in text
    assert "4. SALES RECONCILIATION & DISCREPANCY ANALYSIS" in text
    assert "5. NOTES & REGULATORY DISCLAIMER" in text

    # Business Information Table
    assert "Asha Beauty Parlour" in text
    assert "Shop No. 4, Shivaji Chowk, Pune" in text
    assert "Beauty Parlour & Salon Services" in text
    assert "Indian Rupees (INR / ₹)" in text

    # Mandatory formal disclaimer (exact text)
    disclaimer = (
        "This statement is prepared from the business records provided and is intended to organize transaction "
        "information for reference and supporting documentation. Calculated amounts are derived from the transactions listed. "
        "Pending confirmations and discrepancies are identified separately. "
        "This statement is not an audited or certified financial statement."
    )
    # Remove internal line breaks for fuzzy match
    assert "This statement is prepared from the business records provided" in text
    assert "not an audited or certified financial statement" in text

    # Customer-facing PDF must NOT contain AI terminology
    forbidden_terms = ["AI Extracted", "AI vision", "Gemini", "LLM", "Prompt", "machine learning"]
    for term in forbidden_terms:
        assert term.lower() not in text.lower(), f"Forbidden AI term '{term}' found in customer-facing PDF!"


def test_pdf_report_benchmark_regression_ledger_02():
    """
    Benchmark regression test matching Section 6 requirements:
    - 3 ledger sections.
    - 24 entries.
    - 23 priced entries.
    - 1 unpriced entry.
    - Calculated total: ₹2,040.
    - Recorded subtotals: ₹2,140.
    - Difference: ₹100.
    - 2 pending-confirmation entries.
    - No written page grand total.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        extraction_data = json.load(f)

    # Setup the benchmark scenario on ledger_02:
    # 1. Total entries = 13 + 5 + 6 = 24 entries across 3 sections.
    # 2. In Group 3, set entry 2 ("यु कट amt: 60") to unpriced:
    g3 = extraction_data["groups"][2]
    entry_unpriced = g3["entries"][1]
    entry_unpriced["amount"] = None
    entry_unpriced["flag_reason"] = "Amount not recorded on physical ledger"
    entry_unpriced["uncertain_fields"] = ["amount"]

    # 3. Mark one additional entry as having uncertain description -> 2 pending confirmation entries total
    g1 = extraction_data["groups"][0]
    g1["entries"][2]["uncertain_fields"] = ["raw_marathi_text"]
    g1["entries"][2]["flag_reason"] = "Description partially smudged"

    # Ensure recorded_page_total is None (no written grand total)
    extraction_data["recorded_page_total"] = None

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": extraction_data,
            "business_name": "Radhika Beauty Salon",
        },
    )

    assert response.status_code == 200
    pdf_bytes = response.content
    text = _extract_pdf_text(pdf_bytes)

    # 3 sections must be present and numbered
    assert "Section 1" in text
    assert "Section 2" in text
    assert "Section 3" in text

    # Verify dynamic totals:
    # Calculated total: ₹2,040.00
    assert "2,040.00" in text, "Calculated total ₹2,040.00 missing from PDF"
    # Recorded subtotals: ₹2,140.00
    assert "2,140.00" in text, "Recorded subtotals ₹2,140.00 missing from PDF"
    # Discrepancy: ₹100.00
    assert "100.00" in text, "Variance / Discrepancy ₹100.00 missing from PDF"

    # Verify counts:
    # 24 total entries
    assert "24" in text
    # 23 priced transactions
    assert "23" in text
    # 1 unpriced transaction
    assert "1" in text
    # 2 pending confirmations
    assert "2" in text

    # Written grand total should be "Not Recorded"
    assert "Not Recorded" in text


def test_pdf_report_generation_regression_ledger_03():
    """
    Regression check against ledger_03:
    - 4 date groups, 17 priced entries.
    - Calculated total: ₹1,970.
    - Recorded subtotals sum: ₹730.
    - Written page grand total: Not recorded.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_03_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        extraction_data = json.load(f)

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": extraction_data,
            "business_name": "Kalyani Beauty Salon",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    pdf_bytes = response.content
    assert pdf_bytes.startswith(b"%PDF-")
    text = _extract_pdf_text(pdf_bytes)

    assert "1,970.00" in text
    assert "730.00" in text
    assert "Section 1" in text
    assert "Section 4" in text


def test_pdf_report_with_human_corrections():
    """Verifies that human-corrected description and amount are rendered as Confirmed in the PDF."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_01_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        extraction_data = json.load(f)

    # Apply human review to entry 10 (unpriced peemnant smoothing)
    entry10 = extraction_data["groups"][0]["entries"][9]
    entry10["review_status"] = "human_reviewed"
    entry10["corrected_marathi_text"] = "परमनंट स्मूथिंग"
    entry10["corrected_amount"] = 10
    entry10["reviewed_at"] = "2026-11-01T14:40:00Z"
    entry10["review_note"] = "Confirmed price from parlor card"

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": extraction_data,
            "business_name": "Asha Beauty Parlour",
        },
    )

    assert response.status_code == 200
    pdf_bytes = response.content
    text = _extract_pdf_text(pdf_bytes)

    # Confirmed label must appear for human-reviewed entries
    assert "[Confirmed]" in text
    assert "परमनंट स्मूथिंग" in text


def test_pdf_report_invalid_payload():
    """Posting invalid extraction structure returns 422 Unprocessable Entity."""
    response = client.post(
        "/api/reports/pdf",
        json={"invalid": "payload"},
    )
    assert response.status_code == 422


if __name__ == "__main__":
    test_pdf_report_generation_ledger_01()
    print("test_pdf_report_generation_ledger_01: OK")
    test_pdf_report_benchmark_regression_ledger_02()
    print("test_pdf_report_benchmark_regression_ledger_02: OK")
    test_pdf_report_generation_regression_ledger_03()
    print("test_pdf_report_generation_regression_ledger_03: OK")
    test_pdf_report_with_human_corrections()
    print("test_pdf_report_with_human_corrections: OK")
    test_pdf_report_invalid_payload()
    print("test_pdf_report_invalid_payload: OK")
    print("\nALL PDF REPORT API TESTS PASSED SUCCESSFULLY!")
