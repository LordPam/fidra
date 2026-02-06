"""Balance display widget."""

from decimal import Decimal
from datetime import datetime, date
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame

from fidra.domain.models import Transaction, TransactionType


class BalanceDisplayWidget(QWidget):
    """Widget displaying current balance prominently.

    Modern card-style design showing:
    - Current balance (large, prominent)
    - Projected balance (when Show Planned is ON)
    - Selection summary at bottom (when rows are selected)
    """

    def __init__(self, parent=None):
        """Initialize the balance display.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._current_balance = Decimal("0")
        self._previous_balance = Decimal("0")
        self._projected_balance: Optional[Decimal] = None
        self._last_updated = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(0)

        # ===== CURRENT BALANCE SECTION (top) =====
        current_section = QVBoxLayout()
        current_section.setSpacing(6)

        # Title
        self.title_label = QLabel("Current Balance")
        self.title_label.setObjectName("balance_card_title")
        current_section.addWidget(self.title_label)

        # Balance amount (large and prominent)
        self.balance_label = QLabel("£0.00")
        self.balance_label.setObjectName("balance_card_value")
        self.balance_label.setProperty("status", "neutral")
        current_section.addWidget(self.balance_label)

        # Change indicator
        self.change_label = QLabel("")
        self.change_label.setObjectName("balance_card_change")
        self.change_label.setProperty("direction", "neutral")
        current_section.addWidget(self.change_label)

        layout.addLayout(current_section)

        # ===== PROJECTED BALANCE SECTION (appears below current balance) =====
        projected_section = QVBoxLayout()
        projected_section.setSpacing(6)
        projected_section.setContentsMargins(0, 16, 0, 0)

        self.projected_title = QLabel("Projected Balance")
        self.projected_title.setObjectName("balance_card_subtitle")
        self.projected_title.setVisible(False)
        projected_section.addWidget(self.projected_title)

        self.projected_label = QLabel("£0.00")
        self.projected_label.setObjectName("balance_card_projected")
        self.projected_label.setProperty("status", "neutral")
        self.projected_label.setVisible(False)
        projected_section.addWidget(self.projected_label)

        self.projected_note = QLabel("Based on planned transactions")
        self.projected_note.setObjectName("balance_card_note")
        self.projected_note.setVisible(False)
        projected_section.addWidget(self.projected_note)

        layout.addLayout(projected_section)

        # ===== STRETCH (pushes selection to bottom) =====
        layout.addStretch()

        # ===== SELECTION SUMMARY SECTION (fixed at bottom) =====
        self.selection_separator = QFrame()
        self.selection_separator.setObjectName("balance_card_separator")
        self.selection_separator.setFrameShape(QFrame.HLine)
        self.selection_separator.setVisible(False)
        layout.addWidget(self.selection_separator)

        selection_section = QVBoxLayout()
        selection_section.setSpacing(4)
        selection_section.setContentsMargins(0, 12, 0, 12)

        self.selection_title = QLabel("Selection")
        self.selection_title.setObjectName("balance_card_subtitle")
        self.selection_title.setVisible(False)
        selection_section.addWidget(self.selection_title)

        # Selection amount (prominent)
        self.selection_amount = QLabel("£0.00")
        self.selection_amount.setObjectName("balance_card_selection_value")
        self.selection_amount.setProperty("status", "neutral")
        self.selection_amount.setVisible(False)
        selection_section.addWidget(self.selection_amount)

        # Selection count
        self.selection_count = QLabel("")
        self.selection_count.setObjectName("balance_card_note")
        self.selection_count.setVisible(False)
        selection_section.addWidget(self.selection_count)

        # Selection description
        self.selection_description = QLabel("")
        self.selection_description.setObjectName("balance_card_note")
        self.selection_description.setVisible(False)
        selection_section.addWidget(self.selection_description)

        # Selection date/range
        self.selection_date = QLabel("")
        self.selection_date.setObjectName("balance_card_note")
        self.selection_date.setVisible(False)
        selection_section.addWidget(self.selection_date)

        # Selection party
        self.selection_party = QLabel("")
        self.selection_party.setObjectName("balance_card_note")
        self.selection_party.setVisible(False)
        selection_section.addWidget(self.selection_party)

        layout.addLayout(selection_section)

        # ===== FOOTER =====
        self.updated_label = QLabel("")
        self.updated_label.setObjectName("balance_card_updated")
        layout.addWidget(self.updated_label)

    def set_balance(
        self,
        current: Decimal,
        previous: Optional[Decimal] = None,
        update_time: Optional[datetime] = None,
        projected: Optional[Decimal] = None,
        filtered: bool = False,
    ) -> None:
        """Update the displayed balance.

        Args:
            current: Current balance
            previous: Previous balance for change calculation
            update_time: Time of update (defaults to now)
            projected: Projected balance (when Show Planned is ON)
        """
        self._current_balance = current
        self._previous_balance = previous if previous is not None else current
        self._projected_balance = projected
        self._last_updated = update_time or datetime.now()

        self.title_label.setText("Filtered Balance" if filtered else "Current Balance")
        self.projected_title.setText(
            "Filtered Projected Balance" if filtered else "Projected Balance"
        )
        self._update_display()

    def set_selection(self, transactions: list[Transaction]) -> None:
        """Update the selection summary.

        Args:
            transactions: List of selected transactions
        """
        if not transactions:
            # Hide selection section
            self._hide_selection()
            return

        # Show selection section
        self._show_selection()

        # Calculate total amount (income positive, expense negative)
        total = Decimal("0")
        for t in transactions:
            if t.type == TransactionType.INCOME:
                total += t.amount
            else:
                total -= t.amount

        # Format amount
        amount_str = f"£{abs(total):,.2f}"
        if total < 0:
            amount_str = f"-{amount_str}"
            status = "negative"
        elif total > 0:
            amount_str = f"+{amount_str}"
            status = "positive"
        else:
            status = "neutral"

        self.selection_amount.setText(amount_str)
        self.selection_amount.setProperty("status", status)
        self.selection_amount.style().unpolish(self.selection_amount)
        self.selection_amount.style().polish(self.selection_amount)

        # Count
        count = len(transactions)
        self.selection_count.setText(f"{count} transaction{'s' if count != 1 else ''}")

        # Description
        descriptions = set(t.description for t in transactions if t.description)
        if len(descriptions) == 1:
            self.selection_description.setText(list(descriptions)[0])
            self.selection_description.setVisible(True)
        elif len(descriptions) > 1:
            self.selection_description.setText("Various items")
            self.selection_description.setVisible(True)
        else:
            self.selection_description.setVisible(False)

        # Date or date range
        dates = sorted(set(t.date for t in transactions))
        if len(dates) == 1:
            date_str = dates[0].strftime("%d %b %Y")
        else:
            date_str = f"{dates[0].strftime('%d %b')} – {dates[-1].strftime('%d %b %Y')}"
        self.selection_date.setText(date_str)

        # Party
        parties = set(t.party for t in transactions if t.party)
        if len(parties) == 0:
            self.selection_party.setVisible(False)
        elif len(parties) == 1:
            self.selection_party.setText(list(parties)[0])
            self.selection_party.setVisible(True)
        else:
            self.selection_party.setText("Various parties")
            self.selection_party.setVisible(True)

    def clear_selection(self) -> None:
        """Clear the selection summary."""
        self._hide_selection()

    def _show_selection(self) -> None:
        """Show selection summary section."""
        self.selection_separator.setVisible(True)
        self.selection_title.setVisible(True)
        self.selection_amount.setVisible(True)
        self.selection_count.setVisible(True)
        self.selection_date.setVisible(True)

    def _hide_selection(self) -> None:
        """Hide selection summary section."""
        self.selection_separator.setVisible(False)
        self.selection_title.setVisible(False)
        self.selection_amount.setVisible(False)
        self.selection_count.setVisible(False)
        self.selection_description.setVisible(False)
        self.selection_date.setVisible(False)
        self.selection_party.setVisible(False)

    def _update_display(self) -> None:
        """Update all display elements."""
        # Format balance
        balance_str = f"£{abs(self._current_balance):,.2f}"
        if self._current_balance < 0:
            balance_str = f"-{balance_str}"
            status = "negative"
        elif self._current_balance > 0:
            status = "positive"
        else:
            status = "neutral"

        self.balance_label.setText(balance_str)
        self.balance_label.setProperty("status", status)
        # Force style refresh
        self.balance_label.style().unpolish(self.balance_label)
        self.balance_label.style().polish(self.balance_label)

        # Update change indicator
        self._update_change_indicator()

        # Update timestamp
        if self._last_updated:
            time_str = self._last_updated.strftime("%b %d, %H:%M")
            self.updated_label.setText(f"Updated {time_str}")

        # Update projected balance (only visible if set)
        self._update_projected_balance()

    def _update_change_indicator(self) -> None:
        """Update the change indicator."""
        change = self._current_balance - self._previous_balance

        if change == 0:
            self.change_label.setText("")
            return

        if change > 0:
            change_str = f"+£{abs(change):,.2f}"
            direction = "up"
        else:
            change_str = f"-£{abs(change):,.2f}"
            direction = "down"

        self.change_label.setText(change_str)
        self.change_label.setProperty("direction", direction)
        # Force style refresh
        self.change_label.style().unpolish(self.change_label)
        self.change_label.style().polish(self.change_label)

    def _update_projected_balance(self) -> None:
        """Update the projected balance display."""
        if self._projected_balance is None:
            # Hide projected balance section
            self.projected_title.setVisible(False)
            self.projected_label.setVisible(False)
            self.projected_note.setVisible(False)
            return

        # Show projected balance section
        self.projected_title.setVisible(True)
        self.projected_label.setVisible(True)
        self.projected_note.setVisible(True)

        # Format projected balance
        projected_str = f"£{abs(self._projected_balance):,.2f}"
        if self._projected_balance < 0:
            projected_str = f"-{projected_str}"
            status = "negative"
        elif self._projected_balance > 0:
            status = "positive"
        else:
            status = "neutral"

        self.projected_label.setText(projected_str)
        self.projected_label.setProperty("status", status)
        # Force style refresh
        self.projected_label.style().unpolish(self.projected_label)
        self.projected_label.style().polish(self.projected_label)

    def get_balance(self) -> Decimal:
        """Get current balance.

        Returns:
            Current balance value
        """
        return self._current_balance
