"""
Unit tests for the Business Sales Statement PDF generation endpoint: POST /api/reports/pdf.

Verifies:
1. Automatic AI Verification:
   - High-confidence transactions (valid description, valid amount, zero flags) are automatically accepted.
   - Users are not forced to manually confirm high-confidence transactions.
   - Low-confidence transactions (unpriced, smudged, uncertain description) block PDF generation until resolved.
2. Editable Transactions:
   - Automatically accepted transactions remain fully editable and can be corrected or deleted.
3. Automatic Recalculation after Deletion or Editing:
   - Deleting an entry recalculates daily and overall totals.
   - Deleted entries are completely excluded from the generated PDF.
   - Editing an amount or description immediately updates the statement.
4. Business Information Omission Rules:
   - When business name/address are supplied, they appear in BUSINESS INFORMATION.
   - When business details are unavailable, omit them cleanly (never print 'Business Name Not Provided' or 'Address Missing').
5. Professional Accountant Document Structure:
   - Final PDF contains ONLY finished financial statement data.
   - Contains NO internal AI or review-status terminology ('Pending Confirmation', 'Human Reviewed', 'AI Extracted', 'Handwritten Subtotal', 'Calculated vs Handwritten', etc.).
   - Uses conventional accountant terminology: Daily Sales Register, Section Total, Period Summary, Total.
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


# =============================================================================
# 1. AUTOMATIC ACCEPTANCE & LOW-CONFIDENCE FLAGGING TESTS
# =============================================================================

def test_high_confidence_entries_automatically_accepted():
    """
    High-confidence transactions with clean descriptions and amounts are automatically
    accepted and do NOT require the user to manually click-confirm every single entry.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # In ledger_02, all 24 entries have valid descriptions, positive amounts, and 0 flags.
    # Therefore they should be automatically accepted without needing human_reviewed status!
    for group in data["groups"]:
        for entry in group["entries"]:
            entry["review_status"] = None  # Raw AI extraction

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Radhika Beauty Salon",
            "business_address": "Market Yard, Kolhapur",
            "acknowledge_discrepancies": True,
        },
    )

    # Must succeed with 200 without requiring manual confirmation of all 24 entries
    assert response.status_code == 200
    pdf_bytes = response.content
    assert pdf_bytes.startswith(b"%PDF-")
    text = _extract_pdf_text(pdf_bytes)
    assert "BUSINESS SALES STATEMENT" in text
    assert "Radhika Beauty Salon" in text


def test_low_confidence_or_unpriced_entry_blocks_pdf():
    """
    An entry with an unconfirmed missing amount (unpriced) or uncertainty flag
    genuinely requires human attention in Step 2 and blocks PDF generation until resolved.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_01_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Entry #10 ("peemnant smoothing") has amount: null and uncertain_fields: ['amount']
    # It has NOT been reviewed yet.
    entry10 = data["groups"][0]["entries"][9]
    assert entry10["amount"] is None
    entry10["review_status"] = None

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
    assert err["unresolved_count"] >= 1
    assert any("Entry #10" in r for r in err["blocking_reasons"])


def test_missing_description_blocks_pdf():
    """An entry with an unreadable or empty description blocks PDF until resolved."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Set one entry description to empty
    data["groups"][0]["entries"][0]["raw_marathi_text"] = ""
    data["groups"][0]["entries"][0]["corrected_marathi_text"] = ""

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
    assert any("Entry #1" in r for r in err["blocking_reasons"])


# =============================================================================
# 2. EDITING & DELETION RECALCULATION TESTS
# =============================================================================

def test_deleting_entry_recalculates_totals_and_excludes_from_pdf():
    """
    When a transaction is deleted:
    - It is excluded from the section and overall totals.
    - It does not appear in the generated PDF.
    - Daily and overall totals recalculate immediately.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Initial Section 1 has 13 entries summing to 740.
    # Delete Entry #1 (amount = 20)
    data["groups"][0]["entries"].pop(0)

    # Re-index remaining entries
    for idx, e in enumerate(data["groups"][0]["entries"]):
        e["entry_index"] = idx + 1

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

    # Section 1 total was 740.00, now 740 - 20 = 720.00
    assert "720.00" in text
    # Section 1 transaction count is now 12 (was 13)
    assert "12" in text
    # Overall sales was 2,100, now 2,080.00
    assert "2,080.00" in text


def test_editing_amount_recalculates_totals():
    """
    When an amount is edited (e.g. entry #1 changed from 20 to 50):
    - Daily total increases by 30 (740 -> 770).
    - Overall sales total increases by 30 (2,100 -> 2,130).
    - Statement reflects edited total.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Edit entry 1 amount from 20 to 50 (+30)
    e1 = data["groups"][0]["entries"][0]
    e1["review_status"] = "human_reviewed"
    e1["corrected_amount"] = 50

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Radhika Beauty Salon",
            "acknowledge_discrepancies": True,
        },
    )

    assert response.status_code == 200
    text = _extract_pdf_text(response.content)

    # Section 1 total is now 740 + 30 = 770.00
    assert "770.00" in text
    # Overall sales is now 2,100 + 30 = 2,130.00
    assert "2,130.00" in text


