"""Opening balance dialog for new or empty databases."""

from datetime import date
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext

from fidra.domain.models import ApprovalStatus, Transaction, TransactionType


class OpeningBalanceDialog(QDialog):
    """Dialog to set the opening balance for a new ledger.

    Shown when creating a new database or opening one with no transactions.
    Creates an initial transaction representing the starting balance.
    """

    def __init__(self, parent=None, sheet_name: str = "Main"):
        super().__init__(parent)
        self._sheet_name = sheet_name
        self._transaction: Optional[Transaction] = None

        self.setWindowTitle("Set Opening Balance")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("Opening Balance")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Explanation
        info = QLabel(
            "Enter the starting balance for this ledger. "
            "This is the amount currently in the account before "
            "recording any new transactions."
        )
        info.setWordWrap(True)
        info.setObjectName("secondary_text")
        layout.addWidget(info)

        layout.addSpacing(8)

        # Amount row
        amount_layout = QHBoxLayout()
        amount_label = QLabel("Balance:")
        amount_label.setMinimumWidth(80)
        amount_layout.addWidget(amount_label)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setPrefix("£ ")
        self.amount_input.setRange(0.00, 9999999.99)
        self.amount_input.setDecimals(2)
        self.amount_input.setValue(0.00)
        self.amount_input.setMinimumHeight(32)
        amount_layout.addWidget(self.amount_input, 1)
        layout.addLayout(amount_layout)

        # Date row
        date_layout = QHBoxLayout()
        date_label = QLabel("As of:")
        date_label.setMinimumWidth(80)
        date_layout.addWidget(date_label)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd MMM yyyy")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setMinimumHeight(32)
        date_layout.addWidget(self.date_edit, 1)
        layout.addLayout(date_layout)

        layout.addSpacing(8)

        # Note about skipping
        skip_info = QLabel(
            "Set to £ 0.00 if you want to start from zero."
        )
        skip_info.setObjectName("secondary_text")
        layout.addWidget(skip_info)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self) -> None:
        amount = Decimal(str(self.amount_input.value()))
        balance_date = self.date_edit.date().toPython()

        if amount > 0:
            self._transaction = Transaction.create(
                date=balance_date,
                description="Opening Balance",
                amount=amount,
                type=TransactionType.INCOME,
                sheet=self._sheet_name,
                status=ApprovalStatus.AUTO,
                category="Opening Balance",
                notes="Starting balance for ledger",
            )

        # If amount is 0, no transaction needed - _transaction stays None
        self.accept()

    def get_transaction(self) -> Optional[Transaction]:
        """Get the opening balance transaction, or None if zero."""
        return self._transaction
