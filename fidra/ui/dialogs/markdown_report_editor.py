"""Markdown report editor with placeholder support for custom reports."""

from typing import TYPE_CHECKING, Optional
from datetime import date
from decimal import Decimal
from pathlib import Path
from collections import defaultdict
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QMessageBox,
    QTabWidget,
    QWidget,
    QComboBox,
    QDateEdit,
    QSpinBox,
)
from PySide6.QtGui import QFont, QTextCursor

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


# Default report template
DEFAULT_TEMPLATE = """# {{title}}

**Generated**: {{date}}
**Period**: {{period}}
**Activity**: {{activity}}

---

## Summary

| Metric | Value |
|--------|-------|
| Total Income | {{total_income}} |
| Total Expenses | {{total_expenses}} |
| Net | {{net}} |
| Current Balance | {{balance}} |

---

## Monthly Breakdown

{{monthly_table}}

---

## Expenses by Category

{{category_table_expenses}}

---

## Income by Category

{{category_table_income}}

---

## Transactions

{{transactions_table}}
"""


class MarkdownReportEditor(QDialog):
    """Dialog for editing markdown reports with data placeholders.

    Features:
    - Full markdown editor
    - Sidebar with available placeholders
    - Insert placeholders with double-click
    - Live preview
    - PDF export with ReportLab (Fidra branded)
    - Customizable CSS styling
    """

    # Available placeholders and their descriptions
    PLACEHOLDERS = {
        # Basic info
        "{{title}}": "Report title",
        "{{date}}": "Generation date (YYYY-MM-DD)",
        "{{period}}": "Date range (e.g., '2024-01-01 to 2024-01-31')",
        "{{activity}}": "Selected activity name (or 'All Activities')",
        "{{sheet}}": "Selected activity (alias for {{activity}})",

        # Summary values
        "{{total_income}}": "Total income for period",
        "{{total_expenses}}": "Total expenses for period",
        "{{net}}": "Net (income - expenses)",
        "{{balance}}": "Current balance across all transactions",
        "{{transaction_count}}": "Number of transactions",
        "{{pending_count}}": "Number of pending transactions",
        "{{pending_total}}": "Total pending amount",

        # Tables
        "{{transactions_table}}": "Full transaction table with all columns",
        "{{monthly_table}}": "Monthly breakdown table",
        "{{category_table_expenses}}": "Expenses by category table",
        "{{category_table_income}}": "Income by category table",
        "{{income_table}}": "Income by source table",

        # Charts (embedded as images in PDF)
        "{{chart:balance_trend}}": "Balance trend chart (90 days)",
        "{{chart:expenses_by_category}}": "Expenses by category bar chart",
        "{{chart:income_by_category}}": "Income by category bar chart",
        "{{chart:income_vs_expense}}": "Income vs expenses comparison",
    }

    def __init__(
        self,
        context: "ApplicationContext",
        transactions: list[Transaction],
        parent=None,
    ):
        """Initialize markdown report editor.

        Args:
            context: Application context
            transactions: Transactions to use for data
            parent: Parent widget
        """
        super().__init__(parent)
        self._context = context
        self._transactions = transactions

        self._setup_ui()
        self._load_default_template()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        self.setWindowTitle("Markdown Report Editor")
        self.setModal(True)
        self.setMinimumWidth(900)
        self.setMinimumHeight(700)

        layout = QVBoxLayout(self)

        # Header with date range
        header_layout = QHBoxLayout()

        header_label = QLabel("Markdown Report Editor")
        header_label.setObjectName("page_header")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Date range
        header_layout.addWidget(QLabel("From:"))
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(date.today().replace(day=1))
        header_layout.addWidget(self.start_date)

        header_layout.addWidget(QLabel("To:"))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(date.today())
        header_layout.addWidget(self.end_date)

        header_layout.addWidget(QLabel("Activity:"))
        self.activity_combo = QComboBox()
        self.activity_combo.addItem("All", None)
        activities = sorted(
            {t.activity.strip() for t in self._transactions
             if t.activity and t.activity.strip()},
            key=str.lower,
        )
        for name in activities:
            self.activity_combo.addItem(name, name)
        header_layout.addWidget(self.activity_combo)

        all_btn = QPushButton("All")
        all_btn.setObjectName("link_button")
        all_btn.setToolTip("Expand start date to earliest available transaction")
        all_btn.clicked.connect(self._preset_all_start)
        header_layout.addWidget(all_btn)

        layout.addLayout(header_layout)

        chart_controls = QHBoxLayout()
        chart_controls.addWidget(QLabel("Chart size:"))

        self.chart_size_mode = QComboBox()
        self.chart_size_mode.addItems(["Text width", "Custom width"])
        chart_controls.addWidget(self.chart_size_mode)

        self.chart_width_spin = QSpinBox()
        self.chart_width_spin.setRange(200, 2000)
        self.chart_width_spin.setValue(520)
        self.chart_width_spin.setSuffix(" px")
        self.chart_width_spin.setEnabled(False)
        chart_controls.addWidget(self.chart_width_spin)

        self.chart_size_mode.currentIndexChanged.connect(
            lambda idx: self.chart_width_spin.setEnabled(idx == 1)
        )

        chart_controls.addStretch()
        layout.addLayout(chart_controls)

        # Main content with splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left side: Editor
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        editor_label = QLabel("Markdown Editor")
        editor_label.setObjectName("section_header")
        editor_layout.addWidget(editor_label)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Menlo", 12))
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor.setPlaceholderText("Write your markdown report here...")
        editor_layout.addWidget(self.editor)

        splitter.addWidget(editor_widget)

        # Right side: Tabs for placeholders and preview
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()

        # Placeholders tab
        placeholders_widget = QWidget()
        placeholders_layout = QVBoxLayout(placeholders_widget)

        placeholders_label = QLabel("Double-click to insert placeholder:")
        placeholders_layout.addWidget(placeholders_label)

        self.placeholders_list = QListWidget()
        self.placeholders_list.itemDoubleClicked.connect(self._insert_placeholder)
        self._populate_placeholders()
        placeholders_layout.addWidget(self.placeholders_list)

        self.tabs.addTab(placeholders_widget, "Placeholders")

        # Preview tab
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)

        preview_btn = QPushButton("Refresh Preview")
        preview_btn.clicked.connect(self._update_preview)
        preview_layout.addWidget(preview_btn)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        preview_layout.addWidget(self.preview)

        self.tabs.addTab(preview_widget, "Preview")

        # CSS tab
        css_widget = QWidget()
        css_layout = QVBoxLayout(css_widget)

        css_label = QLabel("Custom CSS (optional):")
        css_layout.addWidget(css_label)

        self.css_editor = QPlainTextEdit()
        self.css_editor.setFont(QFont("Menlo", 11))
        self.css_editor.setPlaceholderText("/* Add custom CSS here */")
        self.css_editor.setPlainText(self._get_default_css())
        css_layout.addWidget(self.css_editor)

        self.tabs.addTab(css_widget, "CSS Styling")

        right_layout.addWidget(self.tabs)
        splitter.addWidget(right_widget)

        # Set splitter sizes (60% editor, 40% right panel)
        splitter.setSizes([540, 360])

        layout.addWidget(splitter)

        # Buttons
        button_layout = QHBoxLayout()

        load_btn = QPushButton("Load Template...")
        load_btn.clicked.connect(self._load_template)
        button_layout.addWidget(load_btn)

        save_btn = QPushButton("Save Template...")
        save_btn.clicked.connect(self._save_template)
        button_layout.addWidget(save_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        export_md_btn = QPushButton("Export Markdown")
        export_md_btn.clicked.connect(self._export_markdown)
        button_layout.addWidget(export_md_btn)

        export_pdf_btn = QPushButton("Export PDF")
        export_pdf_btn.setObjectName("primary_button")
        export_pdf_btn.clicked.connect(self._export_pdf)
        button_layout.addWidget(export_pdf_btn)

        layout.addLayout(button_layout)

    def _populate_placeholders(self) -> None:
        """Populate the placeholders list."""
        for placeholder, description in self.PLACEHOLDERS.items():
            item = QListWidgetItem(f"{placeholder}\n  {description}")
            item.setData(Qt.UserRole, placeholder)
            self.placeholders_list.addItem(item)

    def _insert_placeholder(self, item: QListWidgetItem) -> None:
        """Insert placeholder at cursor position.

        Args:
            item: The clicked list item
        """
        placeholder = item.data(Qt.UserRole)
        cursor = self.editor.textCursor()
        cursor.insertText(placeholder)
        self.editor.setFocus()

    def _load_default_template(self) -> None:
        """Load the default report template."""
        self.editor.setPlainText(DEFAULT_TEMPLATE)

    def _load_template(self) -> None:
        """Load a template from file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Template",
            "",
            "Markdown Files (*.md);;Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                content = Path(file_path).read_text(encoding='utf-8')
                self.editor.setPlainText(content)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load template: {e}")

    def _save_template(self) -> None:
        """Save current content as a template."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Template",
            "report_template.md",
            "Markdown Files (*.md);;Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                Path(file_path).write_text(
                    self.editor.toPlainText(),
                    encoding='utf-8'
                )
                QMessageBox.information(self, "Saved", f"Template saved to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save template: {e}")

    def _get_filtered_transactions(self) -> list[Transaction]:
        """Get transactions filtered by date range and activity.

        Returns:
            Filtered transaction list
        """
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()
        selected_activity = self.activity_combo.currentData()

        return [
            t for t in self._transactions
            if start <= t.date <= end
            and (selected_activity is None or (t.activity and t.activity.strip() == selected_activity))
        ]

    def _preset_all_start(self) -> None:
        """Set start date to earliest available transaction in current activity selection."""
        selected_activity = self.activity_combo.currentData()
        candidates = [
            t for t in self._transactions
            if selected_activity is None or (t.activity and t.activity.strip() == selected_activity)
        ]
        if not candidates:
            return

        earliest = min(t.date for t in candidates)
        self.start_date.setDate(earliest)

    def _process_placeholders(self, content: str) -> str:
        """Replace placeholders with actual data.

        Args:
            content: Markdown content with placeholders

        Returns:
            Content with placeholders replaced
        """
        transactions = self._get_filtered_transactions()
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()
        selected_activity = self.activity_combo.currentData()
        activity_label = selected_activity or "All Activities"

        # Valid transactions (not planned/rejected)
        valid = [
            t for t in transactions
            if t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
        ]

        # Calculate values
        total_income = sum(
            t.amount for t in valid
            if t.type == TransactionType.INCOME
        )
        total_expenses = sum(
            t.amount for t in valid
            if t.type == TransactionType.EXPENSE
        )
        net = total_income - total_expenses
        balance_source = [
            t for t in self._transactions
            if selected_activity is None or (t.activity and t.activity.strip() == selected_activity)
        ]
        balance = self._context.balance_service.compute_total(balance_source)

        pending = [t for t in transactions if t.status == ApprovalStatus.PENDING]
        pending_total = sum(t.amount for t in pending)

        # Replace basic placeholders
        replacements = {
            "{{title}}": "Financial Report",
            "{{date}}": date.today().strftime('%Y-%m-%d'),
            "{{period}}": f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
            "{{sheet}}": activity_label,
            "{{activity}}": activity_label,
            "{{total_income}}": f"£{total_income:,.2f}",
            "{{total_expenses}}": f"£{total_expenses:,.2f}",
            "{{net}}": f"£{net:,.2f}",
            "{{balance}}": f"£{balance:,.2f}",
            "{{transaction_count}}": str(len(transactions)),
            "{{pending_count}}": str(len(pending)),
            "{{pending_total}}": f"£{pending_total:,.2f}",
        }

        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)

        # Replace table placeholders
        content = content.replace("{{transactions_table}}", self._generate_transactions_table(valid))
        content = content.replace("{{monthly_table}}", self._generate_monthly_table(valid))
        expenses_table = self._generate_category_expenses_table(valid)
        content = content.replace("{{category_table_expenses}}", expenses_table)
        content = content.replace("{{category_table}}", expenses_table)
        content = content.replace("{{category_table_income}}", self._generate_category_income_table(valid))
        content = content.replace("{{income_table}}", self._generate_income_table(valid))

        # Chart placeholders - mark for later replacement in HTML
        # These will be replaced with actual images during PDF generation
        content = content.replace(
            "{{chart:balance_trend}}",
            "![Balance Trend](chart:balance_trend)"
        )
        content = content.replace(
            "{{chart:expenses_by_category}}",
            "![Expenses by Category](chart:expenses_by_category)"
        )
        content = content.replace(
            "{{chart:income_by_category}}",
            "![Income by Category](chart:income_by_category)"
        )
        content = content.replace(
            "{{chart:income_vs_expense}}",
            "![Income vs Expenses](chart:income_vs_expense)"
        )

        return content

    def _generate_transactions_table(self, transactions: list[Transaction]) -> str:
        """Generate markdown table of transactions.

        Args:
            transactions: Transactions to include

        Returns:
            Markdown table string
        """
        if not transactions:
            return "*No transactions*"

        # Calculate running balances
        # Normalize created_at for sorting (handle mix of tz-aware and tz-naive)
        def sort_key(t):
            created = t.created_at
            if created and created.tzinfo is not None:
                created = created.replace(tzinfo=None)
            return (t.date, created)
        sorted_trans = sorted(transactions, key=sort_key)
        balances = self._context.balance_service.compute_running_balances(sorted_trans)

        lines = []
        lines.append("| Date | Description | Amount | Party | Category | Balance |")
        lines.append("|------|-------------|--------|-------|----------|---------|")

        for t in sorted_trans:
            amount = f"+£{t.amount:,.2f}" if t.type == TransactionType.INCOME else f"-£{t.amount:,.2f}"
            balance = balances.get(str(t.id), Decimal(0))
            category = t.category or "-"
            party = t.party or "-"

            lines.append(
                f"| {t.date.strftime('%Y-%m-%d')} | {t.description} | {amount} | "
                f"{party} | {category} | £{balance:,.2f} |"
            )

        return '\n'.join(lines)

    def _generate_monthly_table(self, transactions: list[Transaction]) -> str:
        """Generate monthly breakdown table.

        Args:
            transactions: Transactions to analyze

        Returns:
            Markdown table string
        """
        if not transactions:
            return "*No data*"

        monthly = defaultdict(lambda: {'income': Decimal(0), 'expense': Decimal(0)})

        for t in transactions:
            month_key = t.date.strftime('%Y-%m')
            if t.type == TransactionType.INCOME:
                monthly[month_key]['income'] += t.amount
            else:
                monthly[month_key]['expense'] += t.amount

        lines = []
        lines.append("| Month | Income | Expenses | Net |")
        lines.append("|-------|--------|----------|-----|")

        for month_key in sorted(monthly.keys(), reverse=True):
            data = monthly[month_key]
            month_date = date.fromisoformat(f"{month_key}-01")
            month_name = month_date.strftime('%B %Y')
            net = data['income'] - data['expense']

            lines.append(
                f"| {month_name} | £{data['income']:,.2f} | £{data['expense']:,.2f} | £{net:,.2f} |"
            )

        return '\n'.join(lines)

    def _generate_category_expenses_table(self, transactions: list[Transaction]) -> str:
        """Generate expense category breakdown table.

        Args:
            transactions: Transactions to analyze

        Returns:
            Markdown table string
        """
        return self._generate_category_table_for_type(
            transactions,
            TransactionType.EXPENSE,
            "No expense data",
        )

    def _generate_category_income_table(self, transactions: list[Transaction]) -> str:
        """Generate income category breakdown table.

        Args:
            transactions: Transactions to analyze

        Returns:
            Markdown table string
        """
        return self._generate_category_table_for_type(
            transactions,
            TransactionType.INCOME,
            "No income data",
        )

    def _generate_category_table_for_type(
        self,
        transactions: list[Transaction],
        trans_type: TransactionType,
        empty_label: str,
    ) -> str:
        """Generate category breakdown table for a transaction type."""
        items = [t for t in transactions if t.type == trans_type]

        if not items:
            return f"*{empty_label}*"

        category_totals = defaultdict(Decimal)
        for t in items:
            category = t.category or "Uncategorized"
            category_totals[category] += t.amount

        total = sum(category_totals.values())
        sorted_cats = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)

        lines = []
        lines.append("| Category | Amount | % of Total |")
        lines.append("|----------|--------|------------|")

        for category, amount in sorted_cats:
            pct = (amount / total * 100) if total else 0
            lines.append(f"| {category} | £{amount:,.2f} | {pct:.1f}% |")

        lines.append(f"| **Total** | **£{total:,.2f}** | **100%** |")

        return '\n'.join(lines)

    def _generate_income_table(self, transactions: list[Transaction]) -> str:
        """Generate income by source table.

        Args:
            transactions: Transactions to analyze

        Returns:
            Markdown table string
        """
        income = [t for t in transactions if t.type == TransactionType.INCOME]

        if not income:
            return "*No income data*"

        source_totals = defaultdict(Decimal)
        for t in income:
            source = t.party or t.category or "Other"
            source_totals[source] += t.amount

        total = sum(source_totals.values())
        sorted_sources = sorted(source_totals.items(), key=lambda x: x[1], reverse=True)

        lines = []
        lines.append("| Source | Amount | % of Total |")
        lines.append("|--------|--------|------------|")

        for source, amount in sorted_sources:
            pct = (amount / total * 100) if total else 0
            lines.append(f"| {source} | £{amount:,.2f} | {pct:.1f}% |")

        lines.append(f"| **Total** | **£{total:,.2f}** | **100%** |")

        return '\n'.join(lines)

    def _update_preview(self) -> None:
        """Update the preview pane with processed content."""
        content = self.editor.toPlainText()
        processed = self._process_placeholders(content)
        self.preview.setMarkdown(processed)

    def _get_default_css(self) -> str:
        """Get default CSS for PDF styling.

        Returns:
            CSS string
        """
        return """/* Fidra Report Stylesheet */

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #333;
    max-width: 800px;
    margin: 0 auto;
    padding: 40px 20px;
}

h1 {
    color: #2c3e50;
    font-size: 24pt;
    border-bottom: 3px solid #3498db;
    padding-bottom: 10px;
    margin-bottom: 20px;
}

h2 {
    color: #34495e;
    font-size: 16pt;
    border-bottom: 1px solid #bdc3c7;
    padding-bottom: 8px;
    margin-top: 30px;
    margin-bottom: 15px;
}

h3 {
    color: #7f8c8d;
    font-size: 13pt;
    margin-top: 20px;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    font-size: 10pt;
}

th {
    background-color: #3498db;
    color: white;
    font-weight: 600;
    padding: 12px 10px;
    text-align: left;
    border: 1px solid #2980b9;
}

td {
    padding: 10px;
    border: 1px solid #ddd;
}

tr:nth-child(even) {
    background-color: #f8f9fa;
}

tr:hover {
    background-color: #e8f4f8;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 20px auto;
    border: 1px solid #ddd;
    border-radius: 4px;
}

hr {
    border: none;
    border-top: 1px solid #eee;
    margin: 25px 0;
}

strong {
    color: #2c3e50;
}

/* Print optimizations */
@page {
    size: A4;
    margin: 2cm;
}

@media print {
    body {
        max-width: 100%;
        padding: 0;
    }

    table {
        page-break-inside: auto;
    }

    tr {
        page-break-inside: avoid;
    }

    h2 {
        page-break-after: avoid;
    }
}
"""

    def _export_markdown(self) -> None:
        """Export processed markdown to file."""
        content = self.editor.toPlainText()
        processed = self._process_placeholders(content)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Markdown",
            f"report_{date.today().strftime('%Y%m%d')}.md",
            "Markdown Files (*.md);;All Files (*)"
        )

        if file_path:
            try:
                Path(file_path).write_text(processed, encoding='utf-8')
                QMessageBox.information(
                    self,
                    "Exported",
                    f"Markdown exported to:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export: {e}")

    def _export_pdf(self) -> None:
        """Export to professional branded PDF using ReportLab."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            f"report_{date.today().strftime('%Y%m%d')}.pdf",
            "PDF Files (*.pdf);;All Files (*)"
        )

        if not file_path:
            return

        try:
            from pathlib import Path
            from fidra.services.pdf_generator import FidraPDFGenerator

            # Process content with placeholders
            content = self.editor.toPlainText()
            processed = self._process_placeholders(content)
            chart_images = self._render_chart_images(processed)

            # Generate professional branded PDF
            generator = FidraPDFGenerator()
            generator.generate_markdown_report(
                processed,
                Path(file_path),
                title="Financial Report",
                chart_images=chart_images
            )

            QMessageBox.information(
                self,
                "PDF Exported",
                f"Report saved to:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to generate PDF:\n{e}"
            )

    def _markdown_to_html(self, markdown_content: str) -> str:
        """Convert markdown to HTML.

        Args:
            markdown_content: Markdown text

        Returns:
            HTML string
        """
        try:
            import markdown
            md = markdown.Markdown(extensions=['tables', 'fenced_code'])
            return md.convert(markdown_content)
        except ImportError:
            import html
            return f"<pre>{html.escape(markdown_content)}</pre>"

    def _embed_charts(self, html_content: str) -> str:
        """Render and embed chart images in HTML.

        Args:
            html_content: HTML with chart placeholders

        Returns:
            HTML with embedded base64 images
        """
        import base64

        transactions = self._get_filtered_transactions()
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()

        # Check for chart placeholders
        charts_to_render = []
        if 'chart:balance_trend' in html_content:
            charts_to_render.append('balance_trend')
        if 'chart:expenses_by_category' in html_content:
            charts_to_render.append('expenses_by_category')
        if 'chart:income_by_category' in html_content:
            charts_to_render.append('income_by_category')
        if 'chart:income_vs_expense' in html_content:
            charts_to_render.append('income_vs_expense')

        if not charts_to_render:
            return html_content

        # Import chart components
        from fidra.ui.components.charts import (
            BalanceTrendChart,
            ExpensesByCategoryChart,
            IncomeByCategoryChart,
            IncomeVsExpenseChart,
        )
        from fidra.services.report_builder import render_chart_to_image

        # Render each chart
        for chart_name in charts_to_render:
            try:
                if chart_name == 'balance_trend':
                    chart = BalanceTrendChart()
                    chart.update_data(transactions, self._context.balance_service, days=90)
                elif chart_name == 'expenses_by_category':
                    chart = ExpensesByCategoryChart()
                    chart.update_data(transactions, start_date=start, end_date=end)
                elif chart_name == 'income_by_category':
                    chart = IncomeByCategoryChart()
                    chart.update_data(transactions, start_date=start, end_date=end)
                elif chart_name == 'income_vs_expense':
                    chart = IncomeVsExpenseChart()
                    chart.update_data(transactions, months=6)
                else:
                    continue

                # Render to image
                chart.resize(700, 400)
                chart.show()
                chart.hide()

                img_data = render_chart_to_image(chart)
                chart.deleteLater()

                if img_data:
                    b64 = base64.b64encode(img_data).decode('utf-8')
                    placeholder = f'src="chart:{chart_name}"'
                    replacement = f'src="data:image/png;base64,{b64}"'
                    html_content = html_content.replace(placeholder, replacement)

            except Exception:
                # Skip chart on error
                pass

        return html_content

    def _render_chart_images(self, markdown_content: str) -> dict[str, bytes]:
        """Render chart images referenced by markdown placeholders."""
        charts_to_render = []
        if 'chart:balance_trend' in markdown_content:
            charts_to_render.append('balance_trend')
        if 'chart:expenses_by_category' in markdown_content:
            charts_to_render.append('expenses_by_category')
        if 'chart:income_by_category' in markdown_content:
            charts_to_render.append('income_by_category')
        if 'chart:income_vs_expense' in markdown_content:
            charts_to_render.append('income_vs_expense')

        if not charts_to_render:
            return {}

        from fidra.ui.components.charts import (
            BalanceTrendChart,
            ExpensesByCategoryChart,
            IncomeByCategoryChart,
            IncomeVsExpenseChart,
        )
        from fidra.services.report_builder import render_chart_to_drawing

        transactions = self._get_filtered_transactions()
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()

        images: dict[str, bytes] = {}
        width_override = None
        if self.chart_size_mode.currentIndex() == 1:
            width_override = self.chart_width_spin.value()
        for chart_name in charts_to_render:
            try:
                if chart_name == 'balance_trend':
                    chart = BalanceTrendChart()
                    chart.update_data(transactions, self._context.balance_service, days=90)
                elif chart_name == 'expenses_by_category':
                    chart = ExpensesByCategoryChart()
                    chart.update_data(transactions, start_date=start, end_date=end)
                elif chart_name == 'income_by_category':
                    chart = IncomeByCategoryChart()
                    chart.update_data(transactions, start_date=start, end_date=end)
                elif chart_name == 'income_vs_expense':
                    chart = IncomeVsExpenseChart()
                    chart.update_data(transactions, months=6)
                else:
                    continue

                chart.resize(700, 400)
                chart.show()
                chart.hide()

                drawing = render_chart_to_drawing(chart, target_width=width_override)
                chart.deleteLater()

                if drawing:
                    images[chart_name] = drawing
            except Exception:
                continue

        return images