def test_auto_accepted_entries_remain_editable():
    """
    Automatically accepted entries remain fully editable by the user.
    Editing a description or amount updates the statement.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # User modifies an auto-accepted description to a custom service note
    e2 = data["groups"][0]["entries"][1]
    e2["review_status"] = "human_reviewed"
    e2["corrected_marathi_text"] = "हेअर स्पा स्पेशल"

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Radhika Beauty Salon",
            "acknowledge_discrepancies": True,
        },
    )

    assert response.status_code == 200
    text = _extract_pdf_text(response.content)
    assert "हेअर स्पा स्पेशल" in text


# =============================================================================
# 3. DISCREPANCY ACKNOWLEDGMENT TEST
# =============================================================================

def test_unacknowledged_discrepancy_blocks_pdf():
    """If handwritten subtotals differ from calculated sum, user must acknowledge in Step 2."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_01_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # In ledger_01, entries 1-9 sum to 430 (90 + 30*6 + 80 + 80).
    # Group 1 handwritten recorded total is 440.
    # Group 2 entries sum to 230, matching handwritten recorded total of 230.
    # If entry 10 is reviewed with amount = 50, calculated total = 480 != 440.
    e10 = data["groups"][0]["entries"][9]
    e10["review_status"] = "human_reviewed"
    e10["corrected_amount"] = 50  # sum = 480 != 440

    response = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Asha Beauty Parlour",
            "acknowledge_discrepancies": False,  # Not acknowledged -> 422
        },
    )
    assert response.status_code == 422
    err = response.json()["detail"]
    assert err["error"] == "discrepancy_not_acknowledged"

    # Now acknowledge discrepancy -> succeeds with 200
    response_ack = client.post(
        "/api/reports/pdf",
        json={
            "extraction": data,
            "business_name": "Asha Beauty Parlour",
            "acknowledge_discrepancies": True,  # Acknowledged -> 200
        },
    )
    assert response_ack.status_code == 200
    assert response_ack.headers["content-type"] == "application/pdf"


# =============================================================================
# 4. FINAL PDF CONTAINS NO INTERNAL AI / WORKFLOW TERMINOLOGY
# =============================================================================

def test_final_pdf_contains_no_internal_ai_or_review_terms():
    """
    Customer-facing PDF must look like an official accountant-prepared sales register.
    It must NOT contain:
    - Pending Confirmation
    - Human Reviewed
    - AI Extracted
    - AI Confidence
    - Exact Match
    - Handwritten Subtotal
    - Calculated vs Handwritten
    - Business Name Not Provided
    - Address Missing
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

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
    text = _extract_pdf_text(response.content)

    forbidden_phrases = [
        "Pending Confirmation",
        "Human Reviewed",
        "AI Extracted",
        "AI Confidence",
        "Exact Match",
        "Handwritten Subtotal",
        "Calculated vs Handwritten",
        "Calculated total",
        "Business Name Not Provided",
        "Address Missing",
        "Machine Learning",
        "Gemini",
        "LLM",
        "Prompt",
    ]

    for phrase in forbidden_phrases:
        assert phrase.lower() not in text.lower(), f"Forbidden internal term '{phrase}' found in final PDF!"

    # Must contain conventional accountant terminology:
    assert "BUSINESS SALES STATEMENT" in text
    assert "Supporting Financial Records" in text
    assert "1. DAILY SALES REGISTER" in text
    assert "2. PERIOD SUMMARY" in text
    assert "3. DAILY REGISTER SUMMARY" in text
    assert "Total Sales" in text
    assert "Total" in text
    assert "IMPORTANT NOTE" in text


# =============================================================================
# 5. BUSINESS INFORMATION FORMATTING AND CLEAN OMISSION
# =============================================================================

def test_business_details_cleanly_omitted_when_unavailable():
    """
    When business details are not provided by the user, omit the fields.
    Never print 'Business Name Not Provided', 'Address Missing', or 'Not Provided'.
    """
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

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

    assert "Not Provided" not in text
    assert "not provided" not in text.lower()
    assert "Address Missing" not in text
    assert "Reporting period:" in text
    assert "Prepared on:" in text


def test_pdf_report_sections_sharing_same_date():
    """Multiple sections sharing the exact same date are preserved separately in the register."""
    path = Path(__file__).resolve().parent / "data" / "extraction_results" / "ledger_02_extracted.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["groups"][0]["date_iso"] = "2019-11-11"
    data["groups"][0]["date_raw"] = "११/११/२०१९"
    data["groups"][1]["date_iso"] = "2019-11-11"
    data["groups"][1]["date_raw"] = "११/११/२०१९"

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

    assert "SECTION 1 TOTAL" in text
    assert "SECTION 2 TOTAL" in text
    assert "11/11/2019 / Section 1" in text
    assert "11/11/2019 / Section 2" in text


def test_pdf_report_invalid_payload():
    """Posting invalid extraction structure returns 422 Unprocessable Entity."""
    response = client.post(
        "/api/reports/pdf",
        json={"invalid": "payload"},
    )
    assert response.status_code == 422
