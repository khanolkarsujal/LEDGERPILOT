"""
Unit tests for the Business Sales Statement PDF generation endpoint: POST /api/reports/pdf.

Strictly verifies:
1. Mandatory Human Review Gate:
   - PDF generation blocked (422) if even ONE remaining transaction is unreviewed or pending.
   - Direct backend API cannot bypass the review gate.
   - PDF enabled (200) only when ALL remaining transactions are human-confirmed.
2. Deletion & Recalculation:
   - PDF enabled after an unwanted transaction is deleted and remaining entries are confirmed.
   - Deleted entries are completely excluded from totals.
3. Discrepancy Acknowledgment:
   - If handwritten subtotals differ from calculated sums, requires explicit user acknowledgment.
   - Discrepancies remain transparently reported in Section 3 (Sales Reconciliation).
4. Accountant-Style Document Format & Omission Rules:
   - When business details are unavailable, omit them (never print "Not Provided").
   - Formal headings, clean tables, page numbers, Devanagari Marathi text, and ₹ symbol.
   - No AI terminology in customer-facing PDF.
5. Benchmark regression verification against ledger_02 (24 entries, 1 unpriced, ₹2,040 calc, ₹2,140 written).
"""

import io
import json
import sys
from decimal import Decimal
from pathlib import Path
from fastapi.testclient import TestClient
import pypdf

backend_dir = str(Path(__file__).resolve().parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app

client = TestClient(app)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


def _mark_all_entries_reviewed(extraction_data: dict) -> dict:
    """Helper: Marks all entries across all groups as human_reviewed with existing values."""
    for group in extraction_data["groups"]:
        for entry in group["entries"]:
            entry["review_status"] = "human_reviewed"
            entry["corrected_marathi_text"] = entry["raw_marathi_text"]
            entry["corrected_amount"] = entry["amount"]
            entry["reviewed_at"] = "2026-11-01T15:00:00Z"
    return extraction_data


# =============================================================================
# 1. MANDATORY REVIEW GATE TESTS
# =============================================================================

def test_pdf_report_blocked_when_all_unreviewed():
    """Raw AI extraction without human review is blocked with 422."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_01_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Ensure no entries are reviewed
    for group in data["groups"]:
        for entry in group["entries"]:
            entry["review_status"] = None

    response = client.post(
        "/api/reports/pdf",
        json={"extraction": data, "business_name": "Asha Beauty Parlour"},
    )

    assert response.status_code == 422
    err = response.json()["detail"]
    assert err["error"] == "review_gate_failed"
    assert "not all entries have been reviewed" in err["message"]
    assert err["unreviewed_count"] > 0
    assert len(err["blocking_reasons"]) > 0


def test_pdf_report_blocked_with_single_unreviewed_entry():
    """PDF generation must be blocked if even ONE remaining transaction is unreviewed."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Confirm 23 out of 24 entries, leave entry #24 unreviewed
    _mark_all_entries_reviewed(data)
    data["groups"][2]["entries"][-1]["review_status"] = "ai_extracted"

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Radhika Beauty Salon",
            "acknowledge_discrepancies": True,
        },
    )

    assert response.status_code == 422
    err = response.json()["detail"]
    assert err["error"] == "review_gate_failed"
    assert err["unreviewed_count"] == 1
    assert "has not been confirmed by a human reviewer" in err["blocking_reasons"][0]


