# Architecture Context

## Stack

| Layer            | Technology                         | Role                                                                    |
| ---------------- | ---------------------------------- | ----------------------------------------------------------------------- |
| Frontend         | React + TypeScript (strict)        | Upload, side-by-side review (photo + table), cell correction, download  |
| Bundler          | Vite                               | Dev server and production build for the React frontend                  |
| Icons            | lucide-react                       | Stroke-based icons (upload, check, alert-triangle, pencil, download)    |
| Backend          | Python + FastAPI                   | HTTP API; orchestrates extraction, validation, and export               |
| AI extraction    | Google Gemini API via google-genai | Reads handwritten Marathi ledger photos using Gemini Flash              |
| Image handling   | Pillow                             | EXIF orientation normalization, resizing, and preparation               |
| Validation       | Python (plain rule functions)      | Flags missing values, bad totals, odd dates, unreadable rows            |
| Reports          | Pandas + OpenPyXL                  | Builds the Excel export from reviewed rows                              |
| Storage (MVP)    | In-memory, per session             | Holds the current page, rows, and flags until the session ends          |
| Auth             | None in MVP                        | Single-user demo; no accounts                                           |

Deferred (not in MVP): OpenCV, SQLite, PDF reports, WhatsApp, Tally,
GST, credit scoring, lender integration.

## System Boundaries

- `frontend/` — React UI only. Owns upload, photo preview, the review
  table, cell editing, and the download button. Never calls the vision
  LLM directly and never holds the API key.
- `backend/app/api/` — FastAPI routes. Thin handlers only: validate
  input, call a module, return the result. No extraction, validation,
  or report logic lives here.
- `backend/app/extraction/` — Image preparation via Pillow
  (`ImageOps.exif_transpose`), structured vision LLM invocation
  (`gemini-2.5-flash` with `gemini-3.8-flash` fallback via `google-genai`),
  and parsing into Pydantic models.
- `backend/app/schemas/` — Pydantic models (`LedgerEntry`,
  `TransactionGroup`, `LedgerPageExtraction`) that strictly enforce
  types, optionality, and flagging fields.
- `backend/app/validation/` — Rule-based checks that produce flags and
  reasons. Strictly separated from extraction: compares line-item sums
  against recorded totals without mutating either. Independent of the
  model's self-reported confidence.
- `backend/app/reports/` — Builds the Excel file from reviewed rows
  (Pandas + OpenPyXL).
- `tests/` — Backend tests, plus `tests/data/` holding test ledger
  photos and hand-typed ground truth used to measure accuracy.
- Repo root — Context files (`architecture.md`, `progress-tracker.md`,
  `ai-workflow-rules.md`, and the other context files).

## Separation of Extraction and Financial Validation

1. **Extraction (Pure Transcription):**
   - Transcribes only what is visibly recorded on the page.
   - Preserves original Marathi descriptions verbatim in Devanagari.
   - Captures handwritten line-item amounts and explicitly written
     group subtotals / grand totals as separate fields.
   - Does NOT perform arithmetic correction or calculate totals that
     are not written on the physical page.
   - Returns unreadable or missing values as `null` with explicit
     `uncertain_fields` and `flag_reason`.

2. **Validation (Financial & Arithmetic Rules):**
   - Runs deterministic Python rule functions over extracted groups.
   - Calculates the sum of line items within a group and compares it
     against the `recorded_group_total`.
   - When a discrepancy is detected (e.g. items sum to ₹400 but
     recorded total is ₹440), creates an arithmetic discrepancy flag.
   - Neither the line items nor the recorded total is altered or
     overwritten; the discrepancy is highlighted for human review.

## Storage Model

- **In-memory (per session)**: The current page image, extracted rows,
  flags, and the user's corrections. Cleared when the session ends.
  Nothing is written to a database in the MVP.
- **Generated files**: The Excel export is built on demand and streamed
  to the user. It is not stored on the server.
- **Disk (tests only)**: `tests/data/` holds sample ledger photos and
  ground truth for measuring accuracy. Use only photos with permission
  and with private details hidden.
- **Later (decision pending)**: SQLite, only if saving across sessions
  is needed. Record the decision in `progress-tracker.md` first.

## Core Data Shape

### Pydantic Extraction Schemas (`backend/app/schemas/ledger.py`)

- **`LedgerEntry`**:
  - `entry_index` (int): 1-based sequential position.
  - `raw_marathi_text` (str | null): Original Devanagari description.
  - `amount` (Decimal | null): Transaction value.
  - `entry_type` (income | expense | credit | debit | unknown):
    Explicit indicator only; default `unknown`.
  - `uncertain_fields` (list[str]): Names of ambiguous/smudged fields.
  - `flag_reason` (str | null): Explanation for review flags.

- **`TransactionGroup`**:
  - `group_id` (str): Unique section/date identifier.
  - `date_raw` (str | null): Raw handwritten date string.
  - `date_iso` (str | null): ISO 8601 date (YYYY-MM-DD) if unambiguous.
  - `entries` (list[LedgerEntry]): Line items in this block.
  - `recorded_group_total` (Decimal | null): Explicitly written subtotal.
  - `notes` (str | null): Layout observations (e.g. boxed total, column).

- **`LedgerPageExtraction`**:
  - `page_summary` (str): Overview of layout and handwriting clarity.
  - `groups` (list[TransactionGroup]): Sections on the page.
  - `recorded_page_total` (Decimal | null): Page-level total if written.
  - `unreadable_sections_found` (bool): True if illegible ink marks exist.

Unreadable or uncertain values are `null` and flagged. They are never
filled with a plausible guess.

## Auth and Access Model

- No sign-in in the MVP. The demo is a single-user session.
- Ownership: the data belongs to the current session only. Nothing is
  shared between sessions or users.
- Access control: the vision LLM API key lives only in backend
  environment variables (`.env`). The backend restricts cross-origin
  requests to the frontend's origin.
- If accounts are added later, define ownership and access rules here
  before building them.

## Invariants

1. The vision LLM API key never leaves the backend. The frontend never
   calls the LLM directly.
2. No silent guessing. An unreadable or uncertain value is returned as
   `null` with a flag, never as a made-up value.
3. Validation is rule-based code. The model's self-reported confidence
   alone never clears a flag.
4. Export uses only the user's reviewed data. Any row still flagged is
   clearly marked as unresolved in the export.
5. Ledger photos and extracted data are not persisted or logged by
   default.
6. Route handlers stay thin and run no long-lived background work.
   Extraction, validation, and reports live in their own modules.
7. Accuracy figures come only from tests against `tests/data/` ground
   truth, reported with the sample size.