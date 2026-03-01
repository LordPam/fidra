"""Activities summary view - at-a-glance financial summary per activity."""

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

import qasync
from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtGui import QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fidra.domain.models import Transaction, PlannedTemplate, TransactionType

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
        self._activity_notes: dict[str, str] = {}
        self._setup_ui()
        self._connect_signals()
        self._update_summary()
        self._load_notes_from_repo()

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
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Activity", "Txns", "Income", "Expenses", "Net", "Planned", "Projected Net"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        # Column sizing
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 7):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table, 1)

        # Activity notes detail panel
        self.notes_panel = QFrame()
        self.notes_panel.setObjectName("notes_panel")
        self.notes_panel.setFrameShape(QFrame.Shape.NoFrame)
        notes_layout = QVBoxLayout(self.notes_panel)
        notes_layout.setContentsMargins(12, 8, 12, 8)
        notes_layout.setSpacing(4)

        self.notes_label = QLabel()
        bold_font = QFont()
        bold_font.setBold(True)
        self.notes_label.setFont(bold_font)
        notes_layout.addWidget(self.notes_label)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(
            "Add context for this activity\u2019s outcomes..."
        )
        self.notes_edit.setMaximumHeight(100)
        notes_layout.addWidget(self.notes_edit)

        layout.addWidget(self.notes_panel)
        self.notes_panel.hide()

        self._current_notes_activity: str | None = None
        self._notes_save_timer = QTimer(self)
        self._notes_save_timer.setSingleShot(True)
        self._notes_save_timer.setInterval(500)
        self._notes_save_timer.timeout.connect(self._persist_notes_async)

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
            self._on_data_changed
        )
        self._context.state.planned_templates.changed.connect(
            self._on_data_changed
        )
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self.table.cellClicked.connect(self._on_row_clicked)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.notes_edit.textChanged.connect(self._on_notes_text_changed)

        # Escape to clear selection and hide notes panel
        escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        escape_shortcut.activated.connect(self._on_deselect)

        # Click empty space in table to deselect
        self.table.viewport().installEventFilter(self)

    def _on_deselect(self) -> None:
        """Clear table selection and hide the notes panel."""
        self._notes_save_timer.stop()
        self._save_notes_for_activity(
            self._current_notes_activity,
            self.notes_edit.toPlainText().strip(),
        )
        self._current_notes_activity = None
        self.table.clearSelection()
        self.notes_panel.hide()

    def eventFilter(self, obj, event) -> bool:
        """Clear selection when clicking empty space in viewport."""
        if obj is self.table.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            index = self.table.indexAt(event.pos())
            if not index.isValid():
                self._on_deselect()
        return super().eventFilter(obj, event)

    def _on_data_changed(self, *args) -> None:
        """Handle transactions or planned templates change."""
        self._update_summary()

    def _update_summary(self) -> None:
        """Recompute and display the activities summary table."""
        transactions = self._context.state.transactions.value
        planned_templates = self._context.state.planned_templates.value

        # Group transactions by activity
        activity_data: dict[str, dict] = defaultdict(
            lambda: {
                "count": 0,
                "income": Decimal("0"),
                "expenses": Decimal("0"),
                "planned_income": Decimal("0"),
                "planned_expenses": Decimal("0"),
            }
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

        # Add planned template amounts
        for p in planned_templates:
            if not p.activity or not p.activity.strip():
                continue
            entry = activity_data[p.activity.strip()]
            if p.type == TransactionType.INCOME:
                entry["planned_income"] += p.amount
            else:
                entry["planned_expenses"] += p.amount

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
        grand_planned_net = Decimal("0")

        for row, (activity, data) in enumerate(sorted_activities):
            count = data["count"]
            income = data["income"]
            expenses = data["expenses"]
            net = income - expenses
            planned_net = data["planned_income"] - data["planned_expenses"]
            projected_net = net + planned_net

            grand_count += count
            grand_income += income
            grand_expenses += expenses
            grand_planned_net += planned_net

            # Activity name
            name_item = QTableWidgetItem(activity)
            self.table.setItem(row, 0, name_item)

            # Transaction count
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

            # Planned net
            if planned_net != 0:
                planned_item = self._make_net_item(planned_net)
                planned_item.setToolTip(
                    f"Planned: +\u00a3{data['planned_income']:,.2f} income, "
                    f"-\u00a3{data['planned_expenses']:,.2f} expenses"
                )
            else:
                planned_item = QTableWidgetItem("-")
                planned_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            self.table.setItem(row, 5, planned_item)

            # Projected net (actual + planned)
            projected_item = self._make_net_item(projected_net)
            self.table.setItem(row, 6, projected_item)

        # Totals row
        totals_row = len(sorted_activities)
        grand_net = grand_income - grand_expenses
        grand_projected = grand_net + grand_planned_net

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

        totals_planned = self._make_net_item(grand_planned_net)
        totals_planned.setFont(bold_font)
        self.table.setItem(totals_row, 5, totals_planned)

        totals_projected = self._make_net_item(grand_projected)
        totals_projected.setFont(bold_font)
        self.table.setItem(totals_row, 6, totals_projected)

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

    def _on_current_cell_changed(self, row: int, col: int, prev_row: int, prev_col: int) -> None:
        """Handle arrow-key navigation between rows."""
        if row != prev_row and row >= 0:
            self._on_row_clicked(row, col)

    def _on_row_clicked(self, row: int, column: int) -> None:
        """Handle single-click to show the notes panel for the selected activity."""
        name_item = self.table.item(row, 0)
        if not name_item:
            self.notes_panel.hide()
            return

        activity_name = name_item.text()
        if activity_name == "Total":
            self.notes_panel.hide()
            return

        # Save notes for previously selected activity before switching
        self._notes_save_timer.stop()
        self._save_notes_for_activity(
            self._current_notes_activity,
            self.notes_edit.toPlainText().strip(),
        )

        self._current_notes_activity = activity_name
        self.notes_label.setText(f"Notes — {activity_name}")

        # Load existing notes from cached dict
        notes = self._activity_notes.get(activity_name, "")
        self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText(notes)
        self.notes_edit.blockSignals(False)

        self.notes_panel.show()

    def _on_notes_text_changed(self) -> None:
        """Debounce save on text edits."""
        self._notes_save_timer.start()

    @qasync.asyncSlot()
    async def _load_notes_from_repo(self) -> None:
        """Load all activity notes from the repository."""
        repo = self._context.activity_notes_repo
        if repo:
            self._activity_notes = await repo.get_all()

    @qasync.asyncSlot()
    async def _persist_notes_async(self) -> None:
        """Debounced save: persist notes for the currently selected activity."""
        if self._current_notes_activity:
            await self._do_save_notes(
                self._current_notes_activity,
                self.notes_edit.toPlainText().strip(),
            )

    @qasync.asyncSlot()
    async def _save_notes_for_activity(self, activity: str | None, text: str) -> None:
        """Save notes for a specific activity (captures values before async gap)."""
        if activity:
            await self._do_save_notes(activity, text)

    async def _do_save_notes(self, activity: str, text: str) -> None:
        """Write notes to the local cache dict and repository."""
        repo = self._context.activity_notes_repo
        if not repo:
            return

        if text:
            self._activity_notes[activity] = text
            await repo.save(activity, text)
        else:
            self._activity_notes.pop(activity, None)
            await repo.delete(activity)

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
