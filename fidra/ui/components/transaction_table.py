"""Transaction table widget."""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTableView, QHeaderView, QMenu, QAbstractItemView, QStyledItemDelegate
from PySide6.QtGui import QAction, QPainter, QBrush
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

from fidra.domain.models import Transaction
from fidra.ui.models.transaction_model import TransactionTableModel


class TransactionItemDelegate(QStyledItemDelegate):
    """Custom delegate that respects model's BackgroundRole despite QSS."""

    def paint(self, painter: QPainter, option, index):
        """Paint the item with proper background color from model."""
        # Get background color from model
        bg_color = index.data(Qt.BackgroundRole)

        opt = QStyleOptionViewItem(option)
        # Prevent per-cell hover overlays in tables (hover should not override row styling).
        opt.state &= ~QStyle.State_MouseOver
        if bg_color is not None:
            painter.save()
            painter.fillRect(option.rect, QBrush(bg_color))
            painter.restore()

        # Call parent to paint the rest (text, selection, etc.)
        super().paint(painter, opt, index)


class TransactionTable(QTableView):
    """Table widget for displaying transactions.

    Features:
    - Sortable columns
    - Context menu (right-click)
    - Single and multi-select support
    - Signals for user actions
    """

    # Signals
    edit_requested = Signal(Transaction)  # User wants to edit single transaction
    bulk_edit_requested = Signal(list)  # User wants to bulk edit transactions
    delete_requested = Signal(list)  # User wants to delete transaction(s)
    duplicate_requested = Signal(list)  # User wants to duplicate transaction(s)
    approve_requested = Signal(list)  # User wants to approve transaction(s)
    reject_requested = Signal(list)  # User wants to reject transaction(s)
    convert_to_actual_requested = Signal(list)  # User wants to convert planned to actual
    skip_instance_requested = Signal(list)  # User wants to skip planned instance(s)
    delete_template_requested = Signal(list)  # User wants to delete planned template(s)

    def __init__(self, parent=None):
        """Initialize the transaction table.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Create and set model
        self._model = TransactionTableModel()
        self.setModel(self._model)

        # Set custom delegate for proper background colors
        self._delegate = TransactionItemDelegate(self)
        self.setItemDelegate(self._delegate)

        # Configure table appearance
        self._setup_appearance()

        # Configure selection
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # Enable sorting
        self.setSortingEnabled(True)
        self.sortByColumn(self._model.COL_DATE, Qt.DescendingOrder)

        # Context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Double-click to edit
        self.doubleClicked.connect(self._on_double_click)

    def _setup_appearance(self) -> None:
        """Configure table visual appearance."""
        header = self.horizontalHeader()
        header.setStretchLastSection(False)

        # Define base widths and minimum widths for each column
        # These are the "ideal" widths at a reference size
        self._column_base_widths = {
            self._model.COL_DATE: 100,
            self._model.COL_DESCRIPTION: 200,
            self._model.COL_AMOUNT: 90,
            self._model.COL_TYPE: 75,
            self._model.COL_CATEGORY: 95,
            self._model.COL_PARTY: 130,
            self._model.COL_REFERENCE: 100,
            self._model.COL_SHEET: 80,
            self._model.COL_STATUS: 85,
            self._model.COL_BALANCE: 95,
            self._model.COL_NOTES: 90,
        }

        self._column_min_widths = {
            self._model.COL_DATE: 97,        # Fits "2026-01-30"
            self._model.COL_DESCRIPTION: 140,
            self._model.COL_AMOUNT: 85,      # Fits "£1,234.56"
            self._model.COL_TYPE: 65,        # Fits "Expense"
            self._model.COL_CATEGORY: 85,    # Fits "Category" header
            self._model.COL_PARTY: 110,      # Close to description
            self._model.COL_REFERENCE: 80,   # Fits "Reference" header
            self._model.COL_SHEET: 75,
            self._model.COL_STATUS: 75,      # Fits "Approved"
            self._model.COL_BALANCE: 90,     # Fits negative amounts
            self._model.COL_NOTES: 80,
        }

        # Use Interactive mode for all columns (allows manual resize too)
        for col in self._column_base_widths:
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        # Set initial widths
        for col, width in self._column_base_widths.items():
            header.resizeSection(col, width)

        # Set minimum section size (global minimum)
        header.setMinimumSectionSize(50)

        # Hide sheet column by default (only shown in All Sheets mode)
        self.setColumnHidden(self._model.COL_SHEET, True)

        # Disable alternating row colors - we handle backgrounds in the model
        self.setAlternatingRowColors(False)

        # Show grid
        self.setShowGrid(True)

        # Row height - compact for laptop screens
        self.verticalHeader().setDefaultSectionSize(26)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

        # Enable click on header to sort
        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)

    def set_show_sheet_column(self, show: bool) -> None:
        """Show or hide the sheet column.

        Args:
            show: True to show sheet column (for All Sheets mode)
        """
        self.setColumnHidden(self._model.COL_SHEET, not show)

    def set_transactions(self, transactions: list[Transaction]) -> None:
        """Update the table with new transactions.

        Preserves the current sort order after updating.

        Args:
            transactions: List of transactions to display
        """
        # Save current sort state
        header = self.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()

        # Update model
        self._model.set_transactions(transactions)

        # Re-apply sort (this triggers model.sort())
        self.sortByColumn(sort_column, sort_order)

    def get_selected_transactions(self) -> list[Transaction]:
        """Get currently selected transactions.

        Returns:
            List of selected transactions
        """
        selection = self.selectionModel()
        if not selection:
            return []

        selected_rows = set(index.row() for index in selection.selectedRows())
        transactions = []
        for row in sorted(selected_rows):
            trans = self._model.get_transaction_at(row)
            if trans:
                transactions.append(trans)

        return transactions

    def _on_double_click(self, index) -> None:
        """Handle double-click to edit transaction.

        Args:
            index: Model index that was double-clicked
        """
        trans = self._model.get_transaction_at(index.row())
        if trans:
            self.edit_requested.emit(trans)

    def _show_context_menu(self, position) -> None:
        """Show context menu at the given position.

        Args:
            position: Position where menu should appear
        """
        selected = self.get_selected_transactions()
        if not selected:
            return

        menu = QMenu(self)

        # Check if any planned transactions are selected
        from fidra.domain.models import TransactionType, ApprovalStatus
        planned_only = [t for t in selected if t.status == ApprovalStatus.PLANNED]

        # If ALL selected are planned, show planned-specific actions
        if planned_only and len(planned_only) == len(selected):
            # Convert to Actual
            convert_action = QAction(f"Convert to Actual ({len(planned_only)})", self)
            convert_action.triggered.connect(lambda: self.convert_to_actual_requested.emit(planned_only))
            menu.addAction(convert_action)

            menu.addSeparator()

            # Check if all selected are one-time planned (ONCE frequency)
            # is_one_time_planned is True for ONCE, False for recurring, None for actual
            all_one_time = all(t.is_one_time_planned is True for t in planned_only)
            any_recurring = any(t.is_one_time_planned is False for t in planned_only)

            if all_one_time:
                # For one-time planned, just show "Delete" (same as deleting template)
                delete_action = QAction(f"Delete ({len(planned_only)})", self)
                delete_action.triggered.connect(lambda: self.delete_template_requested.emit(planned_only))
                menu.addAction(delete_action)
            elif any_recurring:
                # For recurring (or mixed), show both options
                # Delete This Instance (permanently removes just this occurrence)
                delete_instance_action = QAction(f"Delete This Instance ({len(planned_only)})", self)
                delete_instance_action.triggered.connect(lambda: self.skip_instance_requested.emit(planned_only))
                menu.addAction(delete_instance_action)

                # Delete Entire Template (removes all future instances)
                delete_template_action = QAction(f"Delete Entire Template ({len(planned_only)})", self)
                delete_template_action.triggered.connect(lambda: self.delete_template_requested.emit(planned_only))
                menu.addAction(delete_template_action)

            menu.addSeparator()

        # Edit (for non-planned transactions)
        actual_for_edit = [t for t in selected if t.status != ApprovalStatus.PLANNED]
        if actual_for_edit:
            if len(actual_for_edit) == 1:
                edit_action = QAction("Edit", self)
                edit_action.triggered.connect(lambda: self.edit_requested.emit(actual_for_edit[0]))
            else:
                edit_action = QAction(f"Bulk Edit ({len(actual_for_edit)})", self)
                edit_action.triggered.connect(lambda: self.bulk_edit_requested.emit(actual_for_edit))
            menu.addAction(edit_action)

            # Duplicate
            duplicate_action = QAction(f"Duplicate ({len(actual_for_edit)})", self)
            duplicate_action.triggered.connect(lambda: self.duplicate_requested.emit(actual_for_edit))
            menu.addAction(duplicate_action)

            menu.addSeparator()

        # Approve/Reject (only for pending expenses)
        # Only show Approve for expenses that aren't already approved
        approvable = [t for t in selected
                      if t.type == TransactionType.EXPENSE
                      and t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.APPROVED)]
        # Only show Reject for expenses that aren't already rejected
        rejectable = [t for t in selected
                      if t.type == TransactionType.EXPENSE
                      and t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)]

        if approvable or rejectable:
            if approvable:
                approve_action = QAction(f"Approve ({len(approvable)})", self)
                approve_action.triggered.connect(lambda: self.approve_requested.emit(approvable))
                menu.addAction(approve_action)

            if rejectable:
                reject_action = QAction(f"Reject ({len(rejectable)})", self)
                reject_action.triggered.connect(lambda: self.reject_requested.emit(rejectable))
                menu.addAction(reject_action)

            menu.addSeparator()

        # Delete (not available for planned transactions - they should be skipped instead)
        actual_only = [t for t in selected if t.status != ApprovalStatus.PLANNED]
        if actual_only:
            delete_action = QAction(f"Delete ({len(actual_only)})", self)
            delete_action.triggered.connect(lambda: self.delete_requested.emit(actual_only))
            menu.addAction(delete_action)

        # Show menu
        menu.exec_(self.viewport().mapToGlobal(position))

    def get_all_transactions(self) -> list[Transaction]:
        """Get all transactions in the table.

        Returns:
            List of all transactions
        """
        return self._model.get_all_transactions()

    def clear_selection(self) -> None:
        """Clear current selection."""
        selection_model = self.selectionModel()
        if selection_model:
            selection_model.clearSelection()

    def resizeEvent(self, event) -> None:
        """Handle resize to adjust column widths proportionally."""
        super().resizeEvent(event)
        self._adjust_column_widths()

    def showEvent(self, event) -> None:
        """Handle show event to set initial column widths."""
        super().showEvent(event)
        self._adjust_column_widths()

    def _adjust_column_widths(self) -> None:
        """Adjust column widths proportionally based on available space."""
        header = self.horizontalHeader()
        viewport_width = self.viewport().width()

        if viewport_width <= 0:
            return

        # Calculate total base width of visible columns
        total_base = 0
        visible_columns = []
        for col, base_width in self._column_base_widths.items():
            if not self.isColumnHidden(col):
                total_base += base_width
                visible_columns.append(col)

        if total_base == 0:
            return

        # Calculate total minimum width
        total_min = sum(
            self._column_min_widths[col] for col in visible_columns
        )

        # If viewport is smaller than total minimums, use minimums (will scroll)
        if viewport_width <= total_min:
            for col in visible_columns:
                header.resizeSection(col, self._column_min_widths[col])
            return

        # Scale columns proportionally
        for col in visible_columns:
            base_width = self._column_base_widths[col]
            min_width = self._column_min_widths[col]
            # Calculate proportional width
            proportion = base_width / total_base
            new_width = int(viewport_width * proportion)
            # Ensure minimum width
            new_width = max(new_width, min_width)
            header.resizeSection(col, new_width)
