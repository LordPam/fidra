"""Transaction behavior settings dialog."""

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class TransactionSettingsDialog(QDialog):
    """Dialog for configuring transaction behavior settings.

    Allows the user to configure:
    - Whether to set date to today when approving transactions
    - Whether to set date to today when converting planned to actual
    """

    def __init__(self, context: "ApplicationContext", parent=None):
        super().__init__(parent)
        self._context = context

        self.setWindowTitle("Transaction Settings")
        self.setModal(True)
        self.setMinimumWidth(450)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("Transaction Behavior")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Explanation
        info = QLabel(
            "Configure how transaction dates are handled during approval "
            "and when converting planned transactions to actual."
        )
        info.setWordWrap(True)
        info.setObjectName("secondary_text")
        layout.addWidget(info)

        layout.addSpacing(12)

        # Date on approve checkbox
        self.date_on_approve_cb = QCheckBox("Set date to today when approving transactions")
        self.date_on_approve_cb.setChecked(
            self._context.settings.transactions.date_on_approve
        )
        layout.addWidget(self.date_on_approve_cb)

        # Help text for date on approve
        approve_help = QLabel(
            "When enabled, approving a pending transaction will update its date to today."
        )
        approve_help.setWordWrap(True)
        approve_help.setObjectName("secondary_text")
        approve_help.setContentsMargins(24, 0, 0, 0)
        layout.addWidget(approve_help)

        layout.addSpacing(8)

        # Date on planned conversion checkbox
        self.date_on_conversion_cb = QCheckBox(
            "Set date to today when converting planned to actual"
        )
        self.date_on_conversion_cb.setChecked(
            self._context.settings.transactions.date_on_planned_conversion
        )
        layout.addWidget(self.date_on_conversion_cb)

        # Help text for date on conversion
        conversion_help = QLabel(
            "When enabled, converting a planned transaction to an actual transaction "
            "will set its date to today instead of keeping the planned date."
        )
        conversion_help.setWordWrap(True)
        conversion_help.setObjectName("secondary_text")
        conversion_help.setContentsMargins(24, 0, 0, 0)
        layout.addWidget(conversion_help)

        layout.addSpacing(16)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self) -> None:
        """Save the settings."""
        self._context.settings.transactions.date_on_approve = (
            self.date_on_approve_cb.isChecked()
        )
        self._context.settings.transactions.date_on_planned_conversion = (
            self.date_on_conversion_cb.isChecked()
        )
        self._context.save_settings()
        self.accept()
