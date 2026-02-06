"""Financial year settings dialog."""

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext

from fidra.services.financial_year import FinancialYearService


class FinancialYearDialog(QDialog):
    """Dialog for configuring the financial year start month.

    Allows the treasurer to set when their financial year begins,
    which affects reporting periods and year-end summaries.
    """

    MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    def __init__(self, context: "ApplicationContext", parent=None):
        super().__init__(parent)
        self._context = context
        self._changed = False

        self.setWindowTitle("Financial Year Settings")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QLabel("Financial Year")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Explanation
        info = QLabel(
            "Set the month your financial year begins. "
            "This affects how annual reports and summaries are calculated. "
            "For example, many UK clubs use April as their financial year start."
        )
        info.setWordWrap(True)
        info.setObjectName("secondary_text")
        layout.addWidget(info)

        layout.addSpacing(8)

        # Start month selector
        month_layout = QHBoxLayout()
        month_label = QLabel("Year starts in:")
        month_label.setMinimumWidth(100)
        month_layout.addWidget(month_label)

        self.month_combo = QComboBox()
        self.month_combo.addItems(self.MONTHS)
        self.month_combo.setMinimumHeight(32)

        # Set current value
        current_month = self._context.settings.financial_year.start_month
        self.month_combo.setCurrentIndex(current_month - 1)

        month_layout.addWidget(self.month_combo, 1)
        layout.addLayout(month_layout)

        # Preview of current period
        self.period_label = QLabel()
        self.period_label.setObjectName("secondary_text")
        self._update_period_preview()
        layout.addWidget(self.period_label)

        self.month_combo.currentIndexChanged.connect(self._update_period_preview)

        layout.addSpacing(8)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _update_period_preview(self) -> None:
        """Update the period preview label."""
        month = self.month_combo.currentIndex() + 1
        svc = FinancialYearService(start_month=month)
        period = svc.get_current_period()
        self.period_label.setText(
            f"Current financial year: {period.label} "
            f"({period.start_date.strftime('%d %b %Y')} to "
            f"{period.end_date.strftime('%d %b %Y')})"
        )

    def _on_accept(self) -> None:
        """Save the financial year setting."""
        new_month = self.month_combo.currentIndex() + 1
        old_month = self._context.settings.financial_year.start_month

        if new_month != old_month:
            self._context.settings.financial_year.start_month = new_month
            self._context.financial_year_service.start_month = new_month
            self._context.save_settings()
            self._changed = True

        self.accept()

    @property
    def was_changed(self) -> bool:
        """Whether the setting was actually changed."""
        return self._changed
