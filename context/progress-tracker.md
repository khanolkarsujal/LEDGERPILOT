# Progress Tracker

Update this file after every meaningful implementation change.

## Current Phase

- Milestone 1 Complete: Code secured in Git, Baseline benchmark established.
- Milestone 2 Complete: Live LedgerPilot Dashboard, Asynchronous Job-based Extraction API, Real-time Processing Stages, Split-Screen Review UI.
- Milestone 3 Complete: Manual Review & Correction Workflow, Non-destructive human edits, Arithmetic Discrepancy Feedback.
- Final Implementation Complete: Mandatory Human-Review Gate, Transaction Deletion with Reactive Recalculation, Discrepancy Acknowledgment Gate, and Official Accountant-Style Business Sales Statement PDF for Loan Documentation.

## Current Goal

- Final product delivered: End-to-end verified pipeline from ledger upload, background extraction, side-by-side review, mandatory human confirmation of all transactions, non-destructive editing and deletion with dynamic recalculation, to downloadable accountant-prepared Business Sales Statement PDF.

## Completed

- Chose the problem: small shopkeepers record sales in handwritten notebooks, and banks need digital records for loan applications.
- Chose the target user: small shopkeepers who record sales in handwritten notebooks and need a bank loan.
- Defined the MVP journey, tech stack, and six-step roadmap.
- Step 1: Project setup complete (React + TypeScript strict, Vite, lucide-react, FastAPI, health check, CORS).
- Step 2: Image upload and preview complete (mobile-friendly, 10MB limit, preview cleanup).
- Step 3 (Initial Experiment): Gemini extraction experiment complete on real handwritten Marathi ledger (`assests/img/ledger-page.png`).
- Milestone 1: Secure Code and Establish Extraction Benchmark complete:
  - Repository initialized on `main` branch with strict `.gitignore`.
  - Ground truth dataset established in `tests/data/ground_truth/ground_truth.json` (54 entries across 9 date groups across 3 real images).
  - Automated benchmark evaluation suite (`tests/run_benchmark.py`).
  - Empirical accuracy: 100% date recognition, 100% subtotals capture, 92.59% amounts exact match, 100% unpriced line flagging.
- Milestone 2: Frontend-Backend Integration & Live LedgerPilot Dashboard complete:
  - FastAPI asynchronous job-based endpoint (`POST /api/extract/jobs`, `GET /api/extract/jobs/{job_id}`) alongside thin synchronous route (`POST /api/extract`).
  - Non-blocking background execution via threadpool; `/health` responds with sub-millisecond latency during active extraction.
  - 6-stage lifecycle event logging streamed to the frontend.
  - Full split-screen review dashboard (`ExtractionResultView.tsx`) with collapsible document viewer, dual-tab interface, and Devanagari typography.
- Dashboard Trust & Arithmetic Feedback complete:
  - Root cause analysis on unpriced entries: missing amounts remain `null` or visibly "Not recorded" and never assigned an invented value.
  - Local arithmetic calculation of line items per date group excluding unpriced items.
  - Non-judgmental totaling mismatch banner comparing written subtotals vs. calculated sums.
  - Truthful verification labels: raw extractions marked "AI extracted" / "Needs review"; "Human reviewed" reserved strictly for post-confirmation states.
  - Page Financial Reconciliation distinguishing entry sums, written group subtotals, and written page grand totals.
- Manual Review & Correction Workflow complete:
  - Non-destructive tracking fields (`review_status`, `corrected_marathi_text`, `corrected_amount`, `reviewed_at`, `review_note`), preserving original AI values intact.
  - `EntryReviewModal` component for editing descriptions, correcting amounts, confirming unpriced items as "Not recorded", and confirming as-is.
  - Real-time recalculation of date-group calculated totals, page calculated sums, and discrepancy comparisons upon save.
  - Automated 13-case test suite (`tests/test_manual_review_flow.js`) passing 100%.
