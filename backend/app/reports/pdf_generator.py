"""
Business Sales Statement PDF Generator.

Produces a conventional accountant-prepared Business Sales Statement and
Daily Sales Register suitable for small business loan documentation and
supporting financial records.

Design & Architectural Invariants:
- Generates a formal, accountant-style financial document (white background,
  dark charcoal/navy headings, clean thin borders, consistent margins).
- Strictly distinguishes between dynamically calculated amounts and handwritten
  recorded totals/subtotals.
- Uses neutral financial terminology: 'Recorded', 'Confirmed',
  'Pending Confirmation', 'Amount Not Recorded', 'Calculated Daily Total'.
- Never mentions AI or internal extraction technology in customer-facing PDF.
- Preserves Marathi Devanagari descriptions verbatim using Nirmala UI font.
- Never converts missing amounts to 0; marks them as 'Not Recorded' and excludes
  them from arithmetic sums.
- Preserves separate handwritten sections even if they share the same date.
- Shows transparent sales reconciliation with discrepancies clearly stated.
"""

import io
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.ledger import LedgerEntry, LedgerPageExtraction, TransactionGroup

# -----------------------------------------------------------------------------
# Font Registration (Native Devanagari & Rupee Symbol Support)
# -----------------------------------------------------------------------------
FONT_REGULAR = "NirmalaUI"
FONT_BOLD = "NirmalaUI-Bold"
_FONTS_INITIALIZED = False


def _init_fonts() -> Tuple[str, str]:
    """Registers Nirmala UI for Devanagari Marathi text; falls back gracefully."""
    global _FONTS_INITIALIZED, FONT_REGULAR, FONT_BOLD
    if _FONTS_INITIALIZED:
        return FONT_REGULAR, FONT_BOLD

    candidate_ttc = r"C:\Windows\Fonts\Nirmala.ttc"
    candidate_mangal = r"C:\Windows\Fonts\mangal.ttf"
    candidate_linux = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"

    try:
        if os.path.exists(candidate_ttc):
            pdfmetrics.registerFont(TTFont("NirmalaUI", candidate_ttc, subfontIndex=0))
            pdfmetrics.registerFont(TTFont("NirmalaUI-Bold", candidate_ttc, subfontIndex=1))
            FONT_REGULAR = "NirmalaUI"
            FONT_BOLD = "NirmalaUI-Bold"
            _FONTS_INITIALIZED = True
            return FONT_REGULAR, FONT_BOLD
        elif os.path.exists(candidate_mangal):
            pdfmetrics.registerFont(TTFont("Mangal", candidate_mangal))
            FONT_REGULAR = "Mangal"
            FONT_BOLD = "Mangal"
            _FONTS_INITIALIZED = True
            return FONT_REGULAR, FONT_BOLD
        elif os.path.exists(candidate_linux):
            pdfmetrics.registerFont(TTFont("NotoDeva", candidate_linux))
            FONT_REGULAR = "NotoDeva"
            FONT_BOLD = "NotoDeva"
            _FONTS_INITIALIZED = True
            return FONT_REGULAR, FONT_BOLD
    except Exception as e:
        print(f"[!] PDF Font registration warning: {e}. Falling back to standard fonts.")

    FONT_REGULAR = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    _FONTS_INITIALIZED = True
    return FONT_REGULAR, FONT_BOLD


# -----------------------------------------------------------------------------
# Financial Calculation Helpers (Deterministic Parity)
# -----------------------------------------------------------------------------
def get_effective_description(entry: LedgerEntry) -> str:
    """Returns human-corrected description if reviewed; otherwise raw recorded text."""
    if entry.review_status == "human_reviewed" and entry.corrected_marathi_text is not None:
        return entry.corrected_marathi_text
    return entry.raw_marathi_text or "[Description Not Recorded]"