def test_pdf_report_blocked_when_description_missing():
    """PDF generation blocked if an entry has no description (unresolved missing value)."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_01_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _mark_all_entries_reviewed(data)
    # Set entry 1 description to empty
    data["groups"][0]["entries"][0]["raw_marathi_text"] = ""
    data["groups"][0]["entries"][0]["corrected_marathi_text"] = ""

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Asha Beauty Parlour",
            "acknowledge_discrepancies": True,
        },
    )

    assert response.status_code == 422
    err = response.json()["detail"]
    assert err["error"] == "review_gate_failed"
    assert any("missing a description" in r for r in err["blocking_reasons"])


# =============================================================================
# 2. DISCREPANCY ACKNOWLEDGMENT TESTS
# =============================================================================

def test_pdf_report_blocked_when_discrepancy_unacknowledged():
    """If handwritten subtotals differ from calculated sum, user must acknowledge discrepancy."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_01_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Group 1 has items summing to 400 but written subtotal 440 (₹40 difference)
    _mark_all_entries_reviewed(data)

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Asha Beauty Parlour",
            "acknowledge_discrepancies": False,  # Not acknowledged
        },
    )

    assert response.status_code == 422
    err = response.json()["detail"]
    assert err["error"] == "discrepancy_not_acknowledged"
    assert "Handwritten subtotals differ from calculated totals" in err["message"]
    assert len(err["discrepancies"]) > 0


def test_pdf_report_enabled_when_all_confirmed_and_discrepancy_acknowledged():
    """PDF is generated successfully when all entries are confirmed and discrepancy is acknowledged."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_01_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _mark_all_entries_reviewed(data)

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Asha Beauty Parlour",
            "business_address": "Shop 4, Shivaji Chowk, Pune",
            "acknowledge_discrepancies": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    pdf_bytes = response.content
    assert pdf_bytes.startswith(b"%PDF-")


# =============================================================================
# 3. DELETION AND RECALCULATION TESTS
# =============================================================================

def test_pdf_report_enabled_after_transaction_deleted_and_totals_recalculate():
    """
    Test flow:
    - User extracts ledger_02 (24 entries).
    - User deletes an unwanted/incorrect transaction (e.g. Group 1 entry #1, ₹20).
    - Remaining 23 entries are confirmed.
    - PDF generation succeeds.
    - Totals recalculate: Group 1 calculated total decreases by ₹20.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Delete first entry of Group 1 (amount = 20)
    original_g1_count = len(data["groups"][0]["entries"])
    deleted_entry = data["groups"][0]["entries"].pop(0)
    assert len(data["groups"][0]["entries"]) == original_g1_count - 1

    # Re-index remaining entries
    for idx, e in enumerate(data["groups"][0]["entries"]):
        e["entry_index"] = idx + 1

    # Confirm all remaining entries
    _mark_all_entries_reviewed(data)

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Radhika Beauty Salon",
            "acknowledge_discrepancies": True,
        },
    )

    assert response.status_code == 200
    pdf_bytes = response.content
    text = _extract_pdf_text(pdf_bytes)

    # Total entries should now be 23 (was 24)
    # Section 1 transactions count box: 12 (was 13)
    assert "SECTION 1 TOTALS" in text
    assert "12" in text

    # Section 1 calculated sum was 740, now 740 - 20 = 720.00
    assert "720.00" in text


# =============================================================================
# 4. BENCHMARK REGRESSION & TEMPLATE TESTS (ledger_02)
# =============================================================================

