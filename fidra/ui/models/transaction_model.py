"""Transaction table model for Qt Model/View."""

from decimal import Decimal
from typing import Any, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.services.balance import BalanceService
from fidra.ui.theme.engine import get_theme_engine, Theme


class TransactionTableModel(QAbstractTableModel):
    """Table model for displaying transactions.

    Displays transactions with columns:
    - Date
    - Description
    - Amount
    - Type
    - Category
    - Party
    - Status
    - Balance (running balance)
    - Notes
    """

    # Column indices
    COL_DATE = 0
    COL_DESCRIPTION = 1
    COL_AMOUNT = 2
    COL_TYPE = 3
    COL_CATEGORY = 4
    COL_PARTY = 5
<<<<<<< HEAD
    COL_REFERENCE = 6
    COL_SHEET = 7
    COL_STATUS = 8
    COL_BALANCE = 9
=======
    COL_SHEET = 6
    COL_STATUS = 7
    COL_BALANCE = 8
    COL_REFERENCE = 9
>>>>>>> b9307e3 (Sync local changes)
    COL_NOTES = 10

    COLUMN_NAMES = [
        "Date",
        "Description",
        "Amount",
        "Type",
        "Category",
        "Party",
        "Reference",
        "Sheet",
        "Status",
        "Balance",
        "Reference",
        "Notes",
    ]

    def __init__(self, transactions: Optional[list[Transaction]] = None):
        """Initialize the model.

        Args:
            transactions: Initial list of transactions
        """
        super().__init__()
        self._transactions = transactions or []
        self._balances: dict[str, Decimal] = {}
        self._balance_service = BalanceService()
        self._sort_column = self.COL_DATE
        self._sort_order = Qt.DescendingOrder
        self._update_balances()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return number of rows."""
        if parent.isValid():
            return 0
        return len(self._transactions)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return number of columns."""
        if parent.isValid():
            return 0
        return len(self.COLUMN_NAMES)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        """Return data for the given index and role."""
        if not index.isValid():
            return None

        if index.row() >= len(self._transactions):
            return None

        transaction = self._transactions[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            return self._get_display_data(transaction, col)
        elif role == Qt.TextAlignmentRole:
            return self._get_alignment(col)
        elif role == Qt.ForegroundRole:
            return self._get_foreground_color(transaction, col)
        elif role == Qt.BackgroundRole:
            return self._get_background_color(transaction, index.row())
        elif role == Qt.FontRole:
            return self._get_font(transaction)
        elif role == Qt.UserRole:
            # Store the full transaction object for easy access
            return transaction

        return None

    def _get_display_data(self, transaction: Transaction, col: int) -> Any:
        """Get display data for a specific column."""
        if col == self.COL_DATE:
            return transaction.date.strftime("%Y-%m-%d")
        elif col == self.COL_DESCRIPTION:
            # Add badge for planned transactions
            desc = transaction.description
            if transaction.status == ApprovalStatus.PLANNED:
                return f"{desc}"
            return desc
        elif col == self.COL_AMOUNT:
            return f"£{transaction.amount:.2f}"
        elif col == self.COL_TYPE:
            return transaction.type.value.title()
        elif col == self.COL_CATEGORY:
            return transaction.category or ""
        elif col == self.COL_PARTY:
            return transaction.party or ""
        elif col == self.COL_REFERENCE:
            return transaction.reference or ""
        elif col == self.COL_SHEET:
            return transaction.sheet or ""
        elif col == self.COL_STATUS:
            return transaction.status.value.title()
        elif col == self.COL_BALANCE:
            balance = self._balances.get(str(transaction.id))
            if balance is not None:
                return f"£{balance:.2f}"
            return ""
        elif col == self.COL_REFERENCE:
            return transaction.reference or ""
        elif col == self.COL_NOTES:
            return transaction.notes or ""
        return None

    def _get_alignment(self, col: int) -> Qt.AlignmentFlag:
        """Get text alignment for a column."""
        if col in (self.COL_AMOUNT, self.COL_BALANCE):
            return Qt.AlignRight | Qt.AlignVCenter
        return Qt.AlignLeft | Qt.AlignVCenter

    def _get_foreground_color(self, transaction: Transaction, col: int) -> Optional[QColor]:
        """Get foreground color for a cell."""
        # Rejected transactions: gray text for all columns
        if transaction.status == ApprovalStatus.REJECTED:
            return QColor(160, 160, 160)  # Gray for strikethrough text

        # Planned transactions: use muted colors for all columns
        if transaction.status == ApprovalStatus.PLANNED:
            return QColor(140, 140, 140)  # Muted gray

        # Color amount based on type (for non-planned only)
        if col == self.COL_AMOUNT:
            if transaction.type == TransactionType.INCOME:
                return QColor(34, 139, 34)  # Green
            elif transaction.type == TransactionType.EXPENSE:
                return QColor(220, 20, 60)  # Red

        # Color status (for non-planned only)
        if col == self.COL_STATUS:
            if transaction.status == ApprovalStatus.PENDING:
                return QColor(255, 140, 0)  # Orange

        return None

    def _get_font(self, transaction: Transaction) -> Optional[QFont]:
        """Get font for a row (e.g., strikethrough for rejected)."""
        if transaction.status == ApprovalStatus.REJECTED:
            font = QFont()
            font.setStrikeOut(True)
            return font
        return None

    def _get_background_color(self, transaction: Transaction, row: int) -> Optional[QColor]:
        """Get background color for a row based on status (theme-aware)."""
        theme = get_theme_engine()
        is_dark = theme.current_theme == Theme.DARK

        if transaction.status == ApprovalStatus.PLANNED:
            if is_dark:
                return QColor(45, 55, 72)  # Dark blue-gray
            else:
                return QColor(245, 248, 250)  # Very light blue-gray
        elif transaction.status == ApprovalStatus.PENDING:
            if is_dark:
                return QColor(66, 56, 40)  # Dark amber/brown tint
            else:
                return QColor(255, 243, 224)  # Light amber/orange tint
        # Rejected: no background highlight, uses strikethrough + gray text instead

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        """Return header data."""
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                if 0 <= section < len(self.COLUMN_NAMES):
                    return self.COLUMN_NAMES[section]
            elif orientation == Qt.Vertical:
                return str(section + 1)
        return None

    def set_transactions(self, transactions: list[Transaction]) -> None:
        """Update the model with a new list of transactions.

        Args:
            transactions: New list of transactions
        """
        self.beginResetModel()
        self._transactions = transactions
        self._update_balances()
        self.endResetModel()

    def _update_balances(self) -> None:
        """Recalculate running balances for all transactions."""
        if not self._transactions:
            self._balances = {}
            return

        def get_sort_key(transaction: Transaction):
            if self._sort_column == self.COL_DATE:
                return (transaction.date, transaction.created_at, transaction.description.lower())
            if self._sort_column == self.COL_DESCRIPTION:
                return transaction.description.lower()
            if self._sort_column == self.COL_AMOUNT:
                return transaction.amount
            if self._sort_column == self.COL_TYPE:
                return transaction.type.value
            if self._sort_column == self.COL_CATEGORY:
                return (transaction.category or "").lower()
            if self._sort_column == self.COL_PARTY:
                return (transaction.party or "").lower()
            if self._sort_column == self.COL_REFERENCE:
                return (transaction.reference or "").lower()
            if self._sort_column == self.COL_SHEET:
                return (transaction.sheet or "").lower()
            if self._sort_column == self.COL_STATUS:
                status_order = {
                    ApprovalStatus.PLANNED: 0,
                    ApprovalStatus.PENDING: 1,
                    ApprovalStatus.APPROVED: 2,
                    ApprovalStatus.REJECTED: 3,
                }
                return status_order.get(transaction.status, 99)
            if self._sort_column == self.COL_BALANCE:
                balance = self._balances.get(str(transaction.id), Decimal(0))
                return balance
            if self._sort_column == self.COL_REFERENCE:
                return (transaction.reference or "").lower()
            if self._sort_column == self.COL_NOTES:
                return (transaction.notes or "").lower()
            return transaction.date

        ordered = sorted(
            self._transactions,
            key=get_sort_key,
            reverse=(self._sort_order == Qt.DescendingOrder),
        )

        balances = {}
        running = Decimal("0")
        # If displaying newest-first, compute running balance from oldest to newest,
        # but assign the resulting balance to the displayed rows so the top row
        # reflects the latest cumulative balance.
        if self._sort_order == Qt.DescendingOrder:
            iter_source = reversed(ordered)
        else:
            iter_source = ordered

        for t in iter_source:
            if t.type == TransactionType.INCOME and t.status in self._balance_service.COUNTABLE_INCOME:
                running += t.amount
            elif t.type == TransactionType.EXPENSE and t.status in self._balance_service.COUNTABLE_EXPENSE:
                running -= t.amount
            balances[str(t.id)] = running

        self._balances = balances

    def get_transaction_at(self, row: int) -> Optional[Transaction]:
        """Get transaction at the given row.

        Args:
            row: Row index

        Returns:
            Transaction at that row, or None if invalid
        """
        if 0 <= row < len(self._transactions):
            return self._transactions[row]
        return None

    def get_all_transactions(self) -> list[Transaction]:
        """Get all transactions in the model.

        Returns:
            List of all transactions
        """
        return self._transactions.copy()

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        """Sort the model by the given column.

        Args:
            column: Column index to sort by
            order: Sort order (ascending or descending)
        """
        if not self._transactions:
            return

        self.layoutAboutToBeChanged.emit()

        reverse = (order == Qt.DescendingOrder)
        self._sort_column = column
        self._sort_order = order

        # Define sort key functions for each column
        def get_sort_key(transaction: Transaction):
            if column == self.COL_DATE:
                # Secondary sort by created_at, then description for same-day items
                return (transaction.date, transaction.created_at, transaction.description.lower())
            elif column == self.COL_DESCRIPTION:
                return transaction.description.lower()
            elif column == self.COL_AMOUNT:
                return transaction.amount
            elif column == self.COL_TYPE:
                return transaction.type.value
            elif column == self.COL_CATEGORY:
                return (transaction.category or "").lower()
            elif column == self.COL_PARTY:
                return (transaction.party or "").lower()
            elif column == self.COL_REFERENCE:
                return (transaction.reference or "").lower()
            elif column == self.COL_SHEET:
                return (transaction.sheet or "").lower()
            elif column == self.COL_STATUS:
                # Custom order: planned first, then pending, approved, rejected
                status_order = {
                    ApprovalStatus.PLANNED: 0,
                    ApprovalStatus.PENDING: 1,
                    ApprovalStatus.APPROVED: 2,
                    ApprovalStatus.REJECTED: 3,
                }
                return status_order.get(transaction.status, 99)
            elif column == self.COL_BALANCE:
                balance = self._balances.get(str(transaction.id), Decimal(0))
                return balance
            elif column == self.COL_REFERENCE:
                return (transaction.reference or "").lower()
            elif column == self.COL_NOTES:
                return (transaction.notes or "").lower()
            else:
                return transaction.date

        self._transactions.sort(key=get_sort_key, reverse=reverse)
        self._update_balances()

        self.layoutChanged.emit()
