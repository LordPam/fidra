"""View transaction dialog (read-only details)."""

import asyncio
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QDialogButtonBox,
    QPushButton,
    QApplication,
)

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class ViewTransactionDialog(QDialog):
    """Dialog for viewing a single transaction (read-only)."""

    def __init__(
        self,
        transaction: Transaction,
        parent=None,
        context: Optional["ApplicationContext"] = None,
    ):
        super().__init__(parent)
        self._transaction = transaction
        self._context = context
        self._attachments_task: Optional[asyncio.Task] = None

        self.setWindowTitle("View Transaction")
        self.setModal(True)
        self.setMinimumWidth(520)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        header = QLabel("Transaction Details")
        header.setObjectName("section_header")
        layout.addWidget(header)

        amount_value = QLabel(self._format_amount(self._transaction))
        amount_value.setObjectName("amount_value")
        amount_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        amount_value.setStyleSheet(self._amount_style())
        layout.addWidget(amount_value)

        sep1 = QFrame()
        sep1.setObjectName("balance_card_separator")
        sep1.setFrameShape(QFrame.HLine)
        layout.addWidget(sep1)

        grid = QVBoxLayout()
        grid.setSpacing(10)

        grid.addLayout(self._row("Date", self._transaction.date.strftime("%d %b %Y"))[0])
        grid.addLayout(self._row("Description", self._transaction.description)[0])
        grid.addLayout(self._row("Type", self._title_case(self._transaction.type.value))[0])
        grid.addLayout(self._row("Status", self._format_status(self._transaction.status))[0])
        grid.addLayout(self._row("Sheet", self._transaction.sheet)[0])
        grid.addLayout(self._row("Category", self._transaction.category or "-")[0])
        grid.addLayout(self._row("Party", self._transaction.party or "-")[0])
        grid.addLayout(self._row("Notes", self._transaction.notes or "-")[0])
        self._attachments_row, self._attachments_value = self._row("Attachments", "None")
        grid.addLayout(self._attachments_row)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        buttons.addButton(copy_btn, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)

        if self._context and self._context.attachment_service:
            QTimer.singleShot(0, self._start_load_attachments)

    def _row(self, label: str, value: str) -> tuple[QHBoxLayout, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(14)
        label_widget = QLabel(label)
        label_widget.setObjectName("secondary_text")
        label_widget.setFixedWidth(120)
        value_widget = QLabel(value)
        value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value_widget.setStyleSheet("font-weight: 600;")
        row.addWidget(label_widget)
        row.addWidget(value_widget, 1)
        return row, value_widget

    @staticmethod
    def _format_amount(transaction: Transaction) -> str:
        amount: Decimal = transaction.amount
        sign = "+" if transaction.type == TransactionType.INCOME else "-"
        return f"{sign}£{amount:,.2f}"

    @staticmethod
    def _format_status(status: ApprovalStatus) -> str:
        if status == ApprovalStatus.AUTO:
            return "Auto"
        return status.value.replace("_", " ").title()

    @staticmethod
    def _title_case(value: str) -> str:
        return value.replace("_", " ").title()

    def _amount_style(self) -> str:
        # Use red/green for this view to match transaction view conventions.
        if self._transaction.type == TransactionType.INCOME:
            return "color: #10b981; font-size: 20px; font-weight: 700;"
        return "color: #ef4444; font-size: 20px; font-weight: 700;"

    def _start_load_attachments(self) -> None:
        if not self._context or not self._context.attachment_service:
            return

        if self._attachments_task and not self._attachments_task.done():
            self._attachments_task.cancel()

        loop = asyncio.get_event_loop()
        self._attachments_task = loop.create_task(self._load_attachments())

    async def _load_attachments(self) -> None:
        if not self._context or not self._context.attachment_service:
            return

        try:
            attachments = await self._context.attachment_service.get_attachments(
                self._transaction.id
            )
        except Exception:
            return

        count = len(attachments)
        if count == 0:
            text = "None"
        elif count == 1:
            text = "1 file"
        else:
            text = f"{count} files"
        self._set_attachments_text(text)

    def _set_attachments_text(self, text: str) -> None:
        # Update the value label in the attachments row.
        if isinstance(self._attachments_value, QLabel):
            self._attachments_value.setText(text)

    def closeEvent(self, event) -> None:
        if self._attachments_task and not self._attachments_task.done():
            self._attachments_task.cancel()
        super().closeEvent(event)

    def _copy_to_clipboard(self) -> None:
        """Copy a formatted summary to clipboard for sharing."""
        QApplication.clipboard().setText(self._format_for_clipboard())

    def _format_for_clipboard(self) -> str:
        amount = self._format_amount(self._transaction)
        status = self._format_status(self._transaction.status)
        type_str = self._title_case(self._transaction.type.value)
        date_str = self._transaction.date.strftime("%d %b %Y")
        category = self._transaction.category or "-"
        party = self._transaction.party or "-"
        notes = self._transaction.notes or "-"

        attachments_text = "None"
        if isinstance(self._attachments_value, QLabel):
            attachments_text = self._attachments_value.text()

        return (
            f"Transaction details\n"
            f"Amount: {amount}\n"
            f"Date: {date_str}\n"
            f"Description: {self._transaction.description}\n"
            f"Type: {type_str}\n"
            f"Status: {status}\n"
            f"Sheet: {self._transaction.sheet}\n"
            f"Category: {category}\n"
            f"Party: {party}\n"
            f"Notes: {notes}\n"
            f"Attachments: {attachments_text}"
        )