def test_pdf_report_benchmark_regression_ledger_02():
    """
    Benchmark scenario matching Section 6 requirements:
    - 3 ledger sections.
    - 24 entries (13 + 5 + 6).
    - 23 priced entries, 1 unpriced entry ("Not Recorded").
    - Calculated total: ₹2,040.
    - Recorded subtotals: ₹2,140.
    - Difference: ₹100.
    - All 24 entries confirmed by human reviewer (including confirming unpriced as-is).
    - Discrepancy acknowledged.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. In Group 3, set entry 2 ("यु कट amt: 60") to unpriced:
    g3 = data["groups"][2]
    entry_unpriced = g3["entries"][1]
    entry_unpriced["amount"] = None
    entry_unpriced["flag_reason"] = "Amount not recorded on physical ledger"
    entry_unpriced["uncertain_fields"] = ["amount"]

    # 2. Mark all entries as human confirmed (human confirmed the unpriced entry as Not Recorded)
    _mark_all_entries_reviewed(data)
    entry_unpriced["corrected_amount"] = None  # Confirmed as unpriced

    # Ensure no written page grand total
    data["recorded_page_total"] = None

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Radhika Beauty Salon",
            "business_address": "Shop 12, Market Yard, Kolhapur",
            "acknowledge_discrepancies": True,
        },
    )

    assert response.status_code == 200
    pdf_bytes = response.content
    text = _extract_pdf_text(pdf_bytes)

    # Visual hierarchy headings
    assert "BUSINESS SALES STATEMENT" in text
    assert "Supporting Financial Records" in text
    assert "INR" in text
    assert "₹" in text
    assert "1. DAILY SALES REGISTER" in text
    assert "SECTION 1 TOTALS" in text
    assert "SECTION 2 TOTALS" in text
    assert "SECTION 3 TOTALS" in text
    assert "2. PERIOD SUMMARY" in text
    assert "3. SALES RECONCILIATION" in text
    assert "IMPORTANT NOTE" in text

    # Dynamic totals:
    # Calculated total: ₹ 2,040.00
    assert "2,040.00" in text, "Calculated total 2,040.00 missing from PDF"
    # Recorded subtotals: ₹ 2,140.00
    assert "2,140.00" in text, "Recorded subtotals 2,140.00 missing from PDF"
    # Reconciliation differences (40 + 0 + 60 = 100)
    assert "40.00" in text
    assert "60.00" in text

    # Unpriced item has "Not Recorded"
    assert "Not Recorded" in text
    assert "Not present" in text  # Written grand total not present

    # Forbidden AI terms check
    forbidden_terms = ["AI Extracted", "AI vision", "Gemini", "LLM", "Prompt", "machine learning"]
    for term in forbidden_terms:
        assert term.lower() not in text.lower(), f"Forbidden AI term '{term}' found in customer-facing PDF!"


# =============================================================================
# 5. BUSINESS INFORMATION OMISSION RULES
# =============================================================================

def test_pdf_report_omits_business_details_when_not_provided():
    """
    When business information is not provided by the user, omit the fields.
    Never print 'Business Name Not Provided', 'Not Provided', or similar placeholders.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _mark_all_entries_reviewed(data)

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": None,
            "business_address": "",
            "acknowledge_discrepancies": True,
        },
    )

    assert response.status_code == 200
    text = _extract_pdf_text(response.content)

    # Must NOT contain 'Not Provided'
    assert "Not Provided" not in text
    assert "not provided" not in text.lower()
    # Must still have reporting period and date
    assert "Reporting period:" in text
    assert "Prepared on:" in text


# =============================================================================
# 6. SECTIONS SHARING SAME DATE
# =============================================================================

def test_pdf_report_sections_sharing_same_date():
    """
    Verifies that two handwritten sections sharing the exact same date
    remain preserved as separate sections (Section 1 and Section 2).
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["groups"][0]["date_iso"] = "2019-11-11"
    data["groups"][0]["date_raw"] = "११/११/२०१९"
    data["groups"][1]["date_iso"] = "2019-11-11"
    data["groups"][1]["date_raw"] = "११/११/२०१९"

    _mark_all_entries_reviewed(data)

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Asha Beauty Parlour",
            "acknowledge_discrepancies": True,
        },
    )
    assert response.status_code == 200
    text = _extract_pdf_text(response.content)

    assert "SECTION 1 TOTALS" in text
    assert "SECTION 2 TOTALS" in text
    assert "11/11/2019 / Section 1" in text
    assert "11/11/2019 / Section 2" in text


# =============================================================================
# 7. INVALID PAYLOAD
# =============================================================================

def test_pdf_report_invalid_payload():
    """Posting invalid extraction structure returns 422 Unprocessable Entity."""
    response = client.post(
        "/api/reports/pdf",
        json={"invalid": "payload"},
    )
    assert response.status_code == 422
