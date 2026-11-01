# Code Standards

## General

- Keep modules small, focused, and single-purpose.
- Fix root causes; never layer workarounds.
- Do not mix unrelated concerns in one component, route, or module.
- Never silently guess. Unreadable or uncertain values are `null` and flagged, never filled with a plausible value.
- Prefer plain, readable code over clever abstractions.
- Preserve all existing comments and docstrings that are unrelated to your code changes.

## Financial Integrity Standards (Non-Negotiable)

1. **No Invented Data**: Never invent, guess, or synthesize transaction amounts or dates.
2. **Preserve Missing Values**: Never convert missing, unpriced, or unrecorded amounts into ₹0. An unpriced entry must remain `null` or visibly "Not Recorded".
3. **No Forcing Totals**: Never modify a line-item amount or subtotal to force arithmetic agreement.
4. **Separation of Extraction and Human Review**: Store raw AI extractions (`raw_marathi_text`, `amount`, `uncertain_fields`) in immutable fields; store human review decisions (`corrected_marathi_text`, `corrected_amount`, `review_status`, `reviewed_at`) separately.
5. **Separation of Written and Calculated Totals**: Always calculate line-item sums deterministically from valid entries; never overwrite or alter handwritten subtotals.
6. **No Misleading Trust Labels**: Never label raw AI extractions as "Verified" or "Human reviewed". Only mark an entry as "Human reviewed" after explicit user confirmation.
7. **Transparent Discrepancy Reporting**: Always report differences between handwritten subtotals and calculated sums openly; require explicit user acknowledgment before generating formal statements.
8. **Document Generation Rules**:
   - Customer-facing PDF statements must NOT contain internal AI/LLM terms ("AI Extracted", "Gemini", "LLM", "Prompt", "machine learning").
   - Omit unavailable metadata cleanly: if business name or address is not provided, omit the fields; never print "Not Provided", "N/A", or awkward placeholders.
   - Never describe the document as audited, certified, or guaranteed to be accepted by a lender.

## Mandatory Review Gate Enforcement

- The backend PDF endpoint (`POST /api/reports/pdf`) must validate that 100% of remaining transactions have `review_status == 'human_reviewed'`. Direct API requests must be rejected with HTTP 422 (`review_gate_failed`).
- The frontend must disable statement downloads and display remaining unreviewed counts until all transactions are reviewed or deleted.
- If discrepancies exist between written subtotals and calculated sums, `acknowledge_discrepancies: true` must be validated before statement generation.

## Deletion and Re-Indexing Standards

- Deleting an entry must remove it from the transaction array.
- Remaining entries must be sequentially re-indexed (`1, 2, 3...`) to maintain formal accounting register integrity.
- All date-group sums, page sums, discrepancy calculations, and review counts must update immediately upon deletion.

## TypeScript & React

- Strict mode is required throughout the frontend.
- Avoid `any`. Use explicit interfaces or narrowly scoped types.
- Define transaction types once in `frontend/src/types/` and reuse everywhere.
- Design mobile-first with minimum 44px tap targets.
- Support Unicode text (Marathi, Hindi, English mixed) everywhere.

## Python (Backend)

- Use type hints on all functions and methods.
- Use Pydantic models for request and response validation.
- Represent monetary amounts with `Decimal` (or float/int in JSON serialization); never rely on floating-point arithmetic for financial calculations.
- Store dates as ISO 8601 (`YYYY-MM-DD`). If a date is ambiguous, return `null` and flag it.
- Keep secrets in environment variables (`.env`). Never hardcode API keys.

## API Routes

- Route handlers must remain thin: validate input, call domain modules, return responses.
- Check uploads: allowed image MIME types (JPEG, PNG), 10 MB maximum size limit.
- Return consistent error shapes (`{"detail": {"error": "...", "message": "..."}}`).
- Never log image contents or customer personal data.
