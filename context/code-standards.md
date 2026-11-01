# Code Standards

## General

- Keep modules small and single-purpose
- Fix root causes, do not layer workarounds
- Do not mix unrelated concerns in one component, route, or module
  (for example extraction logic inside a route handler)
- Never silently guess. Unreadable or uncertain values are `null`
  and flagged, never filled with a plausible value
- Prefer plain, readable code over clever code. A teammate should
  understand any file in a minute
- Do not add features, libraries, or abstractions that are not in
  the context files

## TypeScript

- Strict mode is required throughout the frontend
- Avoid `any`. Use explicit interfaces or narrowly scoped types
- Define the transaction row type once (date, description, amount,
  type, status, flag_reason, source_row) and reuse it everywhere
- Validate unknown external input, including API responses, at the
  boundary before trusting it
- Handle loading, empty, and error states explicitly in every view

## React

- Use function components and hooks
- Keep components small. Split the upload view, photo preview,
  review table, and download action into separate components
- Keep API calls in `frontend/src/api/`, not inside components
- Keep server data and UI state separate. Do not duplicate extracted
  rows across several state stores
- Edits to a cell update one source of truth (the reviewed rows)
- The frontend never calls the vision LLM and never holds the API key
- Design mobile-first. Shopkeepers will use phones, so use large tap
  targets and keep the review screen usable at narrow widths
- Support Unicode text (Marathi, Hindi, English mixed) everywhere.
  Never assume Latin-only characters

## Python (backend)

- Use type hints on all functions
- Use Pydantic models for request and response shapes
- Keep functions pure where possible. Validation rules take rows in
  and return flags out, with no side effects
- Represent money with `Decimal` (or integer paise), never floats
- Store dates as ISO 8601 (`YYYY-MM-DD`). If a date cannot be read
  with confidence, return `null` and flag it
- Handle vision LLM failures explicitly: set a timeout, catch errors,
  and return a clear message instead of a partial or made-up result
- Keep secrets in environment variables. Never hardcode API keys

## Styling

- Use CSS custom property tokens. No hardcoded hex values
- Follow the spacing and border radius scale defined in `ui-context.md`
- Flagged cells must be visually distinct, and the cue must not rely
  on color alone (add an icon or label)
- Keep text readable: sufficient size and contrast, no tiny gray text

## API Routes

- Validate and parse request input before any logic runs
- Check uploads: allowed image types only, a maximum file size, and a
  clear error for anything else
- Keep handlers thin: parse input, call one module, return the result
- Return consistent response shapes, for example
  `{ "rows": [...], "flags": [...] }` on success and
  `{ "error": { "code": "...", "message": "..." } }` on failure
- Never log image contents or extracted ledger data
- No auth in the MVP. If accounts are added later, enforce auth and
  ownership before any mutation and update `architecture.md` first

## Data and Storage

- Session data (current page, rows, flags, corrections) lives in
  memory for the MVP
- Do not persist ledger photos or extracted data by default
- Generate the Excel export on demand and stream it. Do not store it
- Test photos and ground truth live in `tests/data/` only, with
  private details hidden
- If a database is added later, record the decision in
  `progress-tracker.md` and update `architecture.md` before building

## File Organization

- `frontend/src/components/` — React components (upload, preview,
  review table, download)
- `frontend/src/api/` — Typed calls to the backend
- `frontend/src/types/` — Shared TypeScript types, including the
  transaction row
- `backend/app/api/` — FastAPI routes (thin handlers only)
- `backend/app/extraction/` — Image preparation and vision LLM calls
- `backend/app/validation/` — Rule-based checks and flag reasons
- `backend/app/reports/` — Excel export
- `backend/app/schemas/` — Pydantic models
- `tests/` — Backend tests
- `tests/data/` — Sample ledger photos and hand-typed ground truth
  (protected; do not edit to make a test pass)