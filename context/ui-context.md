# UI Context

## Theme

Light theme only, mobile-first. Shopkeepers will mostly use a phone in
a bright shop, so the design favors a warm off-white background, high
contrast text, large tap targets, and calm deep-green accents (matching
the deck's green and amber palette). The interface is plain and
trustworthy, not flashy.

The key screen is the review screen: the original ledger photo beside
the extracted table, with flagged cells that are impossible to miss.

Principles:
- One main action per screen
- Every state is clear without relying on color alone
- Text is readable at arm's length (16px minimum body text)
- Tap targets are at least 44px
- The UI text is English for the MVP. Ledger content can be any script
  (Marathi, Hindi, English, mixed)

## Colors

All components must use these tokens as CSS custom properties. No
hardcoded hex values.

| Role                | CSS Variable        | Value     |
| ------------------- | ------------------- | --------- |
| Page background     | `--bg-base`         | `#F7F5EF` |
| Surface             | `--bg-surface`      | `#FFFFFF` |
| Primary text        | `--text-primary`    | `#1A2B24` |
| Muted text          | `--text-muted`      | `#5B6B64` |
| Primary accent      | `--accent-primary`  | `#0B5D45` |
| Secondary accent    | `--accent-secondary`| `#F5B829` |
| Border              | `--border-default`  | `#D9D6CB` |
| Error               | `--state-error`     | `#B42318` |
| Success             | `--state-success`   | `#1A7F4B` |
| Flag (needs review) | `--state-flag`      | `#B54708` |
| Flag background     | `--state-flag-bg`   | `#FFF4D6` |

`--accent-secondary`, `--state-flag`, and `--state-flag-bg` are additions
to the template. Check text and background pairs with a contrast
checker before finalizing.

## Typography

| Role      | Font                                      | Variable      |
| --------- | ----------------------------------------- | ------------- |
| UI text   | Noto Sans, Noto Sans Devanagari, system-ui | `--font-sans` |
| Code/mono | ui-monospace, monospace                   | `--font-mono` |

- Noto Sans Devanagari is required so Marathi and Hindi text render
  correctly. Always include it in the font stack
- Amounts and dates use `font-variant-numeric: tabular-nums` so
  columns line up
- Body text 16px minimum; table cells 16px; headings scale up from there

## Border Radius

| Context           | Token         | Value  |
| ----------------- | ------------- | ------ |
| Inline / small UI | `--radius-sm` | `6px`  |
| Cards / panels    | `--radius-md` | `12px` |
| Modals / sheets   | `--radius-lg` | `16px` |

The project uses plain CSS with custom properties rather than Tailwind,
so radius is defined as tokens, not utility classes.

## Component Library

No component library. Use plain React components styled with CSS
custom properties. Prefer native HTML elements (`<button>`, `<input>`,
`<table>`) for accessibility. Core components: Button, Card, Badge,
Table, EditSheet, Toast. If a library is added later, record the
decision in `architecture.md` first.

For photo capture, use a native file input
(`accept="image/*"` with the camera option on phones), not a custom
camera component.

## Layout Patterns

- Screens: Upload -> Review -> Export, shown as a simple step header
- Phone (default): single column. Photo preview on top (tap to zoom),
  table below
- Desktop (about 900px and up): review screen is a side-by-side split,
  photo on the left and table on the right
- Review table: flagged rows are listed first, each with an icon, a
  short reason, and a visible edit action
- Tapping a flagged row highlights the matching area of the photo
  (using `source_row`)
- Cell editing: a bottom sheet on phones and a centered panel on
  desktop, with the original value and the photo area visible
- Sticky bottom action bar with one primary button ("Download Excel")
- Top bar: app name only, with a bottom border
- Loading, empty, and error states are designed for every screen

### Row states

Every state uses an icon and a text label as well as color.

| State      | Color token       | Icon          | Label        |
| ---------- | ----------------- | ------------- | ------------ |
| OK         | `--state-success` | check         | OK           |
| Flagged    | `--state-flag`    | alert-triangle| Check this   |
| Corrected  | `--accent-primary`| pencil        | Fixed        |
| Unresolved | `--state-error`   | circle-alert  | Unresolved   |

## Icons

Lucide React. Stroke-based icons only. Sizes: 16px inline, 20px in
buttons, 24px for primary actions. Core icons: upload, camera,
check, alert-triangle, pencil, download. Add `lucide-react` to the
stack in `architecture.md` when this file is adopted.