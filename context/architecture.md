# Architecture Context

## Stack

| Layer | Technology | Role |
| :--- | :--- | :--- |
| Frontend | React + TypeScript (strict) | Upload, split-screen review, entry correction, deletion, gate validation, download |
| Bundler | Vite | Dev server and production build for the React frontend |
| Icons | lucide-react | Stroke-based icons (upload, check, alert-triangle, pencil, trash, download, shield) |
| Backend | Python 3.11 + FastAPI | HTTP API; orchestrates extraction, review gate, validation, and report generation |
| AI extraction | Google Gemini API via google-genai | Reads handwritten Marathi ledger photos using Gemini Flash |
| Image handling | Pillow | EXIF orientation normalization, resizing, and preparation |
| Validation & Gates | Python (plain rule functions) | Enforces mandatory review gate, missing field checks, and discrepancy detection |
| PDF Reporting | ReportLab + Nirmala UI / Mangal | Generates official accountant-style Business Sales Statement PDF |
| Storage (MVP) | In-memory, per session | Holds current page, rows, flags, events, and user corrections |
| Auth | None in MVP | Single-user demo; no accounts |

Deferred: OpenCV, SQLite, WhatsApp, Tally, GST, credit scoring, lender integration.

## System Boundaries

- `frontend/src/` — React UI only.
  - `components/UploadView.tsx` — Upload and client validation.
  - `components/LiveProcessingView.tsx` — Real-time 6-stage lifecycle animation.
  - `components/ExtractionResultView.tsx` — Split-screen workspace, table, deletion dialogs, gate warnings, discrepancy acknowledgment modal.
  - `components/EntryReviewModal.tsx` — Edit description, amount, toggle unpriced, confirm as-is, delete.
  - `api/extract.ts` & `api/reports.ts` — Typed backend API clients.
  - Never calls Gemini directly and never holds API keys.
- `backend/app/api/` — FastAPI routes.
  - `extract.py`: `POST /api/extract/jobs` (background worker), `GET /api/extract/jobs/{job_id}`, `POST /api/extract`.
  - `reports.py`: `POST /api/reports/pdf` with strict review gate and discrepancy acknowledgment enforcement.
- `backend/app/extraction/` — Pillow EXIF normalization and Gemini vision prompt execution.
- `backend/app/schemas/` — Pydantic models.
  - `ledger.py`: `LedgerEntry`, `TransactionGroup`, `LedgerPageExtraction` with review tracking fields.
  - `report.py`: `PDFReportRequest`, `ReviewGateResult`, `check_review_gate`, `check_arithmetic_discrepancies`.
- `backend/app/reports/` — `pdf_generator.py` building formal Business Sales Statement PDF strictly matching the official template.
- `tests/` — Automated test suites.
  - `test_api_reports.py` (10 tests: review gate blocking, unreviewed detection, deletion recalculation, template fidelity).
  - `test_api_extract.py` (8 tests: job lifecycle, polling, validation).
  - `test_manual_review_flow.js` (13 tests: editing, as-is confirmation, recalculation).

## Review Gate & Financial Validation Architecture

1. **Intelligent Auto-Verification & Targeted Review Gate**:
   - `is_high_confidence_entry(entry)` checks if an extracted transaction has a valid description, positive amount, and zero uncertainty flags or flag reasons. Clean entries are accepted automatically (`auto_accepted`).
   - `requires_human_attention(entry)` flags only entries with genuine ambiguity, missing descriptions, unpriced amounts, or explicit uncertainty flags.
   - `check_review_gate(extraction)` traverses all entries across all groups.
   - Blocks PDF generation with HTTP 422 (`review_gate_failed`) only if any unresolved flagged entry remains.
   - All entries (including auto-accepted entries) remain fully editable and deletable at any time.
   - Enforced client-side (badge alerts, review buttons) and server-side (cannot be bypassed by direct API calls).

2. **Immediate Dynamic Recalculation & Deletion**:
   - Users can delete unwanted or incorrectly detected transactions with a confirmation dialog.
   - Deletion removes the item from the group's `entries` array.
   - Remaining entries are sequentially re-indexed (`entry_index: 1, 2, 3...`) to maintain accounting register integrity.
   - All group sums, page sums, discrepancy calculations, and review counts recalculate reactively upon editing or deletion.
   - Deleted entries are completely excluded everywhere, including the exported PDF.

3. **Business Details Management**:
   - Before statement export, missing business name and address are requested.
   - Users can enable "Remember business details", saving preferences securely in browser `localStorage` (`ledgerpilot_business_details`) without introducing database dependencies or accounts.
   - Stored business details can be viewed and edited at any time.

4. **Discrepancy Acknowledgment Gate**:
   - Compares handwritten subtotals (`recorded_group_total`) against calculated item sums (`calculate_group_effective_sum`).
   - If a mismatch exists (e.g. written ₹780 vs. calculated ₹740), the user must explicitly acknowledge the discrepancy in Step 2 before generating the PDF statement (`acknowledge_discrepancies: true`).

5. **PDF Generator Architecture (`pdf_generator.py`)**:
   - Server-side generation using ReportLab `SimpleDocTemplate` and custom `TemplateCanvas`.
   - Top navy accent line and running footer (`Page X of Y`) drawn on all pages.
   - Native Unicode font registration: `NirmalaUI` (`Nirmala.ttc`), `Mangal` (`mangal.ttf`), or Linux Noto Devanagari.
   - Clean omission rules: when business details are omitted, the card formats cleanly without printing "Not Provided".
   - Generates strictly the finished financial statement for loan officers: excludes internal workflow, review, and AI terminology (e.g. "Pending Confirmation", "Human Reviewed", "Exact Match", "Handwritten Subtotal").

## Invariants

1. The vision LLM API key never leaves the backend.
2. No silent guessing: unreadable or unpriced values are `null` and flagged, never filled with a plausible guess.
3. High confidence entries are automatically accepted; genuine uncertainties must be resolved before PDF export.
4. Deleted transactions are completely excluded from totals and calculations.
5. All transactions remain editable and deletable, and edits immediately recalculate all totals.
6. Original AI extractions remain immutable; corrections are stored alongside them.
7. Customer-facing financial statements omit unavailable metadata cleanly and contain only finished financial records with zero internal review or AI terminology.
