"""Activities summary view - at-a-glance financial summary per activity."""

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fidra.domain.models import Transaction, TransactionType

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class ActivitiesView(QWidget):
    """Activities summary view showing income, expenses, and net per activity.

    Provides an at-a-glance summary table of all activities with totals.
    Double-clicking a row navigates to the Transactions view filtered by
    that activity.
    """

    activity_selected = Signal(str)  # Emitted with activity name on double-click

    def __init__(self, context: "ApplicationContext", parent=None):
        super().__init__(parent)
        self._context = context
        self._setup_ui()
        self._connect_signals()
        self._update_summary()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Page header
        title = QLabel("Activities")
        title.setObjectName("page_title")
        font = title.font()
        font.setPointSize(18)
        font.setWeight(QFont.Weight.Bold)
        title.setFont(font)
        layout.addWidget(title)

        # Summary table
        self.table = QTableWidget()
        self.table.setObjectName("activities_table")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Activity", "Transactions", "Income", "Expenses", "Net"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        # Column sizing
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table, 1)

        # Empty state label (shown when no activities)
        self.empty_label = QLabel(
            "No activities yet \u2014 tag transactions with an activity to track them here."
        )
        self.empty_label.setObjectName("secondary_text")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        self.empty_label.hide()

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._context.state.transactions.changed.connect(
            self._on_transactions_changed
        )
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)

    def _on_transactions_changed(self, transactions: list[Transaction]) -> None:
        """Handle transactions list change."""
        self._update_summary()

    def _update_summary(self) -> None:
        """Recompute and display the activities summary table."""
        transactions = self._context.state.transactions.value

        # Group by activity
        activity_data: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "income": Decimal("0"), "expenses": Decimal("0")}
        )

        for t in transactions:
            if not t.activity or not t.activity.strip():
                continue
            entry = activity_data[t.activity.strip()]
            entry["count"] += 1
            if t.type == TransactionType.INCOME:
                entry["income"] += t.amount
            else:
                entry["expenses"] += t.amount

        # Sort by activity name
        sorted_activities = sorted(activity_data.items(), key=lambda x: x[0].lower())

        if not sorted_activities:
            self.table.hide()
            self.empty_label.show()
            return

        self.empty_label.hide()
        self.table.show()

        # +1 for totals row
        self.table.setRowCount(len(sorted_activities) + 1)

        grand_count = 0
        grand_income = Decimal("0")
        grand_expenses = Decimal("0")

        for row, (activity, data) in enumerate(sorted_activities):
            count = data["count"]
            income = data["income"]
            expenses = data["expenses"]
            net = income - expenses

            grand_count += count
            grand_income += income
            grand_expenses += expenses

            # Activity name
            name_item = QTableWidgetItem(activity)
            self.table.setItem(row, 0, name_item)

            # Transaction count (center-aligned)
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 1, count_item)

            # Income
            income_item = QTableWidgetItem(f"\u00a3{income:,.2f}")
            income_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 2, income_item)

            # Expenses
            expense_item = QTableWidgetItem(f"\u00a3{expenses:,.2f}")
            expense_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 3, expense_item)

            # Net (coloured)
            net_item = self._make_net_item(net)
            self.table.setItem(row, 4, net_item)

        # Totals row
        totals_row = len(sorted_activities)
        grand_net = grand_income - grand_expenses

        bold_font = QFont()
        bold_font.setBold(True)

        totals_label = QTableWidgetItem("Total")
        totals_label.setFont(bold_font)
        self.table.setItem(totals_row, 0, totals_label)

        totals_count = QTableWidgetItem(str(grand_count))
        totals_count.setFont(bold_font)
        totals_count.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setItem(totals_row, 1, totals_count)

        totals_income = QTableWidgetItem(f"\u00a3{grand_income:,.2f}")
        totals_income.setFont(bold_font)
        totals_income.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setItem(totals_row, 2, totals_income)

        totals_expenses = QTableWidgetItem(f"\u00a3{grand_expenses:,.2f}")
        totals_expenses.setFont(bold_font)
        totals_expenses.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setItem(totals_row, 3, totals_expenses)

        totals_net = self._make_net_item(grand_net)
        totals_net.setFont(bold_font)
        self.table.setItem(totals_row, 4, totals_net)

    @staticmethod
    def _make_net_item(net: Decimal) -> QTableWidgetItem:
        """Create a table item for a net value with colour coding."""
        sign = "+" if net >= 0 else ""
        item = QTableWidgetItem(f"{sign}\u00a3{net:,.2f}")
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        if net > 0:
            item.setForeground(Qt.GlobalColor.darkGreen)
        elif net < 0:
            item.setForeground(Qt.GlobalColor.red)
        return item

    def _on_row_double_clicked(self, row: int, column: int) -> None:
        """Handle double-click on a row to navigate to filtered transactions."""
        name_item = self.table.item(row, 0)
        if not name_item:
            return
        activity_name = name_item.text()
        # Don't navigate for the totals row
        if activity_name == "Total":
            return
        self.activity_selected.emit(f'"{activity_name}"')
