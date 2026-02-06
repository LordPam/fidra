"""Report builder service for generating rich reports with charts and tables."""

from pathlib import Path
from datetime import date
from decimal import Decimal
from typing import Optional
from collections import defaultdict
import base64

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.services.balance import BalanceService


class ReportBuilder:
    """Builder for generating rich financial reports.

    Supports generating reports in Markdown, HTML, and PDF formats
    with embedded charts and customizable sections.
    """

    def __init__(self, balance_service: Optional[BalanceService] = None):
        """Initialize report builder.

        Args:
            balance_service: Balance service for calculations
        """
        self.balance_service = balance_service or BalanceService()

    def generate_report(
        self,
        transactions: list[Transaction],
        output_path: Path,
        format: str = "pdf",
        title: str = "Financial Report",
        include_summary: bool = True,
        include_monthly_breakdown: bool = True,
        include_category_breakdown: bool = True,
        include_transaction_table: bool = True,
        include_charts: bool = True,
        chart_images: Optional[dict[str, bytes]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> None:
        """Generate a comprehensive report.

        Args:
            transactions: Transactions to include
            output_path: Path to save report
            format: Output format ('markdown', 'html', 'pdf')
            title: Report title
            include_summary: Include summary statistics
            include_monthly_breakdown: Include monthly breakdown table
            include_category_breakdown: Include category breakdown
            include_transaction_table: Include full transaction table
            include_charts: Include embedded charts
            chart_images: Dict of chart_name -> PNG bytes (for embedding)
            start_date: Filter start date
            end_date: Filter end date
        """
        # Filter transactions by date if specified
        filtered = transactions
        if start_date:
            filtered = [t for t in filtered if t.date >= start_date]
        if end_date:
            filtered = [t for t in filtered if t.date <= end_date]

        # Sort by date
        filtered = sorted(filtered, key=lambda t: (t.date, t.created_at))

        if format == "pdf":
            # PDF uses ReportLab directly for professional branded output
            self._generate_pdf(
                filtered,
                output_path,
                title=title,
                include_summary=include_summary,
                include_monthly_breakdown=include_monthly_breakdown,
                include_category_breakdown=include_category_breakdown,
                include_transaction_table=include_transaction_table,
                chart_images=chart_images,
                start_date=start_date,
                end_date=end_date,
            )
            return

        # Markdown and HTML use the markdown pipeline
        markdown = self._generate_markdown(
            filtered,
            title=title,
            include_summary=include_summary,
            include_monthly_breakdown=include_monthly_breakdown,
            include_category_breakdown=include_category_breakdown,
            include_transaction_table=include_transaction_table,
            include_charts=include_charts,
            chart_images=chart_images,
            start_date=start_date,
            end_date=end_date,
        )

        if format == "markdown":
            output_path.write_text(markdown, encoding='utf-8')
        elif format == "html":
            html = self._markdown_to_html(markdown, title, chart_images)
            output_path.write_text(html, encoding='utf-8')
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_markdown(
        self,
        transactions: list[Transaction],
        title: str,
        include_summary: bool,
        include_monthly_breakdown: bool,
        include_category_breakdown: bool,
        include_transaction_table: bool,
        include_charts: bool,
        chart_images: Optional[dict[str, bytes]],
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> str:
        """Generate markdown report content.

        Args:
            transactions: Filtered and sorted transactions
            title: Report title
            include_summary: Include summary section
            include_monthly_breakdown: Include monthly breakdown
            include_category_breakdown: Include category breakdown
            include_transaction_table: Include transaction table
            include_charts: Include chart placeholders
            chart_images: Chart images dict
            start_date: Report start date
            end_date: Report end date

        Returns:
            Markdown string
        """
        lines = []

        # Header
        lines.append(f"# {title}\n")
        lines.append(f"**Generated**: {date.today().strftime('%Y-%m-%d')}\n")

        # Date range
        if start_date and end_date:
            lines.append(f"**Period**: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n")
        elif start_date:
            lines.append(f"**Period**: From {start_date.strftime('%Y-%m-%d')}\n")
        elif end_date:
            lines.append(f"**Period**: Up to {end_date.strftime('%Y-%m-%d')}\n")

        lines.append(f"**Total Transactions**: {len(transactions)}\n")
        lines.append("---\n")

        # Summary section
        if include_summary and transactions:
            lines.append(self._generate_summary_section(transactions))

        # Charts section
        if include_charts and chart_images:
            lines.append(self._generate_charts_section(chart_images))

        # Monthly breakdown
        if include_monthly_breakdown and transactions:
            lines.append(self._generate_monthly_breakdown(transactions))

        # Category breakdown
        if include_category_breakdown and transactions:
            lines.append(self._generate_category_breakdown(transactions))

        # Transaction table
        if include_transaction_table and transactions:
            lines.append(self._generate_transaction_table(transactions))

        return '\n'.join(lines)

    def _generate_summary_section(self, transactions: list[Transaction]) -> str:
        """Generate summary statistics section.

        Args:
            transactions: Transactions to summarize

        Returns:
            Markdown for summary section
        """
        lines = []
        lines.append("## Summary\n")

        # Calculate totals (only for approved/auto transactions)
        valid_trans = [
            t for t in transactions
            if t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
        ]

        total_income = sum(
            t.amount for t in valid_trans
            if t.type == TransactionType.INCOME
        )
        total_expenses = sum(
            t.amount for t in valid_trans
            if t.type == TransactionType.EXPENSE
        )
        net = total_income - total_expenses

        income_count = sum(1 for t in valid_trans if t.type == TransactionType.INCOME)
        expense_count = sum(1 for t in valid_trans if t.type == TransactionType.EXPENSE)

        pending_total = sum(
            t.amount for t in transactions
            if t.status == ApprovalStatus.PENDING
        )
        pending_count = sum(1 for t in transactions if t.status == ApprovalStatus.PENDING)

        # Build summary table
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Income | £{total_income:,.2f} ({income_count} transactions) |")
        lines.append(f"| Total Expenses | £{total_expenses:,.2f} ({expense_count} transactions) |")
        lines.append(f"| **Net** | **£{net:,.2f}** |")
        lines.append(f"| Pending Expenses | £{pending_total:,.2f} ({pending_count} pending) |")
        lines.append("")

        return '\n'.join(lines)

    def _generate_charts_section(self, chart_images: dict[str, bytes]) -> str:
        """Generate charts section with embedded images.

        Args:
            chart_images: Dict of chart_name -> PNG bytes

        Returns:
            Markdown with embedded images
        """
        lines = []
        lines.append("## Charts\n")

        for chart_name, _image_data in chart_images.items():
            # Use placeholder that will be replaced in HTML conversion
            # Format: ![Chart Name](chart:chart_name)
            display_name = chart_name.replace('_', ' ').title()
            lines.append(f"### {display_name}\n")
            lines.append(f"![{display_name}](chart:{chart_name})\n")

        return '\n'.join(lines)

    def _generate_monthly_breakdown(self, transactions: list[Transaction]) -> str:
        """Generate monthly breakdown table.

        Args:
            transactions: Transactions to analyze

        Returns:
            Markdown for monthly breakdown
        """
        lines = []
        lines.append("## Monthly Breakdown\n")

        # Filter to valid transactions
        valid_trans = [
            t for t in transactions
            if t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
        ]

        # Group by month
        monthly_data = defaultdict(lambda: {'income': Decimal(0), 'expense': Decimal(0)})

        for trans in valid_trans:
            month_key = trans.date.strftime('%Y-%m')
            if trans.type == TransactionType.INCOME:
                monthly_data[month_key]['income'] += trans.amount
            else:
                monthly_data[month_key]['expense'] += trans.amount

        if not monthly_data:
            lines.append("*No data available*\n")
            return '\n'.join(lines)

        # Build table
        lines.append("| Month | Income | Expenses | Net |")
        lines.append("|-------|--------|----------|-----|")

        for month_key in sorted(monthly_data.keys(), reverse=True):
            data = monthly_data[month_key]
            month_date = date.fromisoformat(f"{month_key}-01")
            month_name = month_date.strftime('%B %Y')
            net = data['income'] - data['expense']

            lines.append(
                f"| {month_name} | £{data['income']:,.2f} | £{data['expense']:,.2f} | £{net:,.2f} |"
            )

        lines.append("")
        return '\n'.join(lines)

    def _generate_category_breakdown(self, transactions: list[Transaction]) -> str:
        """Generate category breakdown table.

        Args:
            transactions: Transactions to analyze

        Returns:
            Markdown for category breakdown
        """
        lines = []
        lines.append("## Expenses by Category\n")

        # Filter to expenses only
        expenses = [
            t for t in transactions
            if t.type == TransactionType.EXPENSE
            and t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
        ]

        if not expenses:
            lines.append("*No expense data available*\n")
            return '\n'.join(lines)

        # Group by category
        category_totals = defaultdict(Decimal)
        for trans in expenses:
            category = trans.category or "Uncategorized"
            category_totals[category] += trans.amount

        total_expenses = sum(category_totals.values())

        # Sort by amount descending
        sorted_categories = sorted(
            category_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Build table
        lines.append("| Category | Amount | % of Total |")
        lines.append("|----------|--------|------------|")

        for category, amount in sorted_categories:
            percentage = (amount / total_expenses * 100) if total_expenses else 0
            lines.append(f"| {category} | £{amount:,.2f} | {percentage:.1f}% |")

        lines.append(f"| **Total** | **£{total_expenses:,.2f}** | **100%** |")
        lines.append("")

        return '\n'.join(lines)

    def _generate_transaction_table(self, transactions: list[Transaction]) -> str:
        """Generate full transaction table.

        Args:
            transactions: Transactions to list

        Returns:
            Markdown for transaction table
        """
        lines = []
        lines.append("## Transactions\n")

        if not transactions:
            lines.append("*No transactions*\n")
            return '\n'.join(lines)

        # Calculate running balances
        balances = self.balance_service.compute_running_balances(transactions)

        # Build table
        lines.append("| Date | Description | Amount | Party | Category | Balance |")
        lines.append("|------|-------------|--------|-------|----------|---------|")

        for trans in transactions:
            date_str = trans.date.strftime('%Y-%m-%d')
            category = trans.category or '-'
            party = trans.party or '-'
            balance = balances.get(str(trans.id), Decimal(0))

            # Format amount with +/- sign
            if trans.type == TransactionType.INCOME:
                amount_str = f"+£{trans.amount:,.2f}"
            else:
                amount_str = f"-£{trans.amount:,.2f}"

            lines.append(
                f"| {date_str} | {trans.description} | {amount_str} | "
                f"{party} | {category} | £{balance:,.2f} |"
            )

        lines.append("")
        return '\n'.join(lines)

    def _markdown_to_html(
        self,
        markdown_content: str,
        title: str,
        chart_images: Optional[dict[str, bytes]] = None,
    ) -> str:
        """Convert markdown to HTML with styling.

        Args:
            markdown_content: Markdown content
            title: Document title
            chart_images: Chart images to embed

        Returns:
            HTML string
        """
        try:
            import markdown
        except ImportError:
            # Fallback: wrap markdown in pre tags
            return self._simple_html_wrapper(markdown_content, title)

        # Convert markdown to HTML
        md = markdown.Markdown(extensions=['tables', 'fenced_code'])
        html_body = md.convert(markdown_content)

        # Replace chart placeholders with base64 images
        if chart_images:
            for chart_name, image_data in chart_images.items():
                placeholder = f'src="chart:{chart_name}"'
                b64_data = base64.b64encode(image_data).decode('utf-8')
                replacement = f'src="data:image/png;base64,{b64_data}"'
                html_body = html_body.replace(placeholder, replacement)

        # Build full HTML document with CSS
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        {self._get_report_css()}
    </style>
</head>
<body>
    <div class="container">
        {html_body}
    </div>
</body>
</html>
"""
        return html

    def _simple_html_wrapper(self, markdown_content: str, title: str) -> str:
        """Simple HTML wrapper for markdown (fallback).

        Args:
            markdown_content: Raw markdown
            title: Document title

        Returns:
            Basic HTML
        """
        # Escape HTML
        import html
        escaped = html.escape(markdown_content)

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: monospace; padding: 20px; }}
        pre {{ white-space: pre-wrap; }}
    </style>
</head>
<body>
    <pre>{escaped}</pre>
</body>
</html>
"""

    def _get_report_css(self) -> str:
        """Get CSS styles for the report.

        Returns:
            CSS string
        """
        return """
        @page {
            size: A4;
            margin: 2.2cm 1.8cm;
        }

        body {
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 10.5pt;
            line-height: 1.45;
            color: #1f2937;
            margin: 0;
            background: #ffffff;
        }

        .container {
            max-width: 860px;
            margin: 0 auto;
        }

        h1 {
            color: #23395B;
            font-size: 24pt;
            font-weight: 700;
            margin: 0 0 14pt 0;
            padding-bottom: 6pt;
            border-bottom: 2pt solid #23395B;
            letter-spacing: 0.2px;
        }

        h2 {
            color: #0D1F2F;
            font-size: 14pt;
            font-weight: 700;
            margin: 20pt 0 8pt 0;
            padding: 4pt 0 4pt 8pt;
            border-left: 4pt solid #BFA159;
            background: #fcfbf7;
        }

        h3 {
            color: #23395B;
            font-size: 11.5pt;
            margin: 14pt 0 6pt 0;
        }

        p {
            margin: 5pt 0;
        }

        strong {
            color: #0D1F2F;
        }

        hr {
            border: none;
            border-top: 1pt solid #d7dde6;
            margin: 14pt 0;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin: 10pt 0 14pt 0;
            font-size: 9.8pt;
            page-break-inside: avoid;
        }

        th {
            background-color: #23395B;
            color: #ffffff;
            text-align: left;
            font-weight: 700;
            font-size: 9pt;
            padding: 7pt 8pt;
            border: 1pt solid #23395B;
            letter-spacing: 0.2px;
        }

        td {
            padding: 7pt 8pt;
            border: 1pt solid #dce2ea;
            color: #1f2937;
            vertical-align: top;
        }

        tbody tr:nth-child(even) {
            background-color: #f6f3ec;
        }

        th:nth-child(n+2),
        td:nth-child(n+2) {
            text-align: right;
        }

        table:first-of-type tr:last-child td {
            border-top: 1.5pt solid #BFA159;
            font-weight: 700;
            background-color: #fcfbf7;
        }

        img {
            width: 100%;
            margin: 8pt 0 14pt 0;
            border: 1pt solid #dce2ea;
            background: #ffffff;
            page-break-inside: avoid;
        }

        blockquote {
            margin: 10pt 0;
            padding: 6pt 10pt;
            border-left: 3pt solid #BFA159;
            background: #fcfbf7;
            color: #475569;
        }

        code {
            font-family: "Courier New", monospace;
            font-size: 9pt;
            color: #23395B;
            background: #f3f4f6;
            padding: 1pt 3pt;
        }

        pre {
            font-family: "Courier New", monospace;
            font-size: 9pt;
            white-space: pre-wrap;
            background: #f8fafc;
            border: 1pt solid #dce2ea;
            padding: 8pt;
            page-break-inside: avoid;
        }
        """

    def _generate_pdf(
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
    ) -> None:
        """Generate comprehensive branded PDF using ReportLab.

        Bypasses the markdown pipeline entirely for maximum visual quality.

        Args:
            transactions: Filtered, sorted transactions
            output_path: Output PDF path
            title: Report title
            include_summary: Include summary cards
            include_monthly_breakdown: Include monthly breakdown table
            include_category_breakdown: Include category analysis
            include_transaction_table: Include full transaction table
            chart_images: Optional dict of chart_name -> PNG bytes
            start_date: Report period start
            end_date: Report period end
        """
        from fidra.services.pdf_generator import FidraPDFGenerator

        # Compute running balances for the transaction table
        balances = self.balance_service.compute_running_balances(transactions)

        generator = FidraPDFGenerator()
        generator.generate_comprehensive_report(
            transactions=transactions,
            output_path=output_path,
            title=title,
            include_summary=include_summary,
            include_monthly_breakdown=include_monthly_breakdown,
            include_category_breakdown=include_category_breakdown,
            include_transaction_table=include_transaction_table,
            chart_images=chart_images,
            start_date=start_date,
            end_date=end_date,
            balances=balances,
        )


def render_chart_to_image(chart_widget) -> bytes:
    """Render a pyqtgraph chart widget to PNG bytes.

    Args:
        chart_widget: A chart widget (BalanceTrendChart, etc.)

    Returns:
        PNG image data as bytes
    """
    try:
        import pyqtgraph.exporters as exporters
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QImage
        from PySide6.QtGui import QBrush, QColor

        # Get the plot widget
        plot_widget = getattr(chart_widget, 'plot_widget', chart_widget)

        # Force a print-friendly (light) export theme
        try:
            plot_item = plot_widget.getPlotItem()
            old_bg = plot_widget.backgroundBrush()
            plot_widget.setBackground('w')

            text_color = QColor('#111111')
            axis_pen = QColor('#333333')

            plot_item.setTitle(plot_item.titleLabel.text, color=text_color)
            for axis_name in ('left', 'bottom'):
                axis = plot_widget.getAxis(axis_name)
                axis.setTextPen(axis_pen)
                axis.setPen(axis_pen)
        except Exception:
            old_bg = None

        # Create exporter
        exporter = exporters.ImageExporter(plot_widget.plotItem)
        exporter.parameters()['width'] = 1200

        # Export to QImage
        img = exporter.export(toBytes=True)

        # Restore background if possible
        if old_bg is not None:
            plot_widget.setBackground(old_bg)

        # Convert to PNG bytes
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        img.save(buffer, "PNG")

        return bytes(buffer.data())

    except Exception:
        # Return a placeholder image or empty bytes on failure
        return b''


def render_chart_to_drawing(chart_widget, target_width: Optional[int] = None):
    """Render a pyqtgraph chart widget to a ReportLab Drawing (vector)."""
    try:
        from reportlab.lib import colors
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.linecharts import LineChart

        plot_widget = getattr(chart_widget, 'plot_widget', chart_widget)

        # Fixed, print-friendly palette
        income_color = colors.HexColor('#BFA159')
        expense_color = colors.HexColor('#23395B')
        accent_color = colors.HexColor('#4A6FA5')

        chart_name = type(chart_widget).__name__

        # Balance trend line chart
        if chart_name == 'BalanceTrendChart':
            balances = getattr(chart_widget, '_plot_balances', None)
            if not balances:
                return None

            width, height = 520, 280
            drawing = Drawing(width, height)
            chart = LineChart()
            chart.x = 30
            chart.y = 30
            chart.width = width - 60
            chart.height = height - 60
            chart.data = [balances]
            chart.lines[0].strokeColor = accent_color
            chart.lines[0].strokeWidth = 1.8
            chart.valueAxis.valueMin = min(balances + [0])
            chart.valueAxis.valueMax = max(balances + [0]) * 1.05
            chart.categoryAxis.categoryNames = [''] * len(balances)
            chart.categoryAxis.visibleTicks = 0
            chart.categoryAxis.visibleLabels = 0
            drawing.add(chart)
            if target_width:
                drawing._fidra_width = target_width
            return drawing

        # Expenses by category bar chart
        if chart_name == 'ExpensesByCategoryChart':
            categories = getattr(chart_widget, '_bar_categories', None)
            amounts = getattr(chart_widget, '_bar_amounts', None)
            if not categories or not amounts:
                return None

            width, height = 520, 280
            drawing = Drawing(width, height)
            chart = VerticalBarChart()
            chart.x = 40
            chart.y = 40
            chart.width = width - 70
            chart.height = height - 80
            chart.data = [amounts]
            chart.categoryAxis.categoryNames = categories
            chart.barWidth = 12
            chart.groupSpacing = 12
            chart.barSpacing = 6
            chart.valueAxis.valueMin = 0
            chart.valueAxis.valueMax = max(amounts) * 1.15
            chart.bars[0].fillColor = expense_color
            chart.bars[0].strokeColor = expense_color
            drawing.add(chart)
            if target_width:
                drawing._fidra_width = target_width
            return drawing

        # Income by category bar chart
        if chart_name == 'IncomeByCategoryChart':
            categories = getattr(chart_widget, '_bar_categories', None)
            amounts = getattr(chart_widget, '_bar_amounts', None)
            if not categories or not amounts:
                return None

            width, height = 520, 280
            drawing = Drawing(width, height)
            chart = VerticalBarChart()
            chart.x = 40
            chart.y = 40
            chart.width = width - 70
            chart.height = height - 80
            chart.data = [amounts]
            chart.categoryAxis.categoryNames = categories
            chart.barWidth = 12
            chart.groupSpacing = 12
            chart.barSpacing = 6
            chart.valueAxis.valueMin = 0
            chart.valueAxis.valueMax = max(amounts) * 1.15
            chart.bars[0].fillColor = income_color
            chart.bars[0].strokeColor = income_color
            drawing.add(chart)
            if target_width:
                drawing._fidra_width = target_width
            return drawing

        # Income vs expense grouped bar chart
        if chart_name == 'IncomeVsExpenseChart':
            months = getattr(chart_widget, '_month_labels', None)
            income = getattr(chart_widget, '_income_data', None)
            expense = getattr(chart_widget, '_expense_data', None)
            if not months or income is None or expense is None:
                return None

            width, height = 520, 280
            drawing = Drawing(width, height)
            chart = VerticalBarChart()
            chart.x = 40
            chart.y = 40
            chart.width = width - 70
            chart.height = height - 80
            chart.data = [income, expense]
            chart.categoryAxis.categoryNames = months
            chart.groupSpacing = 10
            chart.barSpacing = 4
            chart.barWidth = 8
            chart.valueAxis.valueMin = 0
            chart.valueAxis.valueMax = max(income + expense + [0]) * 1.15
            chart.bars[0].fillColor = income_color
            chart.bars[0].strokeColor = income_color
            chart.bars[1].fillColor = expense_color
            chart.bars[1].strokeColor = expense_color
            drawing.add(chart)
            if target_width:
                drawing._fidra_width = target_width
            return drawing

        # Fallback: try SVG export + svglib (may be raster-like)
        from io import BytesIO
        import pyqtgraph.exporters as exporters
        from svglib.svglib import svg2rlg

        exporter = exporters.SVGExporter(plot_widget.plotItem)
        svg_bytes = exporter.export(toBytes=True)
        if not svg_bytes:
            return None
        svg_io = BytesIO(svg_bytes)
        drawing = svg2rlg(svg_io)
        if drawing and target_width:
            drawing._fidra_width = target_width
        return drawing
    except Exception:
        return None
