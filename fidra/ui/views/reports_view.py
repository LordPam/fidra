"""Reports view - generate reports with charts and export options."""

from typing import TYPE_CHECKING
from datetime import date, timedelta
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDateEdit,
    QComboBox,
    QFrame,
    QScrollArea,
    QStackedWidget,
    QSizePolicy,
    QApplication,
    QFileDialog,
    QMessageBox,
)

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.ui.dialogs.markdown_report_editor import MarkdownReportEditor
from fidra.ui.components.charts import (
    BalanceTrendChart,
    ExpensesByCategoryChart,
    IncomeByCategoryChart,
    IncomeVsExpenseChart,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class StatCard(QFrame):
    """A compact stat card for displaying a single metric."""

    def __init__(self, title: str, value: str = "£0.00", color: str = "default", parent=None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        self.setProperty("color", color)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("stat_card_title")
        layout.addWidget(self.title_label)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("stat_card_value")
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class ReportsView(QWidget):
    """Reports view for generating financial reports.

    Clean, modern design with:
    - Inline filter toolbar at top
    - Summary stat cards
    - Large chart area
    - Simple export bar at bottom
    """

    def __init__(self, context: "ApplicationContext", parent=None):
        """Initialize reports view.

        Args:
            context: Application context
            parent: Parent widget
        """
        super().__init__(parent)
        self._context = context
        self._filtered_transactions = []
        self._setup_ui()
        self._connect_signals()

        # Initial load
        self._apply_filters()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ===== HEADER ROW =====
        header_row = QHBoxLayout()

        title = QLabel("Reports")
        title.setObjectName("page_header")
        header_row.addWidget(title)

        header_row.addStretch()

        # Build custom report button
        build_btn = QPushButton("Build Custom Report")
        build_btn.setObjectName("primary_button")
        build_btn.clicked.connect(self._on_build_report)
        header_row.addWidget(build_btn)

        layout.addLayout(header_row)

        # ===== FILTER BAR =====
        filter_bar = QFrame()
        filter_bar.setObjectName("filter_bar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(12, 8, 12, 8)
        filter_layout.setSpacing(12)

        # Date range
        filter_layout.addWidget(QLabel("From:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("dd MMM yyyy")
        # Default: 3 months ago
        self.start_date_edit.setDate(date.today() - timedelta(days=90))
        self.start_date_edit.dateChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.start_date_edit)

        filter_layout.addWidget(QLabel("To:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("dd MMM yyyy")
        self.end_date_edit.setDate(date.today())
        self.end_date_edit.dateChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.end_date_edit)

        filter_layout.addSpacing(20)

        # Activity filter
        filter_layout.addWidget(QLabel("Activity:"))
        self.activity_combo = QComboBox()
        self.activity_combo.setMinimumWidth(120)
        self._populate_activities()
        self.activity_combo.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.activity_combo)

        filter_layout.addStretch()

        # Quick presets
        preset_label = QLabel("Quick:")
        preset_label.setObjectName("secondary_text")
        filter_layout.addWidget(preset_label)

        this_month_btn = QPushButton("This Month")
        this_month_btn.setObjectName("link_button")
        this_month_btn.clicked.connect(self._preset_this_month)
        filter_layout.addWidget(this_month_btn)

        last_month_btn = QPushButton("Last Month")
        last_month_btn.setObjectName("link_button")
        last_month_btn.clicked.connect(self._preset_last_month)
        filter_layout.addWidget(last_month_btn)

        ytd_btn = QPushButton("Year to Date")
        ytd_btn.setObjectName("link_button")
        ytd_btn.clicked.connect(self._preset_ytd)
        filter_layout.addWidget(ytd_btn)

        fy_btn = QPushButton("Financial Year")
        fy_btn.setObjectName("link_button")
        fy_btn.clicked.connect(self._preset_financial_year)
        filter_layout.addWidget(fy_btn)

        all_btn = QPushButton("All")
        all_btn.setObjectName("link_button")
        all_btn.clicked.connect(self._preset_all)
        filter_layout.addWidget(all_btn)

        layout.addWidget(filter_bar)

        # ===== STATS ROW =====
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self.transactions_card = StatCard("Transactions", "0")
        stats_row.addWidget(self.transactions_card)

        self.income_card = StatCard("Total Income", "£0.00", "danger")
        stats_row.addWidget(self.income_card)

        self.expense_card = StatCard("Total Expenses", "£0.00", "success")
        stats_row.addWidget(self.expense_card)

        self.net_card = StatCard("Net Change", "£0.00")
        stats_row.addWidget(self.net_card)

        self.balance_card = StatCard("Period Balance", "£0.00")
        stats_row.addWidget(self.balance_card)

        layout.addLayout(stats_row)

        # ===== CHART SECTION =====
        chart_container = QFrame()
        chart_container.setObjectName("chart_container")
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(12, 12, 12, 12)
        chart_layout.setSpacing(8)

        # Chart selector row
        chart_selector_row = QHBoxLayout()
        chart_selector_row.addWidget(QLabel("Visualization:"))

        self.chart_combo = QComboBox()
        self.chart_combo.addItems([
            "Balance Trend",
            "Expenses by Category",
            "Income by Category",
            "Income vs Expenses",
        ])
        self.chart_combo.currentTextChanged.connect(self._on_chart_type_changed)
        chart_selector_row.addWidget(self.chart_combo)

        chart_selector_row.addStretch()
        chart_layout.addLayout(chart_selector_row)

        # Chart stack
        self.chart_stack = QStackedWidget()
        self.chart_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.chart_stack.setMinimumHeight(250)

        # Balance trend chart (index 0)
        self.balance_chart = BalanceTrendChart()
        self.chart_stack.addWidget(self.balance_chart)

        # Expenses by category chart (index 1)
        self.category_chart = ExpensesByCategoryChart()
        self.chart_stack.addWidget(self.category_chart)

        # Income by category chart (index 2)
        self.income_category_chart = IncomeByCategoryChart()
        self.chart_stack.addWidget(self.income_category_chart)

        # Income vs expenses chart (index 3)
        self.income_expense_chart = IncomeVsExpenseChart()
        self.chart_stack.addWidget(self.income_expense_chart)

        chart_layout.addWidget(self.chart_stack, 1)

        layout.addWidget(chart_container, 1)

        # ===== EXPORT BAR =====
        export_bar = QFrame()
        export_bar.setObjectName("export_bar")
        export_layout = QHBoxLayout(export_bar)
        export_layout.setContentsMargins(12, 8, 12, 8)
        export_layout.setSpacing(8)

        export_label = QLabel("Export:")
        export_label.setObjectName("secondary_text")
        export_layout.addWidget(export_label)

        csv_btn = QPushButton("CSV")
        csv_btn.clicked.connect(lambda: self._quick_export('csv'))
        export_layout.addWidget(csv_btn)

        md_btn = QPushButton("Markdown")
        md_btn.clicked.connect(lambda: self._quick_export('markdown'))
        export_layout.addWidget(md_btn)

        pdf_btn = QPushButton("PDF")
        pdf_btn.clicked.connect(lambda: self._quick_export('pdf'))
        export_layout.addWidget(pdf_btn)

        export_layout.addSpacing(20)

        clipboard_btn = QPushButton("Copy to Clipboard")
        clipboard_btn.clicked.connect(self._copy_to_clipboard)
        export_layout.addWidget(clipboard_btn)

        export_layout.addStretch()

        # Transaction count summary
        self.export_summary = QLabel("")
        self.export_summary.setObjectName("secondary_text")
        export_layout.addWidget(self.export_summary)

        layout.addWidget(export_bar)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._context.state.transactions.changed.connect(self._on_transactions_changed)

    def _populate_activities(self) -> None:
        """Populate activity combo box from transaction data."""
        self.activity_combo.clear()
        self.activity_combo.addItem("All", None)
        activities = sorted(
            {t.activity.strip() for t in self._context.state.transactions.value
             if t.activity and t.activity.strip()},
            key=str.lower,
        )
        for name in activities:
            self.activity_combo.addItem(name, name)

    def _on_transactions_changed(self, transactions: list[Transaction]) -> None:
        """Handle transactions list change."""
        current = self.activity_combo.currentData()
        self._populate_activities()
        index = self.activity_combo.findData(current)
        if index >= 0:
            self.activity_combo.setCurrentIndex(index)
        self._apply_filters()

    def _preset_this_month(self) -> None:
        """Set date range to this month."""
        today = date.today()
        self.start_date_edit.setDate(today.replace(day=1))
        self.end_date_edit.setDate(today)

    def _preset_last_month(self) -> None:
        """Set date range to last month."""
        today = date.today()
        first_of_this_month = today.replace(day=1)
        last_of_prev_month = first_of_this_month - timedelta(days=1)
        first_of_prev_month = last_of_prev_month.replace(day=1)
        self.start_date_edit.setDate(first_of_prev_month)
        self.end_date_edit.setDate(last_of_prev_month)

    def _preset_ytd(self) -> None:
        """Set date range to year-to-date."""
        today = date.today()
        self.start_date_edit.setDate(today.replace(month=1, day=1))
        self.end_date_edit.setDate(today)

    def _preset_financial_year(self) -> None:
        """Set date range to current financial year."""
        period = self._context.financial_year_service.get_current_period()
        self.start_date_edit.setDate(period.start_date)
        self.end_date_edit.setDate(period.end_date)

    def _preset_all(self) -> None:
        """Set date range to include all available transactions."""
        all_transactions = self._context.state.transactions.value
        if not all_transactions:
            today = date.today()
            self.start_date_edit.setDate(today.replace(month=1, day=1))
            self.end_date_edit.setDate(today)
            return

        min_date = min(t.date for t in all_transactions)
        max_date = max(t.date for t in all_transactions)
        self.start_date_edit.setDate(min_date)
        self.end_date_edit.setDate(max_date)

    def _on_chart_type_changed(self, chart_type: str) -> None:
        """Handle chart type selection change."""
        if chart_type == "Balance Trend":
            self.chart_stack.setCurrentIndex(0)
            self._update_balance_chart()
        elif chart_type == "Expenses by Category":
            self.chart_stack.setCurrentIndex(1)
            self._update_category_chart()
        elif chart_type == "Income by Category":
            self.chart_stack.setCurrentIndex(2)
            self._update_income_category_chart()
        elif chart_type == "Income vs Expenses":
            self.chart_stack.setCurrentIndex(3)
            self._update_income_expense_chart()

    def _update_balance_chart(self) -> None:
        """Update the balance trend chart."""
        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()
        days = (end_date - start_date).days

        # Get all transactions (with sheet filter but NOT date filter)
        # so the chart can calculate opening balance from prior transactions
        all_transactions = self._context.state.transactions.value
        transactions_for_chart = [
            t for t in all_transactions
            if t.status != ApprovalStatus.PLANNED
        ]

        # Apply activity filter if selected
        selected_activity = self.activity_combo.currentData()
        if selected_activity is not None:
            transactions_for_chart = [
                t for t in transactions_for_chart
                if t.activity and t.activity.strip() == selected_activity
            ]

        self.balance_chart.update_data(
            transactions_for_chart,
            self._context.balance_service,
            days=max(days, 30),
            start_date=start_date,
            end_date=end_date
        )

    def _update_category_chart(self) -> None:
        """Update the expenses by category chart."""
        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()
        self.category_chart.update_data(
            self._filtered_transactions,
            start_date=start_date,
            end_date=end_date
        )

    def _update_income_expense_chart(self) -> None:
        """Update the income vs expenses chart."""
        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()
        self.income_expense_chart.update_data(
            self._filtered_transactions,
            start_date=start_date,
            end_date=end_date
        )

    def _update_income_category_chart(self) -> None:
        """Update the income by category chart."""
        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()
        self.income_category_chart.update_data(
            self._filtered_transactions,
            start_date=start_date,
            end_date=end_date
        )

    def _apply_filters(self) -> None:
        """Apply filters and update display."""
        all_transactions = self._context.state.transactions.value

        # Apply date range filter
        start_date = self.start_date_edit.date().toPython()
        end_date = self.end_date_edit.date().toPython()

        filtered = [
            t for t in all_transactions
            if start_date <= t.date <= end_date
            and t.status != ApprovalStatus.PLANNED
        ]

        # Apply activity filter
        selected_activity = self.activity_combo.currentData()
        if selected_activity is not None:
            filtered = [
                t for t in filtered
                if t.activity and t.activity.strip() == selected_activity
            ]

        self._filtered_transactions = filtered

        # Update stats
        self._update_stats()

        # Update current chart
        self._on_chart_type_changed(self.chart_combo.currentText())

        # Update export summary
        self.export_summary.setText(f"{len(filtered)} transactions")

    def _update_stats(self) -> None:
        """Update summary statistics cards."""
        transactions = self._filtered_transactions

        total_income = sum(
            t.amount for t in transactions
            if t.type == TransactionType.INCOME
        )
        total_expenses = sum(
            t.amount for t in transactions
            if t.type == TransactionType.EXPENSE
        )
        net = total_income - total_expenses
        balance = self._context.balance_service.compute_total(transactions)

        self.transactions_card.set_value(str(len(transactions)))
        self.income_card.set_value(f"£{total_income:,.2f}")
        self.expense_card.set_value(f"£{total_expenses:,.2f}")

        # Color net based on positive/negative
        net_sign = "+" if net >= 0 else ""
        self.net_card.set_value(f"{net_sign}£{net:,.2f}")

        balance_sign = "+" if balance >= 0 else ""
        self.balance_card.set_value(f"{balance_sign}£{balance:,.2f}")

    def _quick_export(self, format: str) -> None:
        """Quick export in selected format."""
        from pathlib import Path

        if not self._filtered_transactions:
            QMessageBox.warning(self, "No Data", "No transactions to export.")
            return

        extension = "md" if format == "markdown" else format
        format_name = format.upper() if format != "markdown" else "Markdown"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {format_name}",
            f"report.{extension}",
            f"{format_name} Files (*.{extension});;All Files (*)"
        )

        if not file_path:
            return

        try:
            self._context.export_service.export(
                self._filtered_transactions,
                Path(file_path),
                format,
                include_balance=True
            )
            QMessageBox.information(
                self, "Exported",
                f"Exported {len(self._filtered_transactions)} transactions to:\n{file_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export: {e}")

    def _copy_to_clipboard(self) -> None:
        """Copy transactions to clipboard as TSV."""
        if not self._filtered_transactions:
            QMessageBox.warning(self, "No Data", "No transactions to copy.")
            return

        tsv = self._context.export_service.export_to_tsv(
            self._filtered_transactions,
            include_balance=True
        )

        QApplication.clipboard().setText(tsv)
        QMessageBox.information(
            self, "Copied",
            f"Copied {len(self._filtered_transactions)} transactions to clipboard."
        )

    def _on_build_report(self) -> None:
        """Open the markdown report editor."""
        all_transactions = self._context.state.transactions.value

        if not all_transactions:
            QMessageBox.warning(self, "No Data", "No transactions available.")
            return

        dialog = MarkdownReportEditor(self._context, all_transactions, self)
        dialog.exec()

    def refresh_theme(self) -> None:
        """Refresh chart colors after theme change."""
        self.balance_chart.refresh_theme()
        self.category_chart.refresh_theme()
        self.income_category_chart.refresh_theme()
        self.income_expense_chart.refresh_theme()