def get_effective_amount(entry: LedgerEntry) -> Optional[Decimal]:
    """Returns human-corrected amount if reviewed; otherwise raw recorded amount."""
    if entry.review_status == "human_reviewed" and entry.corrected_amount is not None:
        return Decimal(str(entry.corrected_amount))
    if entry.amount is not None:
        try:
            return Decimal(str(entry.amount))
        except Exception:
            return None
    return None


def is_entry_unpriced(entry: LedgerEntry) -> bool:
    """
    Checks if entry has no recorded price.
    Guarantees unpriced items remain null and are excluded from arithmetic.
    """
    if entry.review_status == "human_reviewed" and entry.corrected_amount is not None:
        return False
    if entry.review_status == "human_reviewed" and entry.corrected_amount is None:
        return True

    if entry.amount is None:
        return True
    s = str(entry.amount).strip().lower()
    if s in ("", "null", "none", "-", "—", "n/a", "not recorded"):
        return True
    if entry.flag_reason:
        r = entry.flag_reason.lower()
        if (
            any(
                kw in r
                for kw in (
                    "no amount",
                    "unpriced",
                    "not recorded",
                    "dash recorded",
                    "amount not explicitly written",
                )
            )
            and "amount" in (entry.uncertain_fields or [])
        ):
            return True
    return False


def is_entry_pending_confirmation(entry: LedgerEntry) -> bool:
    """Identifies entries that require human confirmation or review."""
    if entry.review_status == "human_reviewed":
        return False
    if entry.uncertain_fields or entry.flag_reason or is_entry_unpriced(entry):
        return True
    return False


def calculate_group_sum(group: TransactionGroup) -> Decimal:
    """Computes arithmetic sum of valid priced line items in a ledger section."""
    total = Decimal("0")
    for e in group.entries:
        if not is_entry_unpriced(e):
            amt = get_effective_amount(e)
            if amt is not None:
                total += amt
    return total


def format_inr(amount: Optional[Decimal]) -> str:
    """Formats a decimal amount in Indian Rupees format (e.g. ₹2,040.00)."""
    if amount is None:
        return "Not Recorded"
    return f"₹{amount:,.2f}"


# -----------------------------------------------------------------------------
# Numbered Canvas for Running Headers & Footers
# -----------------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas recording total page count and rendering formal headers/footers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[dict] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        font_reg, _ = _init_fonts()
        self.setFont(font_reg, 8)
        self.setFillColor(colors.HexColor("#475569"))

        # Running Top Header (pages 2+)
        if self._pageNumber > 1:
            self.drawString(36, 808, "BUSINESS SALES STATEMENT")
            self.drawRightString(559, 808, "Supporting Financial Records — Daily Sales Register")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 802, 559, 802)

        # Running Bottom Footer (all pages)
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(559, 22, page_str)
        self.drawString(
            36,
            22,
            "Confidential • Supporting Financial Records • Not an Audited Statement",
        )
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 32, 559, 32)
        self.restoreState()


