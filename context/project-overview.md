# LedgerPilot

## Overview

LedgerPilot is a mobile-friendly web application that transforms a photograph of a handwritten ledger page (bahi-khata) into structured digital records, an interactive side-by-side review workspace, and a downloadable accountant-prepared **Business Sales Statement (Supporting Financial Records)** PDF. It is built for small shopkeepers and micro-business owners who record daily sales in handwritten notebooks and need formal financial records for bank loan applications.

Banks and formal lenders require structured, credible financial statements. Many micro-entrepreneurs pay expensive data-entry services or turn to high-interest informal lenders because they lack formal digital accounts. LedgerPilot eliminates this barrier by transcribing the handwritten ledger, detecting arithmetic mismatches, enforcing a mandatory human-review gate on every single transaction, and generating an official accountant-style sales statement that transparently presents both handwritten records and calculated totals.

It prepares supporting financial records for loan applications. It does not approve loans, score credit, or connect directly to lenders.

Built for the Ctrl+V Hackathon (6 to 10 Nov 2026), whose mission is to make opportunities easier to access by removing unnecessary barriers.

## Goals

1. Convert a photo of a handwritten ledger page into structured digital records in a single upload.
2. Provide real-time processing transparency across upload, preprocessing, Gemini vision extraction, and schema parsing.
3. Measure and report field accuracy against transcribed ground truth on real handwritten Marathi ledger pages.
4. Never silently guess: every unreadable, unpriced, or rule-failing value is flagged for review instead of being invented.
5. Enforce a mandatory human-review gate: PDF statement generation is blocked until every transaction is confirmed, corrected, or deleted.
6. Generate a conventional accountant-style Business Sales Statement PDF strictly matching the official financial template with native Marathi Devanagari script and Rupee (₹) formatting.

## Core User Flow

1. **Upload & Preprocessing**: The shopkeeper uploads a photo of a handwritten ledger page (JPEG/PNG up to 10 MB).
2. **AI Extraction**: The backend processes the image via Gemini Flash, streaming lifecycle stages (`upload_received`, `preprocessing`, `gemini_request_started`, `waiting_gemini`, `parsing_extraction`, `completed`).
3. **Side-by-Side Review Workspace**: The UI displays the original ledger photo beside the transcribed transactions, separated by date groups.
4. **Arithmetic Feedback & Reconciliation**: The system calculates valid numeric line-item amounts per date group and compares them with handwritten subtotals, providing clear, non-judgmental feedback.
5. **Mandatory Human Review**: The user inspects every transaction. Users can:
   - Correct the Marathi service/item description.
   - Enter or correct the numerical amount.
   - Confirm unpriced entries as "Not Recorded".
   - Confirm accurate entries as-is.
   - Delete unwanted or incorrect transactions with confirmation.
   - Use quick-review actions ("Review Next Pending" / "Confirm Remaining Clean Entries").
6. **Discrepancy Acknowledgment**: If handwritten subtotals differ from calculated sums, the system displays the mismatches and requires explicit user acknowledgment.
7. **Document Generation**: The user downloads a formal, accountant-prepared **Business Sales Statement** PDF for loan documentation.

## Features

### Capture & Preprocessing
- Upload photo via mobile camera capture or gallery selection.
- Client-side format (JPEG, PNG) and file size validation (max 10 MB).
- Pillow-based EXIF orientation normalization.

### AI Extraction
- Google Gemini vision extraction with structured Pydantic schemas.
- Verbatim transcription of handwritten Marathi text in Devanagari script without English translation.
- Date recognition and ISO conversion (e.g. `४/११/२०१९ सोमवार` -> `2019-11-04`).
- Handwritten line-item amounts and written subtotals captured separately.
- Unreadable or missing amounts returned as `null` with explicit reasons, never guessed.

### Trust, Validation & Review
- Transparent status labeling: raw extractions marked "AI extracted" / "Needs review"; "Human reviewed" reserved strictly for post-confirmation states.
- Local arithmetic recalculation per section excluding unpriced items.
- Non-destructive review tracking: original extractions remain immutable; corrections stored in dedicated fields.
- Individual transaction deletion with modal confirmation and sequential re-indexing.
- Mandatory Review Gate: PDF generation blocked on frontend and backend until 100% of remaining entries are human-confirmed.

### Formal Business Sales Statement PDF
- Strictly matches `ledgerpilot_business_sales_statement_template.png` with pixel-level fidelity.
- Traditional accounting layout: top navy bar, formal heading, INR currency identifier.
- Business details printed only when actually supplied; cleanly omitted without "Not Provided" text when unavailable.
- 4-column Daily Sales Register (`Date`, `Sr. No.`, `Particulars / Description`, `Amount (₹)`).
- Section totals boxes with Transactions count, Calculated total, Handwritten subtotal, and Difference.
- Period summary box with total sales, subtotals sum, written grand total, unpriced count, and pending count.
- Sales reconciliation table preserving separate sections that share the same date.
- Formal accounting disclaimer and running page numbers (`Page X of Y`).
- Zero AI terminology in customer-facing PDF document.

## Scope

### In Scope
- Single-page photo upload and preview.
- Asynchronous job-based AI extraction with lifecycle logging.
- Side-by-side review workspace with Devanagari typography.
- Rule-based arithmetic validation and discrepancy detection.
- Human review and correction of every transaction.
- Individual transaction deletion with confirmation and sequential re-indexing.
- Mandatory review gate and discrepancy acknowledgment gate.
- Formal Business Sales Statement PDF download.
- Automated test suites (PDF report API, extraction API, manual review flow).

### Out of Scope (Deferred)
- WhatsApp or Tally integration.
- GST filing or GST portal integration.
- Credit scoring or lender direct connection.
- Multi-page batch uploads.
- User accounts and authentication (single-session MVP).
- Persistent database storage (in-memory per session).
