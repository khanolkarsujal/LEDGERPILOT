# AI Workflow Rules

## Approach

Build LedgerPilot MVP 1.0 incrementally using a spec-driven workflow.
Context files define what to build, how to build it, and the current
state of progress. Always implement against these specs. Do not infer
or invent behavior from scratch.

The MVP journey is:
photo of a handwritten ledger page -> AI extraction into a structured
table -> uncertain entries flagged -> shopkeeper reviews and corrects ->
downloadable Excel report.

Stack: React (frontend), Python + FastAPI (backend), a vision LLM API
for extraction, Pillow for image handling, Pandas + OpenPyXL for
reports. Results stay in memory until saving is explicitly needed.

## Scoping Rules

- Work on one feature unit at a time
- Prefer small, verifiable increments over large
  speculative changes
- Do not combine unrelated system boundaries in a
  single implementation step

## When to Split Work

Split an implementation step if it combines:

- UI changes and backend extraction or validation changes
- Extraction prompt changes and validation rule changes
- Multiple unrelated API routes (for example upload and export)
- Behavior not clearly defined in the context files
  (for example GST, lender integration, WhatsApp, Tally,
  credit scoring, or PDF reports)

If a change cannot be verified end to end quickly,
the scope is too broad. Split it.

## Handling Missing Requirements

- Do not invent product behavior not defined in the
  context files
- If a requirement is ambiguous, resolve it in the
  relevant context file before implementing
- If a requirement is missing, add it as an open question
  in `progress-tracker.md` before continuing

## Product Guardrails

These apply to every unit of work:

- Never silently guess. If a value is unreadable, missing, or uncertain,
  return it as null, flag it, and show it beside the original photo
  for the user to confirm or fix. Never invent dates, amounts, or types.
- Preserve original Marathi text verbatim in Devanagari script. Do not
  translate handwritten descriptions into English.
- Preserve handwritten recorded totals separately from calculated sums.
  Never silently correct a shopkeeper's arithmetic: if individual line
  items sum to a different figure than the written total (e.g. items sum
  to ₹400 but the written subtotal is ₹440), preserve the written ₹440
  intact and flag the difference as an arithmetic discrepancy for human
  review. Do not alter or overwrite either number.
- Do not rely on the model's self-reported confidence alone.
  Combine it with rule checks (missing amounts, totals that do
  not add up, odd dates, unreadable rows).
- Do not store ledger photos or extracted data by default.
  Ledgers contain customers' names and amounts, so be explicit
  about what is sent to the external API.
- Never invent accuracy numbers. Report field accuracy only from
  a measured test on real ledger pages, with the sample size stated.
  Do not describe preliminary runs as verified accuracy without a
  formally annotated ground-truth dataset.
- Do not claim the product gets a loan approved. It prepares
  records for loan applications.
- Excel export comes before PDF.

## Protected Files

Do not modify the following unless explicitly instructed:

- `tests/data/ground_truth/*` (hand-typed correct values used to
  measure accuracy; never edit these to make a test pass)
- `.env` and any file containing API keys or secrets
- Any generated UI library components (for example
  `frontend/src/components/ui/*`, if a component library is used)
- Any third-party library internals (`node_modules`, virtual
  environment folders)

## Keeping Docs in Sync

Update the relevant context file whenever implementation
changes:

- System architecture or boundaries
- Extraction schema (fields, formats) and validation rules
- Storage model decisions and privacy handling
- Code conventions or standards
- Feature scope

## Before Moving to the Next Unit

1. The current unit works end to end within its defined scope
2. No invariant defined in `architecture.md` was violated
3. `progress-tracker.md` reflects the completed work
4. The frontend build passes (`npm run build`) and backend tests
   pass (`pytest`)
5. If extraction or validation changed, accuracy was re-measured
   on the test set and recorded, with the sample size