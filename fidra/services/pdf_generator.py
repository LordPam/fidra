"""Professional PDF generator using ReportLab with Fidra branding.

Creates beautiful, branded financial reports with:
- Brand colors (Dark Blue #23395B, Gold #BFA159, Light Blue #4A6FA5)
- Professional typography and layout
- Styled tables with alternating rows
- Summary cards and charts
- Headers and footers
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    HRFlowable,
    Image,
)
from reportlab.graphics.shapes import Drawing

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus


# =============================================================================
# BRAND COLORS
# =============================================================================

class FidraColors:
    """Fidra brand color palette."""

    # Primary brand colors
    DARK_BLUE = colors.HexColor('#23395B')
    GOLD = colors.HexColor('#BFA159')
    LIGHT_BLUE = colors.HexColor('#4A6FA5')
    NAVY = colors.HexColor('#0D1F2F')

    # Neutral colors
    WHITE = colors.HexColor('#FFFFFF')
    OFF_WHITE = colors.HexColor('#F9FAFB')
    LIGHT_GRAY = colors.HexColor('#F3F4F6')
    MEDIUM_GRAY = colors.HexColor('#9CA3AF')
    DARK_GRAY = colors.HexColor('#4B5563')
    TEXT = colors.HexColor('#111827')

    # Status colors
    SUCCESS = colors.HexColor('#10B981')
    DANGER = colors.HexColor('#EF4444')
    WARNING = colors.HexColor('#F59E0B')

    # Table colors
    TABLE_HEADER_BG = DARK_BLUE
    TABLE_HEADER_TEXT = WHITE
    TABLE_ROW_ALT = colors.HexColor('#F6F3EC')
    TABLE_BORDER = colors.HexColor('#DCE2EA')
    TABLE_ACCENT_BORDER = GOLD


# =============================================================================
# STYLES
# =============================================================================

def get_fidra_styles():
    """Get Fidra-branded paragraph styles."""
    styles = getSampleStyleSheet()

    # Title style - large, dark blue
    styles.add(ParagraphStyle(
        name='FidraTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=FidraColors.DARK_BLUE,
        spaceAfter=6*mm,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold',
    ))

    # Subtitle
    styles.add(ParagraphStyle(
        name='FidraSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=FidraColors.MEDIUM_GRAY,
        spaceAfter=8*mm,
    ))

    # Section header - gold accent bar
    styles.add(ParagraphStyle(
        name='FidraH2',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=FidraColors.NAVY,
        spaceBefore=10*mm,
        spaceAfter=4*mm,
        fontName='Helvetica-Bold',
        leftIndent=3*mm,
        borderPadding=(2*mm, 2*mm, 2*mm, 2*mm),
    ))

    # Subsection header
    styles.add(ParagraphStyle(
        name='FidraH3',
        parent=styles['Heading3'],
        fontSize=11,
        textColor=FidraColors.DARK_BLUE,
        spaceBefore=6*mm,
        spaceAfter=3*mm,
        fontName='Helvetica-Bold',
    ))

    # Body text
    styles.add(ParagraphStyle(
        name='FidraBody',
        parent=styles['Normal'],
        fontSize=10,
        textColor=FidraColors.TEXT,
        spaceAfter=3*mm,
        leading=14,
    ))

    # Small text (for notes, footers)
    styles.add(ParagraphStyle(
        name='FidraSmall',
        parent=styles['Normal'],
        fontSize=8,
        textColor=FidraColors.MEDIUM_GRAY,
    ))

    # Figure caption
    styles.add(ParagraphStyle(
        name='FidraCaption',
        parent=styles['Normal'],
        fontSize=8,
        textColor=FidraColors.MEDIUM_GRAY,
        alignment=TA_LEFT,
        spaceBefore=1*mm,
        spaceAfter=4*mm,
    ))

    # Amount styles
    styles.add(ParagraphStyle(
        name='FidraIncome',
        parent=styles['Normal'],
        fontSize=10,
        textColor=FidraColors.SUCCESS,
        fontName='Helvetica-Bold',
    ))

    styles.add(ParagraphStyle(
        name='FidraExpense',
        parent=styles['Normal'],
        fontSize=10,
        textColor=FidraColors.DANGER,
        fontName='Helvetica-Bold',
    ))

    return styles


# =============================================================================
# TABLE STYLING
# =============================================================================

def get_transaction_table_style():
    """Get styled table configuration for transaction tables."""
    return TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), FidraColors.TABLE_HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), FidraColors.TABLE_HEADER_TEXT),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),

        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('TEXTCOLOR', (0, 1), (-1, -1), FidraColors.TEXT),

        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [FidraColors.WHITE, FidraColors.TABLE_ROW_ALT]),

        # Borders
        ('GRID', (0, 0), (-1, -1), 0.5, FidraColors.TABLE_BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, FidraColors.DARK_BLUE),

        # Alignment
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Date column left
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),  # Description left
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),  # Numbers right

        # Vertical alignment
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])


def get_summary_table_style():
    """Get styled table for summary cards."""
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), FidraColors.OFF_WHITE),
        ('BOX', (0, 0), (-1, -1), 1, FidraColors.TABLE_BORDER),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('TEXTCOLOR', (0, 0), (-1, 0), FidraColors.MEDIUM_GRAY),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 14),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ])


# =============================================================================
# PDF GENERATOR
# =============================================================================

class FidraPDFGenerator:
    """Generate professional PDFs with Fidra branding."""

    def __init__(self):
        """Initialize the PDF generator."""
        self.styles = get_fidra_styles()
        self.page_width, self.page_height = A4
        self.margin = 2 * cm
        self._logo_drawing = self._load_logo()

    def _load_logo(self):
        """Load the Fidra logo SVG as a ReportLab Drawing.

        Returns:
            Scaled Drawing or None if unavailable.
        """
        try:
            from svglib.svglib import svg2rlg

            logo_path = Path(__file__).parent.parent / 'resources' / 'logo.svg'
            if not logo_path.exists():
                return None

            drawing = svg2rlg(str(logo_path))
            if drawing is None:
                return None

            # Scale to fit banner height (approx 8mm tall)
            target_h = 8 * mm
            scale = target_h / drawing.height
            drawing.width *= scale
            drawing.height = target_h
            drawing.scale(scale, scale)

            return drawing
        except Exception:
            return None

    def generate_transaction_report(
        self,
        transactions: list[Transaction],
        output_path: Path,
        title: str = "Transaction Report",
        include_summary: bool = True,
        include_charts: bool = False,
        balances: Optional[dict[str, Decimal]] = None,
    ) -> None:
        """Generate a professional transaction report PDF.

        Args:
            transactions: List of transactions to include
            output_path: Output file path
            title: Report title
            include_summary: Whether to include summary section
            include_charts: Whether to include charts
            balances: Optional dict of transaction ID to running balance
        """
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=self.margin,
            rightMargin=self.margin,
            topMargin=3 * cm,
            bottomMargin=self.margin,
        )

        story = []

        # Header
        story.extend(self._build_header(title))

        # Summary section
        if include_summary and transactions:
            story.extend(self._build_summary(transactions))

        # Transaction table
        if transactions:
            story.extend(self._build_transaction_table(transactions, balances))
        else:
            story.append(Paragraph(
                "No transactions to display.",
                self.styles['FidraBody']
            ))

        # Build PDF
        doc.build(story, onFirstPage=self._add_branded_first_page,
                  onLaterPages=self._add_branded_later_pages)

    def _build_header(self, title: str) -> list:
        """Build report header."""
        elements = []

        # Title with gold underline
        elements.append(Paragraph(title, self.styles['FidraTitle']))

        # Gold accent line
        elements.append(HRFlowable(
            width="100%",
            thickness=2,
            color=FidraColors.GOLD,
            spaceAfter=2*mm,
        ))

        # Subtitle with date
        elements.append(Paragraph(
            f"Generated on {date.today().strftime('%d %B %Y')}",
            self.styles['FidraSubtitle']
        ))

        return elements

    def _build_summary(self, transactions: list[Transaction]) -> list:
        """Build summary cards section."""
        elements = []

        # Calculate totals
        valid = [t for t in transactions
                 if t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)]

        total_income = sum(
            t.amount for t in valid if t.type == TransactionType.INCOME
        )
        total_expenses = sum(
            t.amount for t in valid if t.type == TransactionType.EXPENSE
        )
        net = total_income - total_expenses
        pending_count = sum(1 for t in transactions if t.status == ApprovalStatus.PENDING)

        # Section header with gold bar
        elements.append(self._section_header("Summary"))

        # Summary cards as a table
        card_data = [
            ['Transactions', 'Total Income', 'Total Expenses', 'Net Change'],
            [
                str(len(transactions)),
                f"£{total_income:,.2f}",
                f"£{total_expenses:,.2f}",
                f"{'+'if net >= 0 else ''}£{net:,.2f}",
            ]
        ]

        # Calculate column widths
        available_width = self.page_width - 2 * self.margin
        col_width = available_width / 4

        summary_table = Table(card_data, colWidths=[col_width] * 4)

        # Custom styling for summary cards
        style = [
            ('BACKGROUND', (0, 0), (-1, -1), FidraColors.OFF_WHITE),
            ('BOX', (0, 0), (0, -1), 1, FidraColors.DARK_BLUE),
            ('BOX', (1, 0), (1, -1), 1, FidraColors.SUCCESS),
            ('BOX', (2, 0), (2, -1), 1, FidraColors.DANGER),
            ('BOX', (3, 0), (3, -1), 1, FidraColors.GOLD if net >= 0 else FidraColors.DANGER),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('TEXTCOLOR', (0, 0), (-1, 0), FidraColors.MEDIUM_GRAY),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, 1), 16),
            ('TEXTCOLOR', (0, 1), (0, 1), FidraColors.DARK_BLUE),
            ('TEXTCOLOR', (1, 1), (1, 1), FidraColors.SUCCESS),
            ('TEXTCOLOR', (2, 1), (2, 1), FidraColors.DANGER),
            ('TEXTCOLOR', (3, 1), (3, 1), FidraColors.GOLD if net >= 0 else FidraColors.DANGER),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]

        summary_table.setStyle(TableStyle(style))
        elements.append(summary_table)
        elements.append(Spacer(1, 6*mm))

        # Pending notice if any
        if pending_count > 0:
            elements.append(Paragraph(
                f"<i>Note: {pending_count} transaction{'s' if pending_count != 1 else ''} pending approval</i>",
                self.styles['FidraSmall']
            ))
            elements.append(Spacer(1, 4*mm))

        return elements

    def _build_transaction_table(
        self,
        transactions: list[Transaction],
        balances: Optional[dict[str, Decimal]] = None,
    ) -> list:
        """Build transaction table."""
        elements = []

        # Section header
        elements.append(self._section_header("Transactions"))

        # Sort transactions by date
        sorted_trans = sorted(transactions, key=lambda t: (t.date, t.description.lower()))

        # Build table data
        if balances:
            headers = ['Date', 'Description', 'Amount', 'Type', 'Status', 'Balance']
            col_widths = [22*mm, 55*mm, 25*mm, 20*mm, 22*mm, 25*mm]
        else:
            headers = ['Date', 'Description', 'Amount', 'Type', 'Status', 'Category']
            col_widths = [22*mm, 60*mm, 25*mm, 20*mm, 22*mm, 25*mm]

        data = [headers]

        for t in sorted_trans:
            # Format amount with color indicator
            if t.type == TransactionType.INCOME:
                amount_str = f"+£{t.amount:,.2f}"
            else:
                amount_str = f"-£{t.amount:,.2f}"

            row = [
                t.date.strftime('%d %b %Y'),
                t.description[:35] + '...' if len(t.description) > 35 else t.description,
                amount_str,
                t.type.value.title(),
                t.status.value.title(),
            ]

            if balances:
                balance = balances.get(str(t.id), Decimal(0))
                row.append(f"£{balance:,.2f}")
            else:
                row.append(t.category or '-')

            data.append(row)

        # Create table
        table = Table(data, colWidths=col_widths, repeatRows=1)

        # Apply base style
        style = list(get_transaction_table_style().getCommands())

        # Add conditional formatting for amounts (column 2)
        for i, t in enumerate(sorted_trans, start=1):
            if t.type == TransactionType.INCOME:
                style.append(('TEXTCOLOR', (2, i), (2, i), FidraColors.SUCCESS))
            else:
                style.append(('TEXTCOLOR', (2, i), (2, i), FidraColors.DANGER))

            # Highlight pending rows
            if t.status == ApprovalStatus.PENDING:
                style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#FFFBEB')))

        table.setStyle(TableStyle(style))
        elements.append(table)

        return elements

    def _section_header(self, text: str) -> Paragraph:
        """Create a section header with gold accent."""
        # Create paragraph with left border effect using a table
        return Paragraph(
            f'<font color="#BFA159">▎</font> {text}',
            self.styles['FidraH2']
        )

    def _add_page_decorations(self, canvas, doc):
        """Add header/footer decorations to each page."""
        canvas.saveState()
        self._draw_footer(canvas, doc)
        canvas.restoreState()

    def _draw_footer(self, canvas, doc):
        """Draw standard footer with page number and branding."""
        # Thin gold line above footer
        canvas.setStrokeColor(FidraColors.GOLD)
        canvas.setLineWidth(0.5)
        canvas.line(
            self.margin, self.margin - 5*mm,
            self.page_width - self.margin, self.margin - 5*mm,
        )

        # Footer text
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(FidraColors.MEDIUM_GRAY)
        canvas.drawString(self.margin, self.margin - 10*mm, "Generated by Fidra")
        canvas.drawRightString(
            self.page_width - self.margin,
            self.margin - 10*mm,
            f"Page {doc.page}",
        )

    # =========================================================================
    # COMPREHENSIVE REPORT
    # =========================================================================

    def generate_comprehensive_report(
        self,
        transactions: list[Transaction],
        output_path: Path,
        title: str = "Financial Report",
        include_summary: bool = True,
        include_monthly_breakdown: bool = True,
        include_category_breakdown: bool = True,
        include_transaction_table: bool = True,
        chart_images: Optional[dict[str, bytes]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        balances: Optional[dict[str, Decimal]] = None,
    ) -> None:
        """Generate a comprehensive, professionally branded financial report.

        Includes summary cards, charts, monthly breakdown, category analysis,
        and a full transaction table with Fidra branding.

        Args:
            transactions: List of transactions (already filtered/sorted)
            output_path: Output file path
            title: Report title
            include_summary: Include summary cards section
            include_monthly_breakdown: Include monthly income/expense table
            include_category_breakdown: Include category analysis table
            include_transaction_table: Include full transaction listing
            chart_images: Dict of chart_name -> PNG bytes to embed
            start_date: Report period start date
            end_date: Report period end date
            balances: Optional running balances dict (transaction ID -> balance)
        """
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=self.margin,
            rightMargin=self.margin,
            topMargin=3 * cm,
            bottomMargin=self.margin,
        )

        story = []

        # Sort transactions
        sorted_trans = sorted(transactions, key=lambda t: (t.date, t.created_at))

        # Report header with metadata
        story.extend(self._build_report_header(title, sorted_trans, start_date, end_date))

        # Summary cards
        if include_summary and sorted_trans:
            story.extend(self._build_summary(sorted_trans))

        # Charts
        if chart_images:
            story.extend(self._build_charts_section(chart_images))

        # Monthly breakdown
        if include_monthly_breakdown and sorted_trans:
            story.extend(self._build_monthly_breakdown(sorted_trans))

        # Category breakdown
        if include_category_breakdown and sorted_trans:
            story.extend(self._build_category_breakdown(sorted_trans))

        # Full transaction table
        if include_transaction_table and sorted_trans:
            story.extend(self._build_transaction_table(sorted_trans, balances))

        # Build with branded page decorations
        doc.build(
            story,
            onFirstPage=self._add_branded_first_page,
            onLaterPages=self._add_branded_later_pages,
        )

    def _build_report_header(
        self,
        title: str,
        transactions: list[Transaction],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list:
        """Build comprehensive report header with metadata."""
        elements = []

        # Title
        elements.append(Paragraph(title, self.styles['FidraTitle']))

        # Gold accent line
        elements.append(HRFlowable(
            width="100%", thickness=2, color=FidraColors.GOLD, spaceAfter=3*mm,
        ))

        # Metadata line
        parts = [f"Generated {date.today().strftime('%d %B %Y')}"]
        if start_date and end_date:
            parts.append(
                f"Period: {start_date.strftime('%d %b %Y')} \u2014 "
                f"{end_date.strftime('%d %b %Y')}"
            )
        elif start_date:
            parts.append(f"From {start_date.strftime('%d %b %Y')}")
        elif end_date:
            parts.append(f"Up to {end_date.strftime('%d %b %Y')}")

        parts.append(f"{len(transactions)} transactions")

        elements.append(Paragraph(
            " \u00b7 ".join(parts),
            self.styles['FidraSubtitle'],
        ))

        return elements

    def _build_charts_section(self, chart_images: dict[str, bytes]) -> list:
        """Build charts section with embedded images."""
        elements = []
        elements.append(self._section_header("Charts"))

        for chart_name, image_data in chart_images.items():
            display_name = chart_name.replace('_', ' ').title()
            elements.append(Paragraph(display_name, self.styles['FidraH3']))

            img = self._create_chart_image(image_data, display_name)
            if img:
                elements.append(img)
                elements.append(Spacer(1, 6*mm))

        return elements

    def _build_monthly_breakdown(self, transactions: list[Transaction]) -> list:
        """Build monthly income/expense breakdown table with color coding."""
        elements = []
        elements.append(self._section_header("Monthly Breakdown"))

        # Filter valid transactions
        valid = [
            t for t in transactions
            if t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
        ]

        # Group by month
        monthly: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {'income': Decimal(0), 'expense': Decimal(0)}
        )
        for t in valid:
            key = t.date.strftime('%Y-%m')
            if t.type == TransactionType.INCOME:
                monthly[key]['income'] += t.amount
            else:
                monthly[key]['expense'] += t.amount

        if not monthly:
            elements.append(Paragraph(
                "<i>No transaction data available.</i>", self.styles['FidraBody']
            ))
            return elements

        # Build table data
        headers = ['Month', 'Income', 'Expenses', 'Net']
        data = [headers]

        grand_income = Decimal(0)
        grand_expense = Decimal(0)
        sorted_months = sorted(monthly.keys(), reverse=True)

        for key in sorted_months:
            m = monthly[key]
            month_date = date.fromisoformat(f"{key}-01")
            net = m['income'] - m['expense']
            sign = '+' if net >= 0 else '\u2013'
            data.append([
                month_date.strftime('%B %Y'),
                f"\u00a3{m['income']:,.2f}",
                f"\u00a3{m['expense']:,.2f}",
                f"{sign}\u00a3{abs(net):,.2f}",
            ])
            grand_income += m['income']
            grand_expense += m['expense']

        grand_net = grand_income - grand_expense
        grand_sign = '+' if grand_net >= 0 else '\u2013'
        data.append([
            'Total',
            f"\u00a3{grand_income:,.2f}",
            f"\u00a3{grand_expense:,.2f}",
            f"{grand_sign}\u00a3{abs(grand_net):,.2f}",
        ])

        # Create table
        w = self.page_width - 2 * self.margin
        table = Table(data, colWidths=[w * 0.34, w * 0.22, w * 0.22, w * 0.22])

        style_cmds = [
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), FidraColors.TABLE_HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), FidraColors.TABLE_HEADER_TEXT),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('TEXTCOLOR', (0, 1), (-1, -1), FidraColors.TEXT),
            # Alternating rows (exclude totals)
            ('ROWBACKGROUNDS', (0, 1), (-1, -2),
             [FidraColors.WHITE, FidraColors.TABLE_ROW_ALT]),
            # Borders
            ('GRID', (0, 0), (-1, -1), 0.5, FidraColors.TABLE_BORDER),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, FidraColors.DARK_BLUE),
            # Alignment
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            # Month names styled
            ('FONTNAME', (0, 1), (0, -2), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 1), (0, -2), FidraColors.DARK_BLUE),
            # Totals row
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, FidraColors.GOLD),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), FidraColors.OFF_WHITE),
            ('TEXTCOLOR', (0, -1), (0, -1), FidraColors.NAVY),
            # Vertical alignment
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        # Color-code amount columns
        for i in range(1, len(data)):
            # Income green
            style_cmds.append(('TEXTCOLOR', (1, i), (1, i), FidraColors.SUCCESS))
            # Expenses red
            style_cmds.append(('TEXTCOLOR', (2, i), (2, i), FidraColors.DANGER))
            # Net conditional
            if i < len(data) - 1:
                m = monthly[sorted_months[i - 1]]
                net = m['income'] - m['expense']
            else:
                net = grand_net
            color = FidraColors.SUCCESS if net >= 0 else FidraColors.DANGER
            style_cmds.append(('TEXTCOLOR', (3, i), (3, i), color))

        table.setStyle(TableStyle(style_cmds))
        elements.append(table)
        elements.append(Spacer(1, 4*mm))

        return elements

    def _build_category_breakdown(self, transactions: list[Transaction]) -> list:
        """Build expense category analysis table."""
        elements = []
        elements.append(self._section_header("Expenses by Category"))

        # Filter to approved/auto expenses
        expenses = [
            t for t in transactions
            if t.type == TransactionType.EXPENSE
            and t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
        ]

        if not expenses:
            elements.append(Paragraph(
                "<i>No expense data available.</i>", self.styles['FidraBody']
            ))
            return elements

        # Group by category
        cat_totals: dict[str, Decimal] = defaultdict(Decimal)
        cat_counts: dict[str, int] = defaultdict(int)
        for t in expenses:
            cat = t.category or "Uncategorized"
            cat_totals[cat] += t.amount
            cat_counts[cat] += 1

        total = sum(cat_totals.values())
        sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)

        # Build table
        headers = ['Category', 'Transactions', 'Amount', '% of Total']
        data = [headers]

        for cat, amount in sorted_cats:
            pct = (amount / total * 100) if total else Decimal(0)
            data.append([
                cat,
                str(cat_counts[cat]),
                f"\u00a3{amount:,.2f}",
                f"{pct:.1f}%",
            ])

        data.append([
            'Total',
            str(len(expenses)),
            f"\u00a3{total:,.2f}",
            '100.0%',
        ])

        # Create table
        w = self.page_width - 2 * self.margin
        table = Table(
            data,
            colWidths=[w * 0.36, w * 0.16, w * 0.26, w * 0.22],
        )

        style_cmds = [
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), FidraColors.TABLE_HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), FidraColors.TABLE_HEADER_TEXT),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('TEXTCOLOR', (0, 1), (-1, -1), FidraColors.TEXT),
            # Alternating rows (exclude totals)
            ('ROWBACKGROUNDS', (0, 1), (-1, -2),
             [FidraColors.WHITE, FidraColors.TABLE_ROW_ALT]),
            # Borders
            ('GRID', (0, 0), (-1, -1), 0.5, FidraColors.TABLE_BORDER),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, FidraColors.DARK_BLUE),
            # Alignment
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            # Category names bold
            ('FONTNAME', (0, 1), (0, -2), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 1), (0, -2), FidraColors.DARK_BLUE),
            # Amounts in danger red
            ('TEXTCOLOR', (2, 1), (2, -1), FidraColors.DANGER),
            # Percentages in light blue
            ('TEXTCOLOR', (3, 1), (3, -2), FidraColors.LIGHT_BLUE),
            # Transaction count in medium gray
            ('TEXTCOLOR', (1, 1), (1, -2), FidraColors.DARK_GRAY),
            # Totals row
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, FidraColors.GOLD),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), FidraColors.OFF_WHITE),
            ('TEXTCOLOR', (0, -1), (0, -1), FidraColors.NAVY),
            ('TEXTCOLOR', (3, -1), (3, -1), FidraColors.NAVY),
            # Vertical alignment
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]

        table.setStyle(TableStyle(style_cmds))
        elements.append(table)
        elements.append(Spacer(1, 4*mm))

        return elements

    def _add_branded_first_page(self, canvas, doc):
        """Add branded banner with logo and footer to first page."""
        canvas.saveState()

        # Top banner - navy rectangle across full width
        banner_h = 14 * mm
        banner_y = self.page_height - banner_h
        canvas.setFillColor(FidraColors.NAVY)
        canvas.rect(0, banner_y, self.page_width, banner_h, fill=1, stroke=0)

        # Logo or "FIDRA" text on the left
        if self._logo_drawing:
            from reportlab.graphics import renderPDF
            logo_x = self.margin
            logo_y = banner_y + (banner_h - self._logo_drawing.height) / 2
            renderPDF.draw(self._logo_drawing, canvas, logo_x, logo_y)
        else:
            canvas.setFont('Helvetica-Bold', 14)
            canvas.setFillColor(FidraColors.GOLD)
            canvas.drawString(self.margin, banner_y + 4*mm, "FIDRA")

        # Subtitle on the right of banner
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#8899AA'))
        canvas.drawRightString(
            self.page_width - self.margin,
            banner_y + 5*mm,
            "Financial Ledger Report",
        )

        # Thin gold accent line under banner
        canvas.setStrokeColor(FidraColors.GOLD)
        canvas.setLineWidth(0.75)
        canvas.line(0, banner_y, self.page_width, banner_y)

        # Footer
        self._draw_footer(canvas, doc)

        canvas.restoreState()

    def _add_branded_later_pages(self, canvas, doc):
        """Add minimal header and footer to subsequent pages."""
        canvas.saveState()

        # Thin dark blue line at top
        y_top = self.page_height - 10*mm
        canvas.setStrokeColor(FidraColors.DARK_BLUE)
        canvas.setLineWidth(0.5)
        canvas.line(self.margin, y_top, self.page_width - self.margin, y_top)

        # Small "FIDRA" text above the line
        canvas.setFont('Helvetica-Bold', 7)
        canvas.setFillColor(FidraColors.GOLD)
        canvas.drawString(self.margin, y_top + 2*mm, "FIDRA")

        # Page marker on the right
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(FidraColors.MEDIUM_GRAY)
        canvas.drawRightString(
            self.page_width - self.margin, y_top + 2*mm,
            "Financial Ledger Report",
        )

        # Footer
        self._draw_footer(canvas, doc)

        canvas.restoreState()

    def generate_markdown_report(
        self,
        markdown_content: str,
        output_path: Path,
        title: str = "Financial Report",
        chart_images: Optional[dict[str, bytes]] = None,
    ) -> None:
        """Generate PDF from markdown-like content.

        The markdown content provides its own headers (# Title, ## Sections)
        which are rendered with Fidra branding. No separate header is added
        to avoid duplication.

        Args:
            markdown_content: Markdown text content
            output_path: Output file path
            title: Report title (used in page banner only)
            chart_images: Optional dict of chart_name -> PNG bytes
        """
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=self.margin,
            rightMargin=self.margin,
            topMargin=3 * cm,
            bottomMargin=self.margin,
        )

        story = []

        # Parse and render markdown content directly (it provides its own title)
        story.extend(self._parse_markdown(markdown_content, chart_images))

        doc.build(story, onFirstPage=self._add_branded_first_page,
                  onLaterPages=self._add_branded_later_pages)

    def _parse_markdown(
        self,
        content: str,
        chart_images: Optional[dict[str, bytes]] = None,
    ) -> list:
        """Parse markdown-like content into ReportLab elements.

        Args:
            content: Markdown content
            chart_images: Optional dict of chart_name -> PNG bytes

        Returns:
            List of ReportLab flowable elements
        """
        import re

        elements = []
        lines = content.split('\n')

        in_table = False
        table_data = []
        figure_index = 0

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines
            if not line:
                if in_table and table_data:
                    elements.append(self._create_markdown_table(table_data))
                    table_data = []
                    in_table = False
                i += 1
                continue

            # Manual breaks
            if line in (r'\newpage', r'\newline'):
                if in_table and table_data:
                    elements.append(self._create_markdown_table(table_data))
                    table_data = []
                    in_table = False
                if line == r'\newpage':
                    elements.append(PageBreak())
                else:
                    elements.append(Spacer(1, self.styles['FidraBody'].leading))
                i += 1
                continue

            # Headers
            if line.startswith('# '):
                if in_table and table_data:
                    elements.append(self._create_markdown_table(table_data))
                    table_data = []
                    in_table = False
                elements.append(Paragraph(line[2:], self.styles['FidraTitle']))
                elements.append(HRFlowable(width="100%", thickness=2, color=FidraColors.GOLD, spaceAfter=4*mm))

            elif line.startswith('## '):
                if in_table and table_data:
                    elements.append(self._create_markdown_table(table_data))
                    table_data = []
                    in_table = False
                elements.append(self._section_header(line[3:]))

            elif line.startswith('### '):
                if in_table and table_data:
                    elements.append(self._create_markdown_table(table_data))
                    table_data = []
                    in_table = False
                elements.append(Paragraph(line[4:], self.styles['FidraH3']))

            # Horizontal rule
            elif line.startswith('---'):
                if in_table and table_data:
                    elements.append(self._create_markdown_table(table_data))
                    table_data = []
                    in_table = False
                elements.append(HRFlowable(width="100%", thickness=1, color=FidraColors.TABLE_BORDER, spaceBefore=4*mm, spaceAfter=4*mm))

            # Table
            elif line.startswith('|'):
                in_table = True
                # Skip separator rows
                if not line.replace('|', '').replace('-', '').replace(' ', ''):
                    i += 1
                    continue
                cells = [c.strip() for c in line.split('|')[1:-1]]
                table_data.append(cells)

            # Image - ![alt](chart:name) or ![alt](path)
            elif line.startswith('!['):
                if in_table and table_data:
                    elements.append(self._create_markdown_table(table_data))
                    table_data = []
                    in_table = False

                # Parse image markdown
                match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line)
                if match:
                    alt_text = match.group(1)
                    src = match.group(2)

                    # Check if it's a chart reference
                    if src.startswith('chart:') and chart_images:
                        chart_name = src[6:]  # Remove 'chart:' prefix
                        if chart_name in chart_images:
                            chart_asset = chart_images[chart_name]
                            if isinstance(chart_asset, Drawing):
                                drawing = self._create_chart_drawing(chart_asset)
                                if drawing:
                                    elements.append(drawing)
                                    figure_index += 1
                                    caption = f"Figure {figure_index}"
                                    if alt_text:
                                        caption = f"{caption}: {alt_text}"
                                    elements.append(Paragraph(caption, self.styles['FidraCaption']))
                            else:
                                img_element = self._create_chart_image(
                                    chart_asset,
                                    alt_text
                                )
                                if img_element:
                                    elements.append(img_element)
                                    figure_index += 1
                                    caption = f"Figure {figure_index}"
                                    if alt_text:
                                        caption = f"{caption}: {alt_text}"
                                    elements.append(Paragraph(caption, self.styles['FidraCaption']))

            # Bold text (simple)
            elif line.startswith('**') and line.endswith('**'):
                if in_table and table_data:
                    elements.append(self._create_markdown_table(table_data))
                    table_data = []
                    in_table = False
                elements.append(Paragraph(f"<b>{line[2:-2]}</b>", self.styles['FidraBody']))

            # Regular paragraph
            else:
                if in_table and table_data:
                    elements.append(self._create_markdown_table(table_data))
                    table_data = []
                    in_table = False
                # Handle basic inline formatting
                text = line
                text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
                text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
                text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
                elements.append(Paragraph(text, self.styles['FidraBody']))

            i += 1

        # Final table if any
        if in_table and table_data:
            elements.append(self._create_markdown_table(table_data))

        return elements

    def _create_chart_image(
        self,
        image_data: bytes,
        alt_text: str = "",
    ) -> Optional[Image]:
        """Create a ReportLab Image from PNG bytes.

        Args:
            image_data: PNG image bytes
            alt_text: Alternative text (unused but for documentation)

        Returns:
            ReportLab Image element or None
        """
        if not image_data:
            return None

        try:
            img_buffer = BytesIO(image_data)
            available_width = self.page_width - 2 * self.margin

            # Create image with maximum width
            img = Image(img_buffer, width=available_width, height=None)

            # Maintain aspect ratio - max height 150mm
            max_height = 150 * mm
            if img.drawHeight > max_height:
                scale = max_height / img.drawHeight
                img.drawWidth *= scale
                img.drawHeight = max_height

            return img
        except Exception:
            return None

    def _create_chart_drawing(self, drawing: Drawing) -> Optional[Drawing]:
        """Scale a ReportLab Drawing to fit page width and max height."""
        if not drawing:
            return None

        try:
            available_width = self.page_width - 2 * self.margin
            max_height = 150 * mm

            width = float(getattr(drawing, "width", 0) or 0)
            height = float(getattr(drawing, "height", 0) or 0)
            if width <= 0 or height <= 0:
                return drawing

            target_width = getattr(drawing, "_fidra_width", None)
            if target_width:
                target_width = min(float(target_width), available_width)
                scale = min(target_width / width, max_height / height)
            else:
                scale = min(available_width / width, max_height / height)
            drawing.scale(scale, scale)
            drawing.width = width * scale
            drawing.height = height * scale

            return drawing
        except Exception:
            return drawing

    def _create_markdown_table(self, data: list[list[str]]) -> Table:
        """Create a styled table from markdown table data.

        Converts cell strings to Paragraphs for:
        - Bold support (**text**)
        - Automatic text wrapping
        - Color-coded amounts (+£ green, -£ red)
        """
        import re as _re

        if not data:
            return Spacer(1, 0)

        num_cols = len(data[0]) if data else 0
        available_width = self.page_width - 2 * self.margin
        col_width = available_width / num_cols if num_cols else available_width

        # Cell styles
        header_style = ParagraphStyle(
            'MDTableHeader', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold',
            textColor=FidraColors.TABLE_HEADER_TEXT,
            leading=11,
        )
        cell_style = ParagraphStyle(
            'MDTableCell', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica',
            textColor=FidraColors.TEXT,
            leading=11,
        )
        cell_bold_style = ParagraphStyle(
            'MDTableCellBold', parent=cell_style,
            fontName='Helvetica-Bold',
        )
        cell_income_style = ParagraphStyle(
            'MDTableIncome', parent=cell_style,
            fontName='Helvetica-Bold',
            textColor=FidraColors.SUCCESS,
        )
        cell_expense_style = ParagraphStyle(
            'MDTableExpense', parent=cell_style,
            fontName='Helvetica-Bold',
            textColor=FidraColors.DANGER,
        )

        def _cell_to_paragraph(text: str, is_header: bool = False) -> Paragraph:
            """Convert a cell string to a styled Paragraph."""
            if is_header:
                return Paragraph(text, header_style)

            stripped = text.strip()

            # Check for amount patterns: +£... = income, -£... = expense
            if _re.match(r'^\+£', stripped):
                return Paragraph(stripped, cell_income_style)
            if _re.match(r'^-£', stripped) or _re.match(r'^\u2013£', stripped):
                return Paragraph(stripped, cell_expense_style)

            # Check if entire cell is bold: **text**
            bold_match = _re.match(r'^\*\*(.+)\*\*$', stripped)
            if bold_match:
                return Paragraph(f"<b>{bold_match.group(1)}</b>", cell_bold_style)

            # Inline bold within text
            formatted = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', stripped)
            return Paragraph(formatted, cell_style)

        # Convert all cells to Paragraphs
        para_data = []
        for row_idx, row in enumerate(data):
            is_header = (row_idx == 0)
            para_row = [_cell_to_paragraph(cell, is_header) for cell in row]
            para_data.append(para_row)

        table = Table(para_data, colWidths=[col_width] * num_cols)

        # Build style
        style_cmds = list(get_transaction_table_style().getCommands())

        # Detect totals row (last row starting with "Total" or "**Total**")
        if len(data) > 1:
            last_cell = data[-1][0].strip().replace('**', '')
            if last_cell.lower() == 'total':
                style_cmds.extend([
                    ('LINEABOVE', (0, -1), (-1, -1), 1.5, FidraColors.GOLD),
                    ('BACKGROUND', (0, -1), (-1, -1), FidraColors.OFF_WHITE),
                ])

        table.setStyle(TableStyle(style_cmds))
        return table


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_transaction_pdf(
    transactions: list[Transaction],
    output_path: Path,
    title: str = "Transaction Report",
    balances: Optional[dict[str, Decimal]] = None,
) -> None:
    """Convenience function to generate a transaction PDF.

    Args:
        transactions: List of transactions
        output_path: Output file path
        title: Report title
        balances: Optional running balances
    """
    generator = FidraPDFGenerator()
    generator.generate_transaction_report(
        transactions,
        output_path,
        title=title,
        include_summary=True,
        balances=balances,
    )


def generate_markdown_pdf(
    content: str,
    output_path: Path,
    title: str = "Financial Report",
    chart_images: Optional[dict[str, bytes]] = None,
) -> None:
    """Convenience function to generate PDF from markdown.

    Args:
        content: Markdown content
        output_path: Output file path
        title: Report title
        chart_images: Optional dict of chart_name -> PNG bytes
    """
    generator = FidraPDFGenerator()
    generator.generate_markdown_report(content, output_path, title, chart_images)
