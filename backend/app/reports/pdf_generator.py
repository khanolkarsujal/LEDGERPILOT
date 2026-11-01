"""
Business Sales Statement PDF Generator.

Reproduces the exact visual structure, layout, typography, and styling
of the official template (ledgerpilot_business_sales_statement_template.png):

1. Top Dark Navy Accent Bar on every page (#0A2540)
2. Document Heading:
   - Left: BUSINESS SALES STATEMENT / Supporting Financial Records
   - Right: INR | ₹
3. Boxed Business Information Card:
   - Header: BUSINESS INFORMATION
   - Two-column: Business name | Business address
   - Divider line
   - Reporting period: [Start date] - [End date] | Prepared on: [Date]
4. Section 1: 1. DAILY SALES REGISTER:
   - Subtitle: Transactions transcribed from the business records provided.
   - 4-column Table: Date | Sr. No. | Particulars / Description | Amount (₹)
     (Dark Navy header, date on first row of section, Devanagari text, Not Recorded for unpriced)
   - Standalone Outlined Box per section: SECTION {N} TOTALS
     (4 columns: Transactions | Calculated total | Handwritten subtotal | Difference)
5. Section 2: 2. PERIOD SUMMARY:
   - Light green background container box (#EAF7EE)
   - Row 1: Calculated sales total | Recorded daily subtotals | Written grand total
   - Row 2: Amounts not recorded | Pending confirmation
6. Section 3: 3. SALES RECONCILIATION:
   - Subtitle: Reconcile each ledger section separately, including sections sharing a date.
   - 4-column Table: Date / Section | Recorded subtotal | Calculated total | Difference
     (Soft grey/blue header #F1F5F9, dark navy text)
7. IMPORTANT NOTE:
   - Divider line, heading IMPORTANT NOTE, exact formal disclaimer
8. Running Footer:
   - BUSINESS SALES STATEMENT • Supporting Financial Records | Page X of Y
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
# Color Palette (Matching Template Exactly)
# -----------------------------------------------------------------------------
COLOR_PRIMARY_NAVY = colors.HexColor("#0A2540")   # Headings, top bar, register header
COLOR_BORDER_GREY = colors.HexColor("#CBD5E1")    # Card and table borders
COLOR_LIGHT_BORDER = colors.HexColor("#E2E8F0")   # Internal card dividers
COLOR_BG_WHITE = colors.HexColor("#FFFFFF")
COLOR_BG_LIGHT_GREY = colors.HexColor("#F8FAFC")
COLOR_BG_LIGHT_BLUE = colors.HexColor("#F1F5F9")  # Reconciliation header
COLOR_BG_LIGHT_GREEN = colors.HexColor("#EAF7EE") # Period summary box
COLOR_BORDER_GREEN = colors.HexColor("#C8E6C9")
COLOR_TEXT_DARK = colors.HexColor("#0F172A")
COLOR_TEXT_MUTED = colors.HexColor("#475569")
COLOR_TEXT_SUBTLE = colors.HexColor("#64748B")

# -----------------------------------------------------------------------------
# Font Registration (Devanagari Unicode & Rupee Symbol)
# -----------------------------------------------------------------------------
FONT_REGULAR = "NirmalaUI"
FONT_BOLD = "NirmalaUI-Bold"
_FONTS_INITIALIZED = False


def _init_fonts() -> Tuple[str, str]:
    """Registers Nirmala UI font with graceful fallbacks."""
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
        print(f"[!] PDF Font warning: {e}. Falling back to standard fonts.")

    FONT_REGULAR = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"
    _FONTS_INITIALIZED = True
    return FONT_REGULAR, FONT_BOLD


# -----------------------------------------------------------------------------
# Financial Data & Formatting Helpers
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
    """Identifies entries where amount was not recorded on physical ledger."""
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
    """Identifies entries requiring confirmation (uncertain or flagged without human review)."""
    if entry.review_status == "human_reviewed":
        return False
    if entry.uncertain_fields or entry.flag_reason or is_entry_unpriced(entry):
        return True
    return False


def calculate_group_sum(group: TransactionGroup) -> Decimal:
    """Sums valid priced amounts in a section."""
    total = Decimal("0")
    for e in group.entries:
        if not is_entry_unpriced(e):
            amt = get_effective_amount(e)
            if amt is not None:
                total += amt
    return total


def format_inr(amount: Optional[Decimal]) -> str:
    """Formats amount with Indian Rupee symbol."""
    if amount is None:
        return "Not Recorded"
    return f"₹ {amount:,.2f}"


def format_date_ddmmyyyy(raw_date: Optional[str], iso_date: Optional[str]) -> str:
    """Formats date to DD/MM/YYYY or cleanly formatted display string."""
    if iso_date and len(iso_date) == 10 and iso_date.count("-") == 2:
        parts = iso_date.split("-")
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    if raw_date:
        clean = raw_date.replace("\n", " ").strip()
        # If raw date already has numbers like 10/11/2019
        return clean
    return ""


# -----------------------------------------------------------------------------
# Numbered Canvas for Top Accent Bar & Footer
# -----------------------------------------------------------------------------
class TemplateCanvas(canvas.Canvas):
    """Draws top navy accent bar on all pages and formal footer."""

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

        # 1. Top Navy Accent Line across the printable top (matching template exactly)
        self.setFillColor(COLOR_PRIMARY_NAVY)
        self.rect(36, 814, 523.27, 3.5, fill=1, stroke=0)

        # 2. Running Bottom Footer (matching template exactly)
        self.setFont(font_reg, 7)
        self.setFillColor(COLOR_TEXT_SUBTLE)
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(559, 22, page_str)
        self.drawString(
            36,
            22,
            "BUSINESS SALES STATEMENT  •  Supporting Financial Records",
        )
        self.setStrokeColor(COLOR_BORDER_GREY)
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
    Generates a formal Business Sales Statement PDF strictly matching
    ledgerpilot_business_sales_statement_template.png.
    """
    font_reg, font_bold = _init_fonts()

    # Dynamic metrics calculation
    all_entries = [e for g in extraction.groups for e in g.entries]
    total_entries_count = len(all_entries)
    unpriced_count = sum(1 for e in all_entries if is_entry_unpriced(e))
    priced_count = total_entries_count - unpriced_count
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
    formatted_dates: List[str] = []
    for g in extraction.groups:
        d_str = format_date_ddmmyyyy(g.date_raw, g.date_iso)
        if d_str and d_str not in formatted_dates:
            formatted_dates.append(d_str)

    if len(formatted_dates) > 1:
        reporting_period_str = f"{formatted_dates[0]} - {formatted_dates[-1]}"
    elif len(formatted_dates) == 1:
        reporting_period_str = formatted_dates[0]
    else:
        reporting_period_str = "Not Specified"

    prep_date_str = datetime.now().strftime("%d/%m/%Y")

    # Document Setup (A4: 595.27 x 841.89 points, margins 36 pt / 0.5 in)
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

    # Style Definitions
    style_doc_title = ParagraphStyle(
        "DocTitle",
        fontName=font_bold,
        fontSize=18,
        leading=22,
        textColor=COLOR_PRIMARY_NAVY,
    )
    style_doc_subtitle = ParagraphStyle(
        "DocSubtitle",
        fontName=font_reg,
        fontSize=9.5,
        leading=13,
        textColor=COLOR_TEXT_SUBTLE,
    )
    style_currency_header = ParagraphStyle(
        "CurrencyHeader",
        fontName=font_bold,
        fontSize=11,
        leading=15,
        textColor=COLOR_PRIMARY_NAVY,
        alignment=2,
    )
    style_section_title = ParagraphStyle(
        "SectionTitle",
        fontName=font_bold,
        fontSize=10.5,
        leading=14,
        textColor=COLOR_PRIMARY_NAVY,
        spaceBefore=10,
        spaceAfter=2,
    )
    style_section_subtitle = ParagraphStyle(
        "SectionSubtitle",
        fontName=font_reg,
        fontSize=7.5,
        leading=10,
        textColor=COLOR_TEXT_SUBTLE,
        spaceAfter=6,
    )
    style_card_heading = ParagraphStyle(
        "CardHeading",
        fontName=font_bold,
        fontSize=7.5,
        leading=10,
        textColor=COLOR_PRIMARY_NAVY,
    )
    style_label_muted = ParagraphStyle(
        "LabelMuted",
        fontName=font_reg,
        fontSize=7,
        leading=9.5,
        textColor=COLOR_TEXT_MUTED,
    )
    style_val_bold = ParagraphStyle(
        "ValBold",
        fontName=font_bold,
        fontSize=8.5,
        leading=11.5,
        textColor=COLOR_TEXT_DARK,
    )
    style_val_bold_large = ParagraphStyle(
        "ValBoldLarge",
        fontName=font_bold,
        fontSize=10,
        leading=13,
        textColor=COLOR_PRIMARY_NAVY,
    )
    style_table_th = ParagraphStyle(
        "TableTH",
        fontName=font_bold,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#FFFFFF"),
    )
    style_table_th_right = ParagraphStyle(
        "TableTHRight",
        fontName=font_bold,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#FFFFFF"),
        alignment=2,
    )
    style_table_th_recon = ParagraphStyle(
        "TableTHRecon",
        fontName=font_bold,
        fontSize=7.5,
        leading=10,
        textColor=COLOR_PRIMARY_NAVY,
    )
    style_table_th_recon_right = ParagraphStyle(
        "TableTHReconRight",
        fontName=font_bold,
        fontSize=7.5,
        leading=10,
        textColor=COLOR_PRIMARY_NAVY,
        alignment=2,
    )
    style_td_reg = ParagraphStyle(
        "TDReg",
        fontName=font_reg,
        fontSize=8,
        leading=10.5,
        textColor=COLOR_TEXT_DARK,
    )
    style_td_right = ParagraphStyle(
        "TDRight",
        fontName=font_reg,
        fontSize=8,
        leading=10.5,
        textColor=COLOR_TEXT_DARK,
        alignment=2,
    )
    style_td_right_bold = ParagraphStyle(
        "TDRightBold",
        fontName=font_bold,
        fontSize=8,
        leading=10.5,
        textColor=COLOR_TEXT_DARK,
        alignment=2,
    )
    style_disclaimer_text = ParagraphStyle(
        "DisclaimerText",
        fontName=font_reg,
        fontSize=7,
        leading=10,
        textColor=COLOR_TEXT_MUTED,
    )

    story: List[Any] = []

    # =========================================================================
    # DOCUMENT HEADING
    # =========================================================================
    # Left: BUSINESS SALES STATEMENT / Supporting Financial Records
    # Right: INR | ₹
    heading_table = Table(
        [
            [
                Paragraph("<b>BUSINESS SALES STATEMENT</b>", style_doc_title),
                Paragraph("<b>INR  |  ₹</b>", style_currency_header),
            ],
            [
                Paragraph("Supporting Financial Records", style_doc_subtitle),
                "",
            ],
        ],
        colWidths=[423.27, 100],
    )
    heading_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(heading_table)
    story.append(Spacer(1, 8))

    # =========================================================================
    # BUSINESS INFORMATION CARD (Outlined Box matching template)
    # =========================================================================
    biz_name_val = business_name.strip() if business_name and business_name.strip() else ""
    biz_addr_val = business_address.strip() if business_address and business_address.strip() else ""

    biz_card_content = [
        # Card Header
        [
            Paragraph("<b>BUSINESS INFORMATION</b>", style_card_heading),
            "",
        ],
        # Field labels + values
        [
            Paragraph(
                f"<font color='#64748B' size='7'>Business name</font><br/><b>{biz_name_val if biz_name_val else '&nbsp;'}</b>",
                style_td_reg,
            ),
            Paragraph(
                f"<font color='#64748B' size='7'>Business address</font><br/>{biz_addr_val if biz_addr_val else '&nbsp;'}",
                style_td_reg,
            ),
        ],
        # Bottom row
        [
            Paragraph(f"Reporting period: <b>{reporting_period_str}</b>", style_td_reg),
            Paragraph(f"Prepared on: <b>{prep_date_str}</b>", style_td_right),
        ],
    ]

    t_biz_box = Table(biz_card_content, colWidths=[261.63, 261.64])
    t_biz_box.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_WHITE),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER_GREY),
                ("LINEBELOW", (0, 1), (1, 1), 0.5, COLOR_LIGHT_BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(t_biz_box)
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 1: 1. DAILY SALES REGISTER
    # =========================================================================
    story.append(Paragraph("<b>1. DAILY SALES REGISTER</b>", style_section_title))
    story.append(
        Paragraph("Transactions transcribed from the business records provided.", style_section_subtitle)
    )

    # Render each ledger section separately (preserving separate handwritten sections)
    for s_idx, group in enumerate(extraction.groups):
        section_num = s_idx + 1
        section_elements: List[Any] = []

        date_formatted = format_date_ddmmyyyy(group.date_raw, group.date_iso)

        # 4-column Transaction Table
        table_data: List[List[Any]] = [
            [
                Paragraph("Date", style_table_th),
                Paragraph("Sr. No.", style_table_th),
                Paragraph("Particulars / Description", style_table_th),
                Paragraph("Amount (₹)", style_table_th_right),
            ]
        ]

        for e_idx, entry in enumerate(group.entries):
            sr_no = str(entry.entry_index if entry.entry_index is not None else e_idx + 1)
            eff_desc = get_effective_description(entry)
            unpriced = is_entry_unpriced(entry)
            amt_val = get_effective_amount(entry)

            # Date is printed on first row of section; subsequent rows blank
            row_date = date_formatted if e_idx == 0 else ""

            # Description Paragraph
            desc_cell = Paragraph(eff_desc, style_td_reg)

            # Amount Column
            if unpriced:
                amt_cell = Paragraph("<b>Not Recorded</b>", style_td_right_bold)
            else:
                amt_str = f"{amt_val:,.2f}" if amt_val is not None else "0.00"
                amt_cell = Paragraph(amt_str, style_td_right)

            table_data.append([
                Paragraph(row_date, style_td_reg),
                Paragraph(sr_no, style_td_reg),
                desc_cell,
                amt_cell,
            ])

        col_widths = [85, 45, 293.27, 100]
        t_register = Table(table_data, colWidths=col_widths, repeatRows=1)

        t_reg_style = [
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY_NAVY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_GREY),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]

        t_register.setStyle(TableStyle(t_reg_style))
        section_elements.append(t_register)
        section_elements.append(Spacer(1, 4))

        # Standalone SECTION {N} TOTALS Outlined Box (matching template exactly)
        sec_calc_sum = calculate_group_sum(group)
        sec_count = len(group.entries)

        rec_total_raw = group.recorded_group_total
        has_rec_total = (
            rec_total_raw is not None
            and str(rec_total_raw).strip().lower() not in ("", "null", "none", "-")
        )

        if has_rec_total:
            rec_subtotal_dec = Decimal(str(rec_total_raw))
            rec_subtotal_str = f"₹ {rec_subtotal_dec:,.2f}"
            diff_dec = rec_subtotal_dec - sec_calc_sum
            diff_str = f"₹ {diff_dec:,.2f}"
        else:
            rec_subtotal_str = "Not Recorded"
            diff_str = "—"

        totals_box_data = [
            [
                Paragraph(f"<b>SECTION {section_num} TOTALS</b>", style_card_heading),
                "",
                "",
                "",
            ],
            [
                Paragraph(
                    f"<font color='#64748B' size='7'>Transactions</font><br/><b>{sec_count}</b>",
                    style_td_reg,
                ),
                Paragraph(
                    f"<font color='#64748B' size='7'>Calculated total</font><br/><b>₹ {sec_calc_sum:,.2f}</b>",
                    style_td_reg,
                ),
                Paragraph(
                    f"<font color='#64748B' size='7'>Handwritten subtotal</font><br/><b>{rec_subtotal_str}</b>",
                    style_td_reg,
                ),
                Paragraph(
                    f"<font color='#64748B' size='7'>Difference</font><br/><b>{diff_str}</b>",
                    style_td_reg,
                ),
            ],
        ]

        t_totals_box = Table(totals_box_data, colWidths=[110, 140, 140, 133.27])
        t_totals_box.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 0), (3, 0)),
                    ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_WHITE),
                    ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER_GREY),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        section_elements.append(t_totals_box)
        section_elements.append(Spacer(1, 8))

        if len(group.entries) <= 6:
            story.append(KeepTogether(section_elements))
        else:
            story.extend(section_elements)

    # =========================================================================
    # SECTION 2: 2. PERIOD SUMMARY (Light Green Container matching template)
    # =========================================================================
    summary_elements: List[Any] = []
    summary_elements.append(Paragraph("<b>2. PERIOD SUMMARY</b>", style_section_title))

    sum_rec_str = f"₹ {sum_recorded_subtotals:,.2f}" if sum_recorded_subtotals is not None else "Not Recorded"
    written_page_str = (
        f"₹ {written_page_total:,.2f}"
        if written_page_total is not None
        else "Not present"
    )

    period_box_data = [
        # Top Row: 3 columns
        [
            Paragraph(
                f"<font color='#475569' size='7'>Calculated sales total</font><br/><b>₹ {total_calculated_sales:,.2f}</b>",
                style_val_bold_large,
            ),
            Paragraph(
                f"<font color='#475569' size='7'>Recorded daily subtotals</font><br/><b>{sum_rec_str}</b>",
                style_val_bold_large,
            ),
            Paragraph(
                f"<font color='#475569' size='7'>Written grand total</font><br/><b>{written_page_str}</b>",
                style_val_bold,
            ),
        ],
        # Bottom Row: 2 columns
        [
            Paragraph(
                f"<font color='#475569' size='7'>Amounts not recorded</font><br/><b>{unpriced_count}</b>",
                style_val_bold,
            ),
            Paragraph(
                f"<font color='#475569' size='7'>Pending confirmation</font><br/><b>{pending_count}</b>",
                style_val_bold,
            ),
            "",
        ],
    ]

    t_period_box = Table(period_box_data, colWidths=[180, 180, 163.27])
    t_period_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_BG_LIGHT_GREEN),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER_GREEN),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    summary_elements.append(t_period_box)
    summary_elements.append(Spacer(1, 10))
    story.append(KeepTogether(summary_elements))

    # =========================================================================
    # SECTION 3: 3. SALES RECONCILIATION
    # =========================================================================
    recon_elements: List[Any] = []
    recon_elements.append(Paragraph("<b>3. SALES RECONCILIATION</b>", style_section_title))
    recon_elements.append(
        Paragraph("Reconcile each ledger section separately, including sections sharing a date.", style_section_subtitle)
    )

    # 4-column Table: Date / Section | Recorded subtotal | Calculated total | Difference
    recon_data: List[List[Any]] = [
        [
            Paragraph("Date / Section", style_table_th_recon),
            Paragraph("Recorded subtotal", style_table_th_recon_right),
            Paragraph("Calculated total", style_table_th_recon_right),
            Paragraph("Difference", style_table_th_recon_right),
        ]
    ]

    for s_idx, group in enumerate(extraction.groups):
        section_label = f"{format_date_ddmmyyyy(group.date_raw, group.date_iso)} / Section {s_idx + 1}"
        c_sum = calculate_group_sum(group)

        if group.recorded_group_total is not None and str(group.recorded_group_total).strip().lower() not in ("", "null", "none", "-"):
            r_dec = Decimal(str(group.recorded_group_total))
            r_str = f"₹ {r_dec:,.2f}"
            diff_dec = r_dec - c_sum
            diff_str = f"₹ {diff_dec:,.2f}"
        else:
            r_str = "Not Recorded"
            diff_str = "—"

        recon_data.append([
            Paragraph(section_label, style_td_reg),
            Paragraph(r_str, style_td_right),
            Paragraph(f"₹ {c_sum:,.2f}", style_td_right),
            Paragraph(diff_str, style_td_right_bold),
        ])

    t_recon = Table(recon_data, colWidths=[163.27, 120, 120, 120])
    t_recon.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_BG_LIGHT_BLUE),
                ("BACKGROUND", (0, 1), (-1, -1), COLOR_BG_WHITE),
                ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_GREY),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    recon_elements.append(t_recon)
    recon_elements.append(Spacer(1, 10))

    # =========================================================================
    # IMPORTANT NOTE (Mandatory Disclaimer matching template)
    # =========================================================================
    recon_elements.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_LIGHT_BORDER, spaceBefore=4, spaceAfter=6))
    recon_elements.append(Paragraph("<b>IMPORTANT NOTE</b>", style_card_heading))
    recon_elements.append(Spacer(1, 2))

    disclaimer_text = (
        "Prepared from the business records provided. Calculated amounts are derived from the transactions listed. "
        "Pending confirmations and discrepancies are identified separately. "
        "This statement is not an audited or certified financial statement."
    )
    recon_elements.append(Paragraph(disclaimer_text, style_disclaimer_text))

    story.append(KeepTogether(recon_elements))

    # Build document with TemplateCanvas
    doc.build(story, canvasmaker=TemplateCanvas)
    return buffer.getvalue()