# -----------------------------------------------------------------------------
# Main PDF Document Generator
# -----------------------------------------------------------------------------
def generate_pdf_report(
    extraction: LedgerPageExtraction,
    business_name: Optional[str] = None,
    business_address: Optional[str] = None,
    nature_of_business: Optional[str] = None,
    statement_reference: Optional[str] = None,
) -> bytes:
    """
    Generates a formal, conventional Business Sales Statement PDF.

    Args:
        extraction: Validated LedgerPageExtraction containing date groups and entries.
        business_name: Optional business or trade name.
        business_address: Optional business physical address.
        nature_of_business: Optional nature/category of business.
        statement_reference: Optional statement reference number.

    Returns:
        bytes: Raw PDF document bytes.
    """
    font_reg, font_bold = _init_fonts()

    # Dynamic metrics calculation
    all_entries = [e for g in extraction.groups for e in g.entries]
    total_entries_count = len(all_entries)
    unpriced_count = sum(1 for e in all_entries if is_entry_unpriced(e))
    priced_count = total_entries_count - unpriced_count
    confirmed_count = sum(1 for e in all_entries if e.review_status == "human_reviewed")
    pending_count = sum(1 for e in all_entries if is_entry_pending_confirmation(e))

    # Total calculated sales (sum of all priced entries across groups)
    total_calculated_sales = sum(
        (calculate_group_sum(g) for g in extraction.groups), Decimal("0")
    )

    # Sum of recorded daily subtotals
    groups_with_subtotal = [
        g
        for g in extraction.groups
        if g.recorded_group_total is not None
        and str(g.recorded_group_total).strip().lower() not in ("", "null", "none", "-")
    ]
    sum_recorded_subtotals: Optional[Decimal] = None
    if groups_with_subtotal:
        sum_recorded_subtotals = sum(
            (Decimal(str(g.recorded_group_total)) for g in groups_with_subtotal),
            Decimal("0"),
        )

    # Written page grand total (only if present in source)
    written_page_total: Optional[Decimal] = None
    if (
        extraction.recorded_page_total is not None
        and str(extraction.recorded_page_total).strip().lower() not in ("", "null", "none", "-")
    ):
        try:
            written_page_total = Decimal(str(extraction.recorded_page_total))
        except Exception:
            written_page_total = None

    # Date range deduction
    date_strings: List[str] = []
    for g in extraction.groups:
        if g.date_raw:
            clean_date = g.date_raw.replace("\n", " ").strip()
            date_strings.append(clean_date)
        elif g.date_iso:
            date_strings.append(g.date_iso)

    if len(date_strings) > 1:
        statement_period_str = f"{date_strings[0]} to {date_strings[-1]}"
    elif len(date_strings) == 1:
        statement_period_str = date_strings[0]
    else:
        statement_period_str = "Not Specified on Records"

    prep_date_str = datetime.now().strftime("%d %B %Y")

    # Document Setup (A4: 595.27 x 841.89 points, margins 36 pt)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=42,
    )

    styles = getSampleStyleSheet()

    # Style Definitions (Formal accountant typography)
    style_doc_title = ParagraphStyle(
        "DocTitle",
        fontName=font_bold,
        fontSize=17,
        leading=21,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=1,
    )
    style_doc_subtitle = ParagraphStyle(
        "DocSubtitle",
        fontName=font_reg,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#475569"),
        spaceAfter=6,
    )
    style_section_heading = ParagraphStyle(
        "SectionHeading",
        fontName=font_bold,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=8,
        spaceAfter=3,
    )
    style_section_sub = ParagraphStyle(
        "SectionSub",
        fontName=font_bold,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=5,
        spaceAfter=2,
    )
    style_table_header = ParagraphStyle(
        "TableHeader",
        fontName=font_bold,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#FFFFFF"),
        alignment=0,
    )
    style_table_header_right = ParagraphStyle(
        "TableHeaderRight",
        fontName=font_bold,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#FFFFFF"),
        alignment=2,
    )
    style_cell_reg = ParagraphStyle(
        "CellReg",
        fontName=font_reg,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#1E293B"),
    )
    style_cell_bold = ParagraphStyle(
        "CellBold",
        fontName=font_bold,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#0F172A"),
    )
    style_cell_muted = ParagraphStyle(
        "CellMuted",
        fontName=font_reg,
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#64748B"),
    )
    style_cell_right = ParagraphStyle(
        "CellRight",
        fontName=font_reg,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#0F172A"),
        alignment=2,
    )
    style_cell_right_bold = ParagraphStyle(
        "CellRightBold",
        fontName=font_bold,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#0F172A"),
        alignment=2,
    )
    style_disclaimer = ParagraphStyle(
        "DisclaimerText",
        fontName=font_reg,
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#334155"),
    )

    story: List[Any] = []

    # =========================================================================
    # SECTION A: Formal Document Header
    # =========================================================================
    effective_business_name = business_name.strip() if business_name and business_name.strip() else "Not Provided"

    header_data = [
        [
            Paragraph("<b>BUSINESS SALES STATEMENT</b>", style_doc_title),
            Paragraph(f"<b>Date Prepared:</b> {prep_date_str}", style_cell_right),
        ],
        [
            Paragraph("Supporting Financial Records — Daily Sales Register", style_doc_subtitle),
            Paragraph(
                f"<b>Statement Ref:</b> {statement_reference.strip()}" if statement_reference and statement_reference.strip() else "",
                style_cell_right_bold,
            ),
        ],
    ]
    t_header = Table(header_data, colWidths=[363.27, 160])
    t_header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(t_header)
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0F172A"), spaceBefore=2, spaceAfter=8))

    # =========================================================================
    # SECTION B: Business Information Table
    # =========================================================================
    story.append(Paragraph("1. BUSINESS & STATEMENT INFORMATION", style_section_heading))

    biz_rows = [
        [Paragraph("Business / Trade Name", style_cell_bold), Paragraph(effective_business_name, style_cell_reg)],
        [
            Paragraph("Business Address", style_cell_bold),
            Paragraph(business_address.strip() if business_address and business_address.strip() else "Not Provided", style_cell_reg),
        ],
    ]
    if nature_of_business and nature_of_business.strip():
        biz_rows.append([Paragraph("Nature of Business", style_cell_bold), Paragraph(nature_of_business.strip(), style_cell_reg)])

    biz_rows.extend(
        [
            [Paragraph("Statement Period", style_cell_bold), Paragraph(statement_period_str, style_cell_reg)],
            [Paragraph("Currency", style_cell_bold), Paragraph("Indian Rupees (INR / ₹)", style_cell_reg)],
            [Paragraph("Documentation Status", style_cell_bold), Paragraph("Supporting Ledger Records (Subject to Loan Review)", style_cell_reg)],
        ]
    )

    t_biz = Table(biz_rows, colWidths=[150, 373.27])
    t_biz.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
                ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#FFFFFF")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(t_biz)
    story.append(Spacer(1, 6))

    # =========================================================================
    # SECTION C: Daily Sales Register (Main Section)
    # =========================================================================
    story.append(Paragraph("2. DAILY SALES REGISTER", style_section_heading))
    story.append(
        Paragraph(
            "Itemized daily transaction records organized chronologically by ledger section. "
            "Amounts missing on physical ledger are reported as 'Not Recorded' and excluded from daily totals.",
            style_cell_muted,
        )
    )
    story.append(Spacer(1, 4))

    # Preserve separate handwritten sections even if they share the same date
    for s_idx, group in enumerate(extraction.groups):
        section_num = s_idx + 1
        date_display = group.date_raw.replace("\n", " ").strip() if group.date_raw else (group.date_iso or f"Section {section_num}")
        iso_addon = f" (ISO: {group.date_iso})" if group.date_iso and group.date_raw else ""
        section_title_text = f"Section {section_num} — Date: {date_display}{iso_addon}"

        group_elements: List[Any] = []
        group_elements.append(Paragraph(section_title_text, style_section_sub))

        # Table Header
        table_data: List[List[Any]] = [
            [
                Paragraph("Date", style_table_header),
                Paragraph("Sr. No.", style_table_header),
                Paragraph("Particulars / Description", style_table_header),
                Paragraph("Amount (₹)", style_table_header_right),
            ]
        ]

        # Populate transaction rows
        for e_idx, entry in enumerate(group.entries):
            sr_no = str(entry.entry_index if entry.entry_index is not None else e_idx + 1)
            eff_desc = get_effective_description(entry)
            unpriced = is_entry_unpriced(entry)
            amt_val = get_effective_amount(entry)

            # Build description paragraph with status notes if applicable
            desc_lines = [f"<font name='{font_reg}' size='8.5'>{eff_desc}</font>"]

            if entry.review_status == "human_reviewed":
                desc_lines.append("<font size='7' color='#0B5D45'><b>[Confirmed]</b></font>")
                if entry.corrected_marathi_text and entry.raw_marathi_text and entry.corrected_marathi_text != entry.raw_marathi_text:
                    desc_lines.append(f"<font size='7' color='#64748B'><i>(Recorded: {entry.raw_marathi_text})</i></font>")
                if entry.review_note:
                    desc_lines.append(f"<font size='7' color='#64748B'><i>(Note: {entry.review_note})</i></font>")
            elif is_entry_pending_confirmation(entry):
                reason_note = f" — {entry.flag_reason}" if entry.flag_reason else ""
                desc_lines.append(f"<font size='7' color='#B45309'><b>[Pending Confirmation]</b></font><font size='7' color='#64748B'><i>{reason_note}</i></font>")

            desc_cell = Paragraph(" ".join(desc_lines), style_cell_reg)

            # Amount formatting
            if unpriced:
                amt_cell = Paragraph("<i>Not Recorded</i>", style_cell_right)
            else:
                amt_cell = Paragraph(format_inr(amt_val), style_cell_right)

            # Row date string (shown cleanly)
            row_date = group.date_iso or date_display

            table_data.append([
                Paragraph(row_date, style_cell_reg),
                Paragraph(sr_no, style_cell_reg),
                desc_cell,
                amt_cell,
            ])

        # Date Section Subtotal calculations
        section_calc_sum = calculate_group_sum(group)
        section_entries_count = len(group.entries)
        section_unpriced_count = sum(1 for e in group.entries if is_entry_unpriced(e))
        section_priced_count = section_entries_count - section_unpriced_count

        rec_subtotal_raw = group.recorded_group_total
        has_rec_subtotal = (
            rec_subtotal_raw is not None
            and str(rec_subtotal_raw).strip().lower() not in ("", "null", "none", "-")
        )
        rec_subtotal_val: Optional[Decimal] = Decimal(str(rec_subtotal_raw)) if has_rec_subtotal else None

        # Section Summary Row in table
        subtotal_label = (
            f"<b>Calculated Daily Total ({section_priced_count} priced transactions)</b>"
            if section_unpriced_count == 0
            else f"<b>Calculated Daily Total ({section_priced_count} priced, {section_unpriced_count} unpriced)</b>"
        )
        table_data.append([
            "",
            "",
            Paragraph(subtotal_label, style_cell_reg),
            Paragraph(f"<b>{format_inr(section_calc_sum)}</b>", style_cell_right_bold),
        ])

        if has_rec_subtotal and rec_subtotal_val is not None:
            diff = rec_subtotal_val - section_calc_sum
            diff_label = (
                "Matches calculated daily total"
                if abs(diff) < Decimal("0.001")
                else f"Difference of {format_inr(abs(diff))} ({'Recorded exceeds calculated' if diff > 0 else 'Calculated exceeds recorded'})"
            )
            table_data.append([
                "",
                "",
                Paragraph(f"<b>Recorded Handwritten Subtotal:</b> <font color='#475569'>({diff_label})</font>", style_cell_reg),
                Paragraph(f"<b>{format_inr(rec_subtotal_val)}</b>", style_cell_right_bold),
            ])
        else:
            table_data.append([
                "",
                "",
                Paragraph("<b>Recorded Handwritten Subtotal:</b> <font color='#64748B'><i>Not Recorded on page</i></font>", style_cell_reg),
                Paragraph("<i>Not Recorded</i>", style_cell_right),
            ])

        # Table Column Widths: total 523.27 pt
        col_widths = [85, 38, 300.27, 100]
        t_group = Table(table_data, colWidths=col_widths, repeatRows=1)

        t_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ("ALIGN", (0, 0), (1, -1), "LEFT"),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]

        # Alternating row shading for data rows
        num_rows = len(table_data)
        summary_rows_count = 2  # Calculated daily total + Recorded subtotal
        data_rows_count = num_rows - 1 - summary_rows_count

        for r_i in range(1, data_rows_count + 1):
            if r_i % 2 == 0:
                t_style.append(("BACKGROUND", (0, r_i), (-1, r_i), colors.HexColor("#F8FAFC")))

        # Highlight summary rows
        t_style.append(("BACKGROUND", (0, num_rows - 2), (-1, num_rows - 1), colors.HexColor("#F1F5F9")))
        t_style.append(("LINEABOVE", (0, num_rows - 2), (-1, num_rows - 2), 1, colors.HexColor("#94A3B8")))

        t_group.setStyle(TableStyle(t_style))
        group_elements.append(t_group)
        group_elements.append(Spacer(1, 6))

        if len(group.entries) <= 6:
            story.append(KeepTogether(group_elements))
        else:
            story.extend(group_elements)

    # =========================================================================
    # SECTION D: Period Sales Summary
    # =========================================================================
    story.append(Spacer(1, 6))
    summary_elements: List[Any] = []
    summary_elements.append(Paragraph("3. PERIOD SALES SUMMARY", style_section_heading))

    summary_rows = [
        [Paragraph("Particulars", style_table_header), Paragraph("Amount / Detail", style_table_header_right)],
        [
            Paragraph("<b>Total Calculated Sales</b> (Sum of individual line items)", style_cell_reg),
            Paragraph(f"<b>{format_inr(total_calculated_sales)}</b>", style_cell_right_bold),
        ],
        [
            Paragraph("<b>Sum of Recorded Daily Subtotals</b> (Handwritten section subtotals)", style_cell_reg),
            Paragraph(
                f"<b>{format_inr(sum_recorded_subtotals)}</b>" if sum_recorded_subtotals is not None else "<i>Not Recorded</i>",
                style_cell_right_bold,
            ),
        ],
        [
            Paragraph("<b>Written Page Grand Total</b> (Handwritten at page bottom)", style_cell_reg),
            Paragraph(
                f"<b>{format_inr(written_page_total)}</b>" if written_page_total is not None else "<i>Not Recorded</i>",
                style_cell_right_bold,
            ),
        ],
        [
            Paragraph("Total Transactions Recorded", style_cell_reg),
            Paragraph(str(total_entries_count), style_cell_right),
        ],
        [
            Paragraph("Priced Transactions (Included in calculated sales)", style_cell_reg),
            Paragraph(str(priced_count), style_cell_right),
        ],
        [
            Paragraph("Unpriced Transactions (Amount Not Recorded — excluded from total)", style_cell_reg),
            Paragraph(str(unpriced_count), style_cell_right),
        ],
        [
            Paragraph("Pending Confirmation Entries", style_cell_reg),
            Paragraph(f"<font color='#B45309'><b>{pending_count}</b></font>", style_cell_right),
        ],
        [
            Paragraph("Confirmed Transactions (Human Reviewed)", style_cell_reg),
            Paragraph(str(confirmed_count), style_cell_right),
        ],
    ]

    t_summary = Table(summary_rows, colWidths=[363.27, 160])
    t_summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
                ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#FFFFFF")),
                ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#F8FAFC")),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    summary_elements.append(t_summary)
    summary_elements.append(Spacer(1, 6))
    story.append(KeepTogether(summary_elements))

    # =========================================================================
    # SECTION E: Sales Reconciliation
    # =========================================================================
    recon_elements: List[Any] = []
    recon_elements.append(Paragraph("4. SALES RECONCILIATION & DISCREPANCY ANALYSIS", style_section_heading))
    recon_elements.append(
        Paragraph(
            "Comparison between handwritten recorded subtotals and dynamically calculated line-item sums. "
            "Neither handwritten figures nor transaction sums are altered.",
            style_cell_muted,
        )
    )
    recon_elements.append(Spacer(1, 4))

    recon_rows: List[List[Any]] = [
        [
            Paragraph("Section / Date", style_table_header),
            Paragraph("Recorded Subtotal", style_table_header_right),
            Paragraph("Calculated Total", style_table_header_right),
            Paragraph("Difference", style_table_header_right),
            Paragraph("Reconciliation Status", style_table_header),
        ]
    ]

    total_rec_diff = Decimal("0")
    has_any_subtotals = False

    for s_idx, group in enumerate(extraction.groups):
        section_label = f"Section {s_idx + 1} ({group.date_raw.replace(chr(10), ' ').strip() if group.date_raw else (group.date_iso or f'Sec {s_idx+1}')})"
        c_sum = calculate_group_sum(group)

        if group.recorded_group_total is not None and str(group.recorded_group_total).strip().lower() not in ("", "null", "none", "-"):
            has_any_subtotals = True
            r_total = Decimal(str(group.recorded_group_total))
            diff = r_total - c_sum
            total_rec_diff += diff
            diff_str = format_inr(diff) if abs(diff) >= Decimal("0.001") else "₹0.00"
            status_text = (
                "<font color='#0B5D45'><b>Reconciled (Exact Match)</b></font>"
                if abs(diff) < Decimal("0.001")
                else f"<font color='#B45309'><b>Discrepancy: {format_inr(abs(diff))}</b></font>"
            )
            r_str = format_inr(r_total)
        else:
            r_str = "<i>Not Recorded</i>"
            diff_str = "—"
            status_text = "<font color='#64748B'>No handwritten subtotal on document</font>"

        recon_rows.append([
            Paragraph(section_label, style_cell_reg),
            Paragraph(r_str, style_cell_right),
            Paragraph(format_inr(c_sum), style_cell_right),
            Paragraph(diff_str, style_cell_right_bold),
            Paragraph(status_text, style_cell_reg),
        ])

    # Summary Reconciliation row
    if has_any_subtotals and sum_recorded_subtotals is not None:
        overall_diff = sum_recorded_subtotals - total_calculated_sales
        overall_status = (
            "<font color='#0B5D45'><b>Reconciled</b></font>"
            if abs(overall_diff) < Decimal("0.001")
            else f"<font color='#B45309'><b>Net Variance: {format_inr(abs(overall_diff))}</b></font>"
        )
        recon_rows.append([
            Paragraph("<b>Total Across Sections</b>", style_cell_bold),
            Paragraph(f"<b>{format_inr(sum_recorded_subtotals)}</b>", style_cell_right_bold),
            Paragraph(f"<b>{format_inr(total_calculated_sales)}</b>", style_cell_right_bold),
            Paragraph(f"<b>{format_inr(overall_diff)}</b>", style_cell_right_bold),
            Paragraph(overall_status, style_cell_reg),
        ])

    t_recon = Table(recon_rows, colWidths=[130, 95, 95, 85, 118.27])
    t_recon_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if has_any_subtotals:
        t_recon_style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F1F5F9")))
        t_recon_style.append(("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#94A3B8")))

    t_recon.setStyle(TableStyle(t_recon_style))
    recon_elements.append(t_recon)
    recon_elements.append(Spacer(1, 6))
    story.append(KeepTogether(recon_elements))

    # =========================================================================
    # SECTION F: Standard Formal Disclaimer (No AI mentions)
    # =========================================================================
    disclaimer_elements: List[Any] = []
    disclaimer_elements.append(Paragraph("5. NOTES & REGULATORY DISCLAIMER", style_section_heading))

    disclaimer_text = (
        "This statement is prepared from the business records provided and is intended to organize transaction "
        "information for reference and supporting documentation. Calculated amounts are derived from the transactions listed. "
        "Pending confirmations and discrepancies are identified separately. "
        "This statement is not an audited or certified financial statement."
    )

    t_disc = Table(
        [[Paragraph(disclaimer_text, style_disclaimer)]],
        colWidths=[523.27],
    )
    t_disc.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    disclaimer_elements.append(t_disc)
    story.append(KeepTogether(disclaimer_elements))

    # Build PDF with dynamic NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
