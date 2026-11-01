# UI Context

## Theme

Light theme only, mobile-first. Small shopkeepers will use the application on phones in bright shop environments, so the design emphasizes:
- Warm off-white background (`--bg-base: #F7F5EF`) with clean white cards (`--bg-surface: #FFFFFF`).
- High-contrast text (`--text-primary: #1A2B24`, `--text-muted: #5B6B64`).
- Deep green primary accent (`--accent-primary: #0B5D45`).
- Generous tap targets (minimum 44px on all interactive controls).
- Plain, trustworthy, and non-judgmental tone.

## Typography

| Role | Font | Variable |
| :--- | :--- | :--- |
| UI text | Noto Sans, Noto Sans Devanagari, system-ui | `--font-sans` |
| Code/mono | ui-monospace, monospace | `--font-mono` |

- `Noto Sans Devanagari`, `Nirmala UI`, and `Mangal` are prioritized in the font stack so handwritten Marathi text renders accurately without clipping or character distortion.
- All monetary amounts, dates, and indices use `font-variant-numeric: tabular-nums` to ensure columnar alignment.

## Color Tokens

| Role | CSS Variable | Value | Usage |
| :--- | :--- | :--- | :--- |
| Page background | `--bg-base` | `#F7F5EF` | Global app backdrop |
| Surface | `--bg-surface` | `#FFFFFF` | Cards, modals, tables |
| Primary text | `--text-primary` | `#1A2B24` | Headings, entry amounts |
| Muted text | `--text-muted` | `#5B6B64` | Subtitles, labels, hints |
| Primary accent | `--accent-primary` | `#0B5D45` | Primary buttons, confirmed states |
| Secondary accent | `--accent-secondary` | `#F5B829` | Warnings, notice highlights |
| Border | `--border-default` | `#D9D6CB` | Dividers, card borders |
| Error / Danger | `--state-error` | `#B42318` | Validation errors, delete buttons |
| Success | `--state-success` | `#1A7F4B` | Totals match, confirmed badges |
| Flag (needs review) | `--state-flag` | `#B54708` | Amber warning badges |
| Flag background | `--state-flag-bg` | `#FFF4D6` | Amber alert card backgrounds |

## Review & Correction Workflow UI

### 1. Mandatory Review Gate
- Top bar and export card download buttons:
  - If any transaction remains unconfirmed: marked with `ShieldAlert` icon, displaying count of pending reviews (e.g. `Review to Export PDF (24)`).
  - If all transactions are confirmed: green `Download` icon, active state.
- **Review Gate Banner**:
  - Displays progress: `X of Y transactions require confirmation`.
  - Action button: `Review Next Pending Entry` (opens modal for first unreviewed row).
  - Quick action button: `Confirm Remaining Clean Entries` (confirms all unflagged, priced rows in one click).

### 2. Transaction Review Modal (`EntryReviewModal.tsx`)
- Desktop: centered modal with backdrop blur.
- Mobile: responsive bottom sheet (`max-width: 100%`, `border-radius: 16px 16px 0 0`).
- Fields:
  - Description input (Marathi / English) with hint "Required for sales statement".
  - Amount input with Indian Rupee symbol prefix (`₹`).
  - Toggle button: "Mark as Not Recorded" (switches between numeric input and unpriced badge).
  - Optional reviewer note input.
- Actions:
  - `Cancel` (escapes without state change).
  - `Delete` (opens delete confirmation).
  - `Confirm As-Is` (confirms existing AI values without modifications).
  - `Save & Confirm` (validates description and saves changes as `human_reviewed`).

### 3. Transaction Deletion with Confirmation
- Per-row `Trash2` icon button on every table row.
- **Confirmation Dialog**:
  - Highlights row number, Marathi description, and amount.
  - Explains: "This transaction will be completely excluded from all calculated totals and will not appear in the generated statement."
  - Explicit `Cancel` and red `Confirm Delete` buttons.
- On deletion, rows are sequentially re-indexed (`1, 2, 3...`) and all totals update reactively.

### 4. Arithmetic Discrepancy Acknowledgment Modal
- Triggered when user attempts PDF download while section handwritten subtotals differ from calculated entry sums.
- Displays each section's date, handwritten subtotal, calculated sum, and difference.
- Non-judgmental explanation of why both figures are preserved in Section 3 (Sales Reconciliation).
- Checkbox: "I acknowledge these arithmetic differences and confirm that the statement should reflect the ledger records as written."
- Primary button: "Acknowledge & Download PDF".

### 5. Transparent Status Pills
- `AI Extracted`: shown on initial extraction before user review.
- `Needs Review`: shown on rows with AI uncertainty flags or missing prices.
- `Human Reviewed`: green checkmark, reserved strictly for entries confirmed or edited by the user.
- Status counter: `{reviewedCount}/{totalCount} Reviewed • {unreviewedCount} Pending`.
