# LedgerPilot

## Overview

LedgerPilot is a mobile-friendly web app that turns a photo of a
handwritten ledger page into a clean digital table and a downloadable
Excel report. It is built for small shopkeepers and micro-business
owners who record daily sales in handwritten notebooks (bahi-khatas)
and need a bank loan. Banks typically need digital records, so many of
these shopkeepers pay a data-entry person or accountant to type
everything in, or borrow informally. LedgerPilot removes that barrier
by reading the notebook for them, flagging anything it is unsure
about, and letting the shopkeeper review and fix it before exporting.

It prepares records for loan applications. It does not approve loans,
score credit, or connect to lenders.

Built for the Ctrl+V Hackathon (6 to 10 Nov 2026), whose mission is to
make opportunities easier to access by removing unnecessary barriers.

## Goals

1. Convert a photo of one handwritten ledger page into a structured
   table in a single upload
2. Measure and report field accuracy (date, description, amount, type)
   on at least 10 real ledger pages, stating the sample size
3. Never silently guess: every unreadable or rule-failing value is
   flagged for review instead of being filled in
4. Show a before and after: time to produce an Excel record from a page
   by hand versus with LedgerPilot, from a small timed test labelled as
   a small sample

## Core User Flow

1. The shopkeeper opens the app on a phone or laptop and uploads a
   photo of a handwritten ledger page
2. The app reads the handwriting and shows the transactions in a
   structured table beside the original photo
3. The app flags uncertain entries and possible errors, each with a
   short reason (for example "amount unreadable" or "total does not
   match")
4. The shopkeeper reviews the flagged cells and corrects them
5. The app shows a simple summary of the reviewed records (sales,
   expenses, and other supported summaries)
6. The shopkeeper downloads an Excel report of the reviewed records

## Features

### Capture

- Upload a photo of one handwritten ledger page
- Preview the photo before processing
- Resize and orient the image for extraction

### AI Extraction

- Uses Google Gemini vision API (originally intended model: `gemini-2.5-flash`;
  active fallback reported by Google API for new keys: `gemini-3.8-flash`)
- Transcribes handwritten Marathi text verbatim in Devanagari script
  without English translation
- Identifies and groups entries by date headers (e.g. `४/११/२०१९ सोमवार`
  mapped to ISO date `2019-11-04`)
- Reads individual transaction rows and extracts numerical amounts
- Captures explicitly written group subtotals and grand totals separately
  from individual entries
- Handles mixed Marathi and English script (e.g. salon service names)
- Unreadable or missing values are returned as `null` and flagged with reasons,
  never guessed or silently filled in

### Validation and Review

- Rule checks for missing amounts, totals that do not add up, odd
  dates, and unreadable rows
- Flagged cells are highlighted and marked with an icon or label, not
  color alone
- Original photo shown beside the table so each flag can be checked
- One-tap correction of any cell

### Reports

- Summary view of the reviewed records
- Excel export built from the reviewed rows
- Any row still unresolved is clearly marked in the export

## Scope

### In Scope

- Single-page photo upload and preview
- AI extraction of handwritten ledger rows
- Rule-based validation and flagging
- Manual correction of any cell
- Simple summary of reviewed records
- Excel export
- Mobile-first web app, with no install needed
- A measured accuracy test on real ledger pages with ground truth

### Out of Scope

- WhatsApp or Tally integration
- GST filing or GST data
- Credit scoring or lender integration
- Any claim that the product gets a loan approved
- User accounts and login
- Saving data across sessions (no database in the MVP)
- Multi-page batch uploads
- PDF reports (only if time permits after Excel)
- Native mobile app

## Success Criteria

1. A user can upload a ledger photo and see the extracted rows beside
   the original image
2. Every unreadable or rule-failing value is flagged with a reason and
   is never filled with a guess
3. A user can correct a flagged cell and the corrected value is what
   appears in the summary and export
4. A user can download an Excel file of the reviewed rows, with any
   unresolved row clearly marked
5. Field accuracy is measured on at least 10 real pages against
   hand-typed ground truth, and reported with the sample size
6. The full journey runs end to end on a phone browser in a rehearsed
   demo, with a recorded backup in case the live demo fails