"""View transaction dialog (read-only details)."""

import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import qasync
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QIcon
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


def _icon_path(name: str) -> str:
    """Get path to a theme icon."""
    try:
        base = Path(sys._MEIPASS)
    except AttributeError:
        base = Path(__file__).resolve().parent.parent
    return str(base / "theme" / "icons" / name)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class ViewTransactionDialog(QDialog):
    """Dialog for viewing a single transaction (read-only)."""

    # Internal signal for async attachment loading (to work with qasync)
    _trigger_load_attachments = Signal()

    def __init__(
        self,
        transaction: Transaction,
        parent=None,
        context: Optional["ApplicationContext"] = None,
    ):
        super().__init__(parent)
        self._transaction = transaction
        self._context = context

        # Connect internal signal to async handler
        self._trigger_load_attachments.connect(self._handle_load_attachments)

        self.setWindowTitle("View Transaction")
        self.setModal(True)
        self.setMinimumWidth(520)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header row with copy button in the corner
        header_row = QHBoxLayout()
        header = QLabel("Transaction Details")
        header.setObjectName("section_header")
        header_row.addWidget(header)
        header_row.addStretch()

        self._clipboard_icon = QIcon(_icon_path("clipboard.svg"))
        self._clipboard_check_icon = QIcon(_icon_path("clipboard-check.svg"))

        self._copy_btn = QPushButton()
        self._copy_btn.setIcon(self._clipboard_icon)
        self._copy_btn.setIconSize(QSize(18, 18))
        self._copy_btn.setToolTip("Copy to clipboard")
        self._copy_btn.setFixedSize(30, 30)
        self._copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 0;
            }
            QPushButton:hover {
                background: rgba(128, 128, 128, 0.15);
                border-color: rgba(128, 128, 128, 0.3);
            }
            QPushButton:pressed {
                background: rgba(128, 128, 128, 0.25);
            }
        """)
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        header_row.addWidget(self._copy_btn)
        layout.addLayout(header_row)

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
        grid.addLayout(self._row("Reference", self._transaction.reference or "-")[0])
        grid.addLayout(self._row("Notes", self._transaction.notes or "-")[0])
        self._attachments_row, self._attachments_value = self._row("Attachments", "None")
        grid.addLayout(self._attachments_row)

        layout.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
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
        self._trigger_load_attachments.emit()

    @qasync.asyncSlot()
    async def _handle_load_attachments(self) -> None:
        """Handle async attachment loading (via signal)."""
        try:
            await self._load_attachments()
        except RuntimeError as e:
            if "Cannot enter into task" not in str(e):
                pass  # Ignore qasync re-entrancy
        except Exception:
            pass  # Silently handle - attachments are optional

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
        super().closeEvent(event)

    def _copy_to_clipboard(self) -> None:
        """Copy a formatted summary to clipboard for sharing."""
        QApplication.clipboard().setText(self._format_for_clipboard())
        # Brief visual feedback — swap to green check icon
        self._copy_btn.setIcon(self._clipboard_check_icon)
        QTimer.singleShot(1500, lambda: self._copy_btn.setIcon(self._clipboard_icon))

    def _format_for_clipboard(self) -> str:
        amount = self._format_amount(self._transaction)
        status = self._format_status(self._transaction.status)
        type_str = self._title_case(self._transaction.type.value)
        date_str = self._transaction.date.strftime("%d %b %Y")
        category = self._transaction.category or "-"
        party = self._transaction.party or "-"
        reference = self._transaction.reference or "-"
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
            f"Reference: {reference}\n"
            f"Notes: {notes}\n"
            f"Attachments: {attachments_text}"
        )
