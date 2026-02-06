"""Report builder dialog for creating custom reports with charts."""

from typing import TYPE_CHECKING, Optional
from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QGroupBox,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QProgressDialog,
)

from fidra.domain.models import Transaction
from fidra.services.report_builder import ReportBuilder, render_chart_to_image
from fidra.ui.components.charts import (
    BalanceTrendChart,
    ExpensesByCategoryChart,
    IncomeVsExpenseChart,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class ReportBuilderDialog(QDialog):
    """Dialog for building custom financial reports.

    Features:
    - Title and date range configuration
    - Section selection (summary, monthly, category, transactions)
    - Chart inclusion options
    - Format selection (PDF, HTML, Markdown)
    - Live preview of included charts
    """

    def __init__(
        self,
        context: "ApplicationContext",
        transactions: list[Transaction],
        parent=None,
    ):
        """Initialize report builder dialog.

        Args:
            context: Application context
            transactions: Transactions to include in report
            parent: Parent widget
        """
        super().__init__(parent)
        self._context = context
        self._transactions = transactions
        self._report_builder = ReportBuilder(context.balance_service)

        # Chart widgets for rendering
        self._balance_chart = None
        self._category_chart = None
        self._income_expense_chart = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        self.setWindowTitle("Report Builder")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header
        header = QLabel("Build Custom Report")
        header.setObjectName("page_header")
        layout.addWidget(header)

        # Report title
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Report Title:"))
        self.title_edit = QLineEdit("Financial Report")
        title_layout.addWidget(self.title_edit, 1)
        layout.addLayout(title_layout)

        # Date range group
        date_group = QGroupBox("Date Range")
        date_group_layout = QVBoxLayout(date_group)

        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("From:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        # Default to first of current month
        self.start_date_edit.setDate(date.today().replace(day=1))
        date_layout.addWidget(self.start_date_edit)

        date_layout.addWidget(QLabel("To:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(date.today())
        date_layout.addWidget(self.end_date_edit)
        date_layout.addStretch()
        date_group_layout.addLayout(date_layout)

        sheet_layout = QHBoxLayout()
        sheet_layout.addWidget(QLabel("Sheet:"))
        self.sheet_combo = QComboBox()
        self.sheet_combo.addItem("All Sheets", None)
        for sheet_name in self._get_ordered_sheet_names():
            self.sheet_combo.addItem(sheet_name, sheet_name)
        sheet_layout.addWidget(self.sheet_combo, 1)

        all_btn = QPushButton("All")
        all_btn.setObjectName("link_button")
        all_btn.setToolTip("Expand start date to earliest available transaction")
        all_btn.clicked.connect(self._preset_all_start)
        sheet_layout.addWidget(all_btn)
        sheet_layout.addStretch()
        date_group_layout.addLayout(sheet_layout)

        layout.addWidget(date_group)

        # Sections group
        sections_group = QGroupBox("Include Sections")
        sections_layout = QVBoxLayout(sections_group)

        self.include_summary_cb = QCheckBox("Summary Statistics")
        self.include_summary_cb.setChecked(True)
        sections_layout.addWidget(self.include_summary_cb)

        self.include_monthly_cb = QCheckBox("Monthly Breakdown Table")
        self.include_monthly_cb.setChecked(True)
        sections_layout.addWidget(self.include_monthly_cb)

        self.include_category_cb = QCheckBox("Expenses by Category")
        self.include_category_cb.setChecked(True)
        sections_layout.addWidget(self.include_category_cb)

        self.include_transactions_cb = QCheckBox("Full Transaction Table")
        self.include_transactions_cb.setChecked(False)
        self.include_transactions_cb.setToolTip(
            "Include full list of transactions with running balance"
        )
        sections_layout.addWidget(self.include_transactions_cb)

        layout.addWidget(sections_group)

        # Charts group
        charts_group = QGroupBox("Include Charts")
        charts_layout = QVBoxLayout(charts_group)

        self.include_balance_chart_cb = QCheckBox("Balance Trend (90-day line chart)")
        self.include_balance_chart_cb.setChecked(True)
        charts_layout.addWidget(self.include_balance_chart_cb)

        self.include_category_chart_cb = QCheckBox("Expenses by Category (bar chart)")
        self.include_category_chart_cb.setChecked(True)
        charts_layout.addWidget(self.include_category_chart_cb)

        self.include_income_expense_chart_cb = QCheckBox("Income vs Expenses (6-month comparison)")
        self.include_income_expense_chart_cb.setChecked(True)
        charts_layout.addWidget(self.include_income_expense_chart_cb)

        layout.addWidget(charts_group)

        # Format selection
        format_group = QGroupBox("Output Format")
        format_layout = QHBoxLayout(format_group)

        format_layout.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PDF", "HTML", "Markdown"])
        format_layout.addWidget(self.format_combo)

        format_layout.addStretch()
        layout.addWidget(format_group)

        # Transaction count info
        count_label = QLabel(f"Transactions available: {len(self._transactions)}")
        count_label.setObjectName("secondary_text")
        layout.addWidget(count_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        preview_btn = QPushButton("Preview...")
        preview_btn.clicked.connect(self._on_preview)
        button_layout.addWidget(preview_btn)

        generate_btn = QPushButton("Generate Report")
        generate_btn.setObjectName("primary_button")
        generate_btn.clicked.connect(self._on_generate)
        button_layout.addWidget(generate_btn)

        layout.addLayout(button_layout)

    def _get_filtered_transactions(self) -> list[Transaction]:
        """Get transactions filtered by date range.

        Returns:
            Filtered transaction list
        """
        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()

        selected_sheet = self.sheet_combo.currentData()

        return [
            t for t in self._transactions
            if start_date <= t.date <= end_date
            and (selected_sheet is None or t.sheet == selected_sheet)
        ]

    def _get_ordered_sheet_names(self) -> list[str]:
        """Get real sheet names in saved dropdown order."""
        sheets = [
            s for s in self._context.state.sheets.value
            if not s.is_virtual and not s.is_planned
        ]

        saved_order = self._context.settings.sheet_order
        order_map = {name: idx for idx, name in enumerate(saved_order)}
        sheets.sort(key=lambda s: (order_map.get(s.name, len(order_map)), s.name.lower()))
        return [s.name for s in sheets]

    def _preset_all_start(self) -> None:
        """Set start date to earliest available transaction in current sheet selection."""
        selected_sheet = self.sheet_combo.currentData()
        candidates = [
            t for t in self._transactions
            if selected_sheet is None or t.sheet == selected_sheet
        ]
        if not candidates:
            return

        earliest = min(t.date for t in candidates)
        self.start_date_edit.setDate(earliest)

    def _render_chart_images(self) -> dict[str, bytes]:
        """Render selected charts to images.

        Returns:
            Dict of chart_name -> PNG bytes
        """
        images = {}
        transactions = self._get_filtered_transactions()
        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()

        if self.include_balance_chart_cb.isChecked():
            # Create and render balance chart
            chart = BalanceTrendChart()
            chart.update_data(
                transactions,
                self._context.balance_service,
                days=90
            )
            chart.resize(700, 400)
            chart.show()
            chart.hide()  # Render offscreen
            img_data = render_chart_to_image(chart)
            if img_data:
                images['balance_trend'] = img_data
            chart.deleteLater()

        if self.include_category_chart_cb.isChecked():
            # Create and render category chart
            chart = ExpensesByCategoryChart()
            chart.update_data(
                transactions,
                start_date=start_date,
                end_date=end_date
            )
            chart.resize(700, 400)
            chart.show()
            chart.hide()
            img_data = render_chart_to_image(chart)
            if img_data:
                images['expenses_by_category'] = img_data
            chart.deleteLater()

        if self.include_income_expense_chart_cb.isChecked():
            # Create and render income vs expense chart
            chart = IncomeVsExpenseChart()
            chart.update_data(transactions, months=6)
            chart.resize(700, 400)
            chart.show()
            chart.hide()
            img_data = render_chart_to_image(chart)
            if img_data:
                images['income_vs_expense'] = img_data
            chart.deleteLater()

        return images

    def _on_preview(self) -> None:
        """Handle preview button click."""
        filtered = self._get_filtered_transactions()

        if not filtered:
            QMessageBox.warning(
                self,
                "No Data",
                "No transactions found in the selected date range."
            )
            return

        # Generate preview text
        preview_lines = [
            f"Report Preview: {self.title_edit.text()}",
            f"Date Range: {self.start_date_edit.date().toString('yyyy-MM-dd')} to {self.end_date_edit.date().toString('yyyy-MM-dd')}",
            f"Transactions: {len(filtered)}",
            "",
            "Sections to include:",
        ]

        if self.include_summary_cb.isChecked():
            preview_lines.append("  - Summary Statistics")
        if self.include_monthly_cb.isChecked():
            preview_lines.append("  - Monthly Breakdown")
        if self.include_category_cb.isChecked():
            preview_lines.append("  - Category Breakdown")
        if self.include_transactions_cb.isChecked():
            preview_lines.append("  - Full Transaction Table")

        preview_lines.append("")
        preview_lines.append("Charts to include:")

        if self.include_balance_chart_cb.isChecked():
            preview_lines.append("  - Balance Trend Chart")
        if self.include_category_chart_cb.isChecked():
            preview_lines.append("  - Expenses by Category Chart")
        if self.include_income_expense_chart_cb.isChecked():
            preview_lines.append("  - Income vs Expenses Chart")

        preview_lines.append("")
        preview_lines.append(f"Output format: {self.format_combo.currentText()}")

        QMessageBox.information(
            self,
            "Report Preview",
            "\n".join(preview_lines)
        )

    def _on_generate(self) -> None:
        """Handle generate button click."""
        filtered = self._get_filtered_transactions()

        if not filtered:
            QMessageBox.warning(
                self,
                "No Data",
                "No transactions found in the selected date range."
            )
            return

        # Get output format
        format_text = self.format_combo.currentText().lower()
        if format_text == "markdown":
            extension = "md"
        elif format_text == "html":
            extension = "html"
        else:
            extension = "pdf"

        # Get output file
        default_filename = f"report_{date.today().strftime('%Y%m%d')}.{extension}"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Report",
            default_filename,
            f"{format_text.upper()} Files (*.{extension});;All Files (*)"
        )

        if not file_path:
            return

        # Show progress
        progress = QProgressDialog("Generating report...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(10)

        try:
            # Render charts
            progress.setLabelText("Rendering charts...")
            progress.setValue(30)

            include_charts = (
                self.include_balance_chart_cb.isChecked() or
                self.include_category_chart_cb.isChecked() or
                self.include_income_expense_chart_cb.isChecked()
            )

            chart_images = {}
            if include_charts:
                chart_images = self._render_chart_images()

            progress.setValue(60)

            # Generate report
            progress.setLabelText("Generating report...")

            self._report_builder.generate_report(
                transactions=filtered,
                output_path=Path(file_path),
                format=format_text,
                title=self.title_edit.text(),
                include_summary=self.include_summary_cb.isChecked(),
                include_monthly_breakdown=self.include_monthly_cb.isChecked(),
                include_category_breakdown=self.include_category_cb.isChecked(),
                include_transaction_table=self.include_transactions_cb.isChecked(),
                include_charts=include_charts,
                chart_images=chart_images if chart_images else None,
                start_date=self.start_date_edit.date().toPython(),
                end_date=self.end_date_edit.date().toPython(),
            )

            progress.setValue(100)
            progress.close()

            QMessageBox.information(
                self,
                "Report Generated",
                f"Report successfully saved to:\n{file_path}"
            )

            self.accept()

        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to generate report:\n{e}"
            )
