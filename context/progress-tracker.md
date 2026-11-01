# Progress Tracker

Update this file after every meaningful implementation
change.

## Current Phase

- Milestone 1 Complete (Code secured in Git, Baseline benchmark established)
- Next: Milestone 2 (Image Upload & Preview integration / API) / Milestone 3 (Validation engine)
- Hackathon: Ctrl+V Hackathon, 6 to 10 Nov 2026 (Devpost)

## Current Goal

- Milestone 1 achieved: Empirical baseline extraction accuracy benchmark established (92.59% amounts, 100% dates and subtotals) on 3 real handwritten Marathi ledger photos.

## Completed

- Chose the problem: small shopkeepers record sales in handwritten
  notebooks, and banks need digital records for loan applications
- Chose the target user (one line): small shopkeepers who record
  sales in handwritten notebooks and need a bank loan
- Defined the MVP journey, tech stack, and six-step roadmap
- Wrote context files: `ai-workflow-rules.md`, `architecture.md`,
  `code-standards.md`, `progress-tracker.md`, `project-overview.md`,
  `ui-context.md`
- First version of the slide deck exists (needs fixes, see Session
  Notes)
- Step 1: Project setup complete
  - React + TypeScript (strict) with Vite initialized
  - Installed `lucide-react` for iconography
  - CSS custom properties design tokens and Noto Sans typography configured
  - Python 3.11 + FastAPI backend initialized with minimal `requirements.txt`
  - Health check endpoint `/health` and restricted CORS set up and verified
  - Scaffolding created for `tests/`, `tests/data/`, `.gitignore`, and `README.md`
  - Documented Vite and `lucide-react` adoption in `architecture.md`
  - Frontend production build (`npm run build`) verified clean
- Step 2: Image upload and preview complete
  - Mobile-friendly upload interface with step navigation (`StepHeader`)
  - Native file input supporting both mobile camera capture and gallery selection
  - File format validation (JPEG, JPG, PNG accepted; other formats rejected with clear message)
  - Enforced 10 MB maximum file size limit with specific size error feedback
  - Image preview with object URL generation and memory cleanup on remove/unmount
  - File details display (filename and formatted file size) with ready badge
  - Replace and remove options with accessible tap targets (>= 44px) and Lucide icons
  - Explicit empty, loading, error, and preview states
  - Passed TypeScript strict check, zero linter warnings, and verified production build
- Step 3 (Initial Experiment): Gemini extraction experiment complete
  - Installed official `google-genai>=1.0.0` in `backend/requirements.txt` and `.venv`
  - Configured `GEMINI_API_KEY` through gitignored `backend/.env` and updated `.env.example`
  - Created strict Pydantic schemas (`LedgerEntry`, `TransactionGroup`, `LedgerPageExtraction` in `backend/app/schemas/ledger.py`)
  - Implemented standalone extractor (`backend/app/extraction/gemini_extractor.py`) with Pillow orientation handling, low-temperature structured JSON generation, and UTF-8 console output
  - Verified API authentication with Google AI Studio
  - Tested on real handwritten ledger photo (`assests/img/ledger-page.png`):
    - Requested `gemini-2.5-flash`; API reported 404 (unavailable to new keys), and gracefully proceeded with `gemini-3.8-flash` as recommended by Google API
    - Group 1 (`४/११/२०१९ सोमवार`): Extracted 8 priced entries (₹90, ₹30×5, ₹80, ₹80) summing to ₹400, plus 1 unpriced service line ("peemnant smoothing") returned as null and flagged with reason. Handwritten recorded subtotal on the page was ₹440 (discrepancy of ₹40). System preserved the written ₹440 intact without altering numbers
    - Group 2 (`५/११/२०१९ मंगळवार`): Extracted 4 entries (₹30, ₹140, ₹30, ₹30) summing to ₹230. Recorded handwritten subtotal: ₹230 (exact arithmetic match)
    - Results recorded as a preliminary qualitative evaluation; no claims of verified accuracy are made until measured against formal ground truth
