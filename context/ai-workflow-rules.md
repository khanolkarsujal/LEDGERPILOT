# AI Workflow Rules

## Approach

Build LedgerPilot MVP 1.0 incrementally using a spec-driven workflow. Context files define what to build, how to build it, and the current state of progress. Always implement against these specs. Do not infer or invent behavior from scratch.

The core journey is:
photo of handwritten ledger page -> asynchronous background AI extraction -> split-screen review workspace -> mandatory human review & confirmation of every transaction -> non-destructive editing & deletion with dynamic recalculation -> discrepancy acknowledgment -> downloadable accountant-prepared Business Sales Statement PDF.

## Scoping Rules

- Work on one feature unit at a time.
- Prefer small, verifiable increments over large speculative changes.
- Do not combine unrelated system boundaries in a single implementation step.
- Update relevant context files after every meaningful change.

## Product Guardrails (Non-Negotiable)

These apply to every unit of work:

- **Never Silently Guess**: If a value is unreadable, missing, or uncertain, return it as `null`, flag it, and show it beside the original photo for the user to confirm or fix. Never invent dates, amounts, or transaction types.
- **Intelligent Auto-Verification**: Automatically accept clean entries with valid descriptions, positive amounts, and zero uncertainty flags (`auto_accepted`). Only flag genuinely ambiguous, missing, or suspicious values for human review.
- **Immediate Dynamic Recalculation**: Whenever an entry is edited or deleted, immediately recalculate all affected daily totals and overall totals. Completely exclude deleted entries everywhere, including the final PDF.
- **Preserve Missing Amounts**: Never convert missing amounts into ₹0. An unpriced entry must remain `null` or visibly "Not Recorded".
- **Preserve Marathi Text**: Transcribe handwritten Marathi text verbatim in Devanagari script. Do not translate descriptions into English.
- **Preserve Recorded Totals Separately**: Never silently correct a shopkeeper's arithmetic: if individual line items sum to a different figure than the written total, preserve the written figure intact and flag the difference as an arithmetic discrepancy for human review in Step 2.
- **Targeted Review Gate**: PDF statement export must be blocked if any unresolved flagged entries remain. Direct API calls must not bypass this gate.
- **Business Details Collection**: Collect business name and address before generating the PDF if missing; offer a "Remember business details" option via `localStorage` without requiring a database.
- **Clean Document Formatting**:
  - Customer-facing PDF statements must strictly present the finalized financial records for loan documentation.
  - Never print internal AI or review terms ("AI Extracted", "Gemini", "LLM", "Prompt", "Pending Confirmation", "Human Reviewed", "Exact Match", "Handwritten Subtotal") in exported documents.
  - If business metadata (name/address) is not provided, omit the fields cleanly; never print "Not Provided", "N/A", or placeholder text.
  - Never claim statements are audited, certified, or guaranteed to be accepted by lenders.
- **No Token Waste**: Do NOT call Gemini API or rerun image extraction when working on frontend, validation, tests, or PDF reporting. Use existing extraction results and local calculations.

## Protected Files

Do not modify the following unless explicitly instructed:

- `tests/data/ground_truth/*` (hand-typed ground truth used to measure accuracy).
- `.env` and any file containing API keys or credentials.
- Third-party library internals (`node_modules`, virtual environment folders).

## Verification Before Milestone Completion

1. The unit works end to end within its defined scope.
2. No architectural invariant was violated.
3. Relevant automated tests pass (`pytest` for backend, `npm run build` for frontend).
4. All six context files are synchronized with actual implementation state.
5. Changes are committed with clear, logical messages and pushed to the remote repository.