- Professional Business Sales Statement PDF for Loan Documentation complete (Template-Perfect):
  - Strictly matches `ledgerpilot_business_sales_statement_template.png` with pixel-level fidelity.
  - Top navy bar (`#0A2540`, 3.5 pt) across all pages.
  - Boxed `BUSINESS INFORMATION` card: business details printed only when actually supplied by user; omitted without awkward placeholders or "Not Provided" text when unavailable.
  - `1. DAILY SALES REGISTER`: 4-column transaction table (`Date`, `Sr. No.`, `Particulars / Description`, `Amount (₹)`) with navy header, native Devanagari typography (`NirmalaUI`), date displayed only on the first row of each section, missing amounts marked as "Not Recorded".
  - Standalone `SECTION {N} TOTALS` outlined box below each section table displaying Transactions count, Calculated total, Handwritten subtotal, and Difference.
  - `2. PERIOD SUMMARY`: Soft light-green container box (`#EAF7EE`) featuring Calculated sales total, Recorded daily subtotals, Written grand total, Amounts not recorded count, and Pending confirmation count.
  - `3. SALES RECONCILIATION`: 4-column table detailing every section separately, including preserving separate sections that share the same date.
  - Formal disclaimer note matching template text verbatim.
  - Running footer: `BUSINESS SALES STATEMENT • Supporting Financial Records | Page X of Y`.
- Mandatory Human-Review Gate & Transaction Deletion complete:
  - Strict review gate enforced both in frontend and backend API (`POST /api/reports/pdf`).
  - Statement generation is blocked (HTTP 422 `review_gate_failed`) if even ONE transaction is unreviewed, pending confirmation, or missing a description.
  - Per-row transaction deletion with confirmation dialog (`handleExecuteDelete`); deleted entries are filtered out, remaining entries sequentially re-indexed, and all group sums, page sums, and discrepancies recalculate instantly.
  - Quick-review helper actions: "Review Next Pending Entry" and "Confirm Remaining Clean Entries" (confirms all unflagged, priced entries in one click).
  - Arithmetic discrepancy acknowledgment gate (`acknowledge_discrepancies` flag): if handwritten subtotals differ from calculated sums, requires explicit user acknowledgment before generating the PDF statement.
  - Comprehensive automated test suite in `tests/test_api_reports.py` (10/10 tests passing).
  - Visual inspection verified via rendered high-resolution PNGs in `scratch/pdf_renders/`.

## Test Results Summary

| Test Suite | File | Tests | Pass Rate |
| :--- | :--- | :--- | :--- |
| PDF Report & Review Gate API | `tests/test_api_reports.py` | 10 | 100% (10/10) |
| Extraction API & Lifecycle | `tests/test_api_extract.py` | 8 | 100% (8/8) |
| Manual Review & Recalculation | `tests/test_manual_review_flow.js` | 13 | 100% (13/13) |
| Extraction Benchmark | `tests/run_benchmark.py` | 3 ledgers | 100% dates/subtotals, 92.59% amounts |
| Frontend Production Build | `npm run build --prefix frontend` | TypeScript + Vite | 100% clean (0 errors) |

## Architecture Decisions

- In-memory session storage, no database for the MVP: fastest to build, and nothing sensitive is stored by default.
- No OpenCV at first: vision model handles reading; Pillow handles EXIF orientation and normalization.
- Rule-based validation and review gate: model confidence alone never clears flags; every transaction must be human-confirmed before formal statement export.
- Non-destructive review model: original AI extractions remain immutable; user corrections and review timestamps stored in dedicated fields.
- Sequential re-indexing on deletion: when an unwanted transaction is deleted, subsequent rows are cleanly re-numbered (1, 2, 3...) to maintain accounting register integrity.
- Server-side independent PDF generation using ReportLab (`SimpleDocTemplate` + `TemplateCanvas`) with native Devanagari font registration (`NirmalaUI` / `Mangal`). Never uses dashboard printouts or `window.print()`.
- Omission of unavailable metadata: when business name/address is not supplied, the fields are omitted cleanly without printing "Not Provided".
- Zero customer-facing AI terminology: words like "AI", "Gemini", "LLM", or "Prompt" never appear in the exported loan document.