- Milestone 1: Secure Code and Establish Extraction Benchmark complete
  - Git repository initialized on branch `main` with strict `.gitignore` (safeguarding `.env`, credentials, virtual environments, node_modules)
  - Real ledger test photographs cleanly organized under `tests/data/real_ledgers/` while preserving originals in `assests/img/`
  - Manually transcribed and verified ground truth dataset established in `tests/data/ground_truth/ground_truth.json` (54 entries across 9 date groups across all 3 images)
  - Implemented automated benchmark evaluation suite (`tests/run_benchmark.py`)
  - Added robust Pydantic field validators for optional/unpriced amounts (`""` / `"-"` -> `None`) and exponential backoff retry for transient API spikes (503)
  - Baseline extraction completed on all 3 images using `gemini-3.8-flash` with raw JSON outputs archived in `tests/data/extraction_results/`
  - Empirical benchmark metrics achieved:
    - Date recognition and ISO conversion accuracy: 100.0% (9/9 date groups)
    - Recorded group subtotals capture: 100.0% (7/7 recorded subtotals captured)
    - Entry amount exact match: 92.59% (50/54 entries)
    - Unpriced / uncertain service line flagging: 100.0% (1/1 unpriced item flagged with `amount: null` and flag reason)
    - Arithmetic error detection capability demonstrated: successfully extracted handwritten recorded totals separately from item sums, exposing shopkeeper discrepancy (₹40 error in Image 1) and cursive ambiguity (Image 2) for downstream Python verification

## In Progress

- Model ID verification and test set ground-truth preparation

## Next Up

1. Verify exact Gemini model ID used (`gemini-2.5-flash` vs `gemini-3.8-flash`)
2. Create manually verified ground truth in `tests/data/ground_truth/`
3. Test extraction on the remaining two ledger images in `assests/img/`
4. Measure and record field extraction accuracy against ground truth (stating sample size)
5. Implement validation module to detect and flag arithmetic discrepancies (e.g. ₹40 difference in Group 1) without altering recorded values
6. Build FastAPI upload and extraction API endpoint (`backend/app/api/`)
7. Build frontend side-by-side review interface (ledger photo + editable table)
8. Generate financial summaries (sales, expenses, monthly surplus) and Excel exports

## Open Questions

- Does the Devpost page allow code written before 6 Nov? If not, do
  only steps 1 to 3 beforehand and start coding on the 6th
- Which vision model and API will we use, and what does it cost per
  page?
- Where do the test ledger photos come from, and do we have permission
  to use them?
- Which languages are in the test set (Marathi, Hindi, English, mixed)?
- Problem evidence is not yet verified. Find a source for each figure
  used in the deck. The 25 lakh crore credit gap is attributed to an
  RBI-constituted committee estimate reported in 2021, so confirm it
  and name the source and year
- Competitors to check: AccuRaik and Hisab Expert (unverified), plus
  Khatabook, OkCredit, and Vyapar, and lenders that use GST and bank
  data through the Account Aggregator framework
- Product name: LedgerPilot or Bridge? Use one name everywhere
- How will we demo: hosted app or local? Plan a recorded backup
- What exactly do we tell users about the third-party AI API, since
  ledger photos contain customers' names and amounts?
- Remaining context files: `project-overview.md` and `ui-context.md`
  (confirm they exist and agree with the files above)

## Architecture Decisions

- In-memory session storage, no database for the MVP: fastest to
  build, and nothing sensitive is stored by default
- No OpenCV at first: the vision model does the reading, so Pillow
  for resizing is enough
- Rule-based validation, not model confidence alone: a model's
  self-reported confidence is often wrong
- Review screen shows the original photo beside the extracted table,
  so a user can confirm or fix flagged cells in one tap
- Excel export before PDF
- TypeScript strict on the frontend; `Decimal` for money; ISO dates
- Mobile-first web app, so shopkeepers need no install
- No auth in the MVP
- Deferred: WhatsApp, Tally, GST, credit scoring, lender integration

## Session Notes

- The project started as Scholarship Bridge (MahaDBT) and switched to
  LedgerPilot. The MSME problem still needs the same evidence check
  the scholarship idea got
- Never invent accuracy numbers. The deck's testing slide still has
  "XX%" placeholders. Replace them with measured field accuracy and
  the sample size, or relabel the slide as a test plan
- The deck is missing a Differentiation, limitations, and roadmap
  slide, and a gap slide for AI extraction tools. It also has leftover
  template text (phone mockup, "2030", duplicate slide numbers).
  Fix it after the product works
- Do not claim the product gets loans approved. It prepares records
  for loan applications
- The riskiest part is handwriting accuracy on mixed-language pages.
  Test that first