"""Dashboard view - overview of financial status with stats and charts."""

from typing import TYPE_CHECKING
from datetime import date, timedelta
from decimal import Decimal

import qasync
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QPushButton,
)
from PySide6.QtGui import QKeySequence, QShortcut

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.ui.components.charts import (
    BalanceTrendChart,
    IncomeVsExpenseChart,
)
from fidra.data.repository import ConcurrencyError
from fidra.services.undo import BulkEditCommand

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class MetricCard(QFrame):
    """A modern metric card for displaying key statistics."""

    def __init__(
        self,
        title: str,
        value: str = "£0.00",
        subtitle: str = "",
        accent_color: str = "default",
        parent=None
    ):
        """Initialize metric card.

        Args:
            title: Card title (e.g., "Current Balance")
            value: Main value to display
            subtitle: Optional subtitle/description
            accent_color: Color variant (default, success, danger, warning)
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("metric_card")
        self.setProperty("accent", accent_color)
        self._setup_ui(title, value, subtitle)

    def _setup_ui(self, title: str, value: str, subtitle: str) -> None:
        """Set up the card UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(1)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setObjectName("metric_card_title")
        layout.addWidget(self.title_label)

        # Value
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metric_card_value")
        layout.addWidget(self.value_label)

        # Subtitle
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("metric_card_subtitle")
        self.subtitle_label.setWordWrap(True)
        if not subtitle:
            self.subtitle_label.hide()
        layout.addWidget(self.subtitle_label)

    def set_value(self, value: str, subtitle: str = "") -> None:
        """Update card value and subtitle."""
        self.value_label.setText(value)
        if subtitle:
            self.subtitle_label.setText(subtitle)
            self.subtitle_label.show()
        elif not self.subtitle_label.text():
            self.subtitle_label.hide()


class ChartCard(QFrame):
    """A card container for charts with a title."""

    def __init__(self, title: str, chart_widget: QWidget, parent=None):
        """Initialize chart card.

        Args:
            title: Chart title
            chart_widget: The chart widget to embed
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("chart_card")
        self._setup_ui(title, chart_widget)

    def _setup_ui(self, title: str, chart_widget: QWidget) -> None:
        """Set up the card UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Allow card itself to shrink - Ignored policy allows any size
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.setMinimumSize(0, 0)

        # Title
        title_label = QLabel(title)
        title_label.setObjectName("chart_card_title")
        layout.addWidget(title_label)

        # Chart - allow shrinking with no minimum
        chart_widget.setMinimumSize(0, 0)
        layout.addWidget(chart_widget, 1)


class ActivityItem(QFrame):
    """A single item in an activity list."""

    def __init__(
        self,
        primary_text: str,
        secondary_text: str,
        amount: str,
        is_income: bool = False,
        parent=None
    ):
        """Initialize activity item.

        Args:
            primary_text: Main text (e.g., description)
            secondary_text: Secondary text (e.g., date)
            amount: Amount text (e.g., "£25.00")
            is_income: Whether this is income (affects color)
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("activity_item")
        self._setup_ui(primary_text, secondary_text, amount, is_income)

    def _setup_ui(
        self,
        primary_text: str,
        secondary_text: str,
        amount: str,
        is_income: bool
    ) -> None:
        """Set up the item UI."""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Left side: text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        primary = QLabel(primary_text)
        primary.setObjectName("activity_primary")
        text_layout.addWidget(primary)

        secondary = QLabel(secondary_text)
        secondary.setObjectName("activity_secondary")
        text_layout.addWidget(secondary)

        layout.addLayout(text_layout, 1)

        # Right side: amount
        amount_label = QLabel(amount)
        amount_label.setObjectName("activity_amount_income" if is_income else "activity_amount_expense")
        amount_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(amount_label)


class ActivityList(QFrame):
    """A list of activity items with a header."""

    def __init__(self, title: str, empty_text: str = "No items", parent=None):
        """Initialize activity list.

        Args:
            title: List title
            empty_text: Text to show when empty
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("activity_list")
        self._empty_text = empty_text
        self._setup_ui(title)

    def _setup_ui(self, title: str) -> None:
        """Set up the list UI."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Header
        header = QFrame()
        header.setObjectName("activity_list_header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 6, 8, 6)

        title_label = QLabel(title)
        title_label.setObjectName("activity_list_title")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self.layout.addWidget(header)

        # Items container
        self.items_container = QWidget()
        self.items_container.setObjectName("activity_items_container")
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(0)
        self.layout.addWidget(self.items_container)

        # Empty state
        self.empty_label = QLabel(self._empty_text)
        self.empty_label.setObjectName("activity_empty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.items_layout.addWidget(self.empty_label)

    def clear(self) -> None:
        """Clear all items."""
        while self.items_layout.count() > 0:
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.empty_label = QLabel(self._empty_text)
        self.empty_label.setObjectName("activity_empty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.items_layout.addWidget(self.empty_label)

    def add_item(
        self,
        primary_text: str,
        secondary_text: str,
        amount: str,
        is_income: bool = False
    ) -> None:
        """Add an item to the list."""
        # Remove empty label and stretches if present
        if self.empty_label:
            # Clear layout completely
            while self.items_layout.count() > 0:
                item = self.items_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.empty_label = None

        item = ActivityItem(primary_text, secondary_text, amount, is_income)
        self.items_layout.addWidget(item)

    def finish_adding(self) -> None:
        """Call after adding all items to add trailing stretch."""
        self.items_layout.addStretch(1)


class PendingApprovalItem(QFrame):
    """Single pending approval item with actions."""

    def __init__(
        self,
        transaction: Transaction,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("pending_item")
        self._transaction = transaction
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)

        primary = QLabel(self._transaction.description)
        primary.setObjectName("activity_primary")
        text_layout.addWidget(primary)

        secondary = QLabel(self._transaction.party or "-")
        secondary.setObjectName("activity_secondary")
        text_layout.addWidget(secondary)

        layout.addLayout(text_layout, 1)

        amount_label = QLabel(DashboardView._format_signed_amount(self._transaction))
        amount_label.setObjectName(
            "activity_amount_income"
            if self._transaction.type == TransactionType.INCOME
            else "activity_amount_expense"
        )
        amount_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(amount_label)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(4)

        self.approve_btn = QPushButton("Approve")
        self.approve_btn.setObjectName("pending_action")
        self.reject_btn = QPushButton("Reject")
        self.reject_btn.setObjectName("pending_action")
        self.actions.addWidget(self.approve_btn)
        self.actions.addWidget(self.reject_btn)

        self.actions_container = QWidget()
        self.actions_container.setObjectName("pending_actions_container")
        self.actions_container.setAttribute(Qt.WA_StyledBackground, True)
        self.actions_container.setLayout(self.actions)
        layout.addWidget(self.actions_container)

    def bind_actions(self, on_approve, on_reject) -> None:
        self.approve_btn.clicked.connect(lambda: on_approve(self._transaction))
        self.reject_btn.clicked.connect(lambda: on_reject(self._transaction))

    @property
    def transaction(self) -> Transaction:
        return self._transaction


class PendingApprovalList(QFrame):
    """Pending approvals list with header actions."""

    def __init__(self, title: str, empty_text: str = "No pending transactions", parent=None):
        super().__init__(parent)
        self.setObjectName("pending_list")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._empty_text = empty_text
        self._footer_label = None
        self._spacer_item = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.items_container = QWidget()
        self.items_container.setObjectName("pending_items_container")
        self.items_container.setAttribute(Qt.WA_StyledBackground, True)
        self.items_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(6, 6, 6, 6)
        self.items_layout.setSpacing(6)
        self.layout.addWidget(self.items_container)

        self.empty_label = QLabel(self._empty_text)
        self.empty_label.setObjectName("activity_empty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.items_layout.addWidget(self.empty_label)

    def clear(self) -> None:
        while self.items_layout.count() > 0:
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.empty_label = QLabel(self._empty_text)
        self.empty_label.setObjectName("activity_empty")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.items_layout.addStretch(1)
        self.items_layout.addWidget(self.empty_label)
        self.items_layout.addStretch(1)
        self._footer_label = None
        self._spacer_item = None

    def add_item(self, transaction: Transaction, on_approve, on_reject) -> None:
        if self.empty_label:
            while self.items_layout.count() > 0:
                item = self.items_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.empty_label = None

        item = PendingApprovalItem(transaction)
        item.bind_actions(on_approve, on_reject)
        self.items_layout.addWidget(item)

    def add_footer(self, text: str) -> None:
        self._footer_label = QLabel(text)
        self._footer_label.setObjectName("activity_secondary")
        self._footer_label.setAlignment(Qt.AlignCenter)
        self.items_layout.addWidget(self._footer_label)

    def ensure_spacer(self) -> None:
        if self._spacer_item is None:
            self._spacer_item = self.items_layout.addStretch(1)


class DashboardView(QWidget):
    """Dashboard view showing financial overview.

    Layout:
    - Top: Metric cards row (balance, this month, pending, count)
    - Middle: Charts grid (3 charts displayed simultaneously)
    - Bottom: Activity lists (recent transactions, upcoming planned)
    """

    # Internal signals for async operations (to work with qasync)
    _trigger_set_status = Signal(object, object)  # transaction, status
    _trigger_undo = Signal()

    def __init__(self, context: "ApplicationContext", parent=None):
        """Initialize dashboard view.

        Args:
            context: Application context
            parent: Parent widget
        """
        super().__init__(parent)
        self._context = context

        # Connect internal signals to async handlers
        self._trigger_set_status.connect(self._handle_set_status)
        self._trigger_undo.connect(self._handle_undo)

        self._setup_ui()
        self._connect_signals()

        # Initial data load
        self._update_dashboard()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        # Main scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Content widget
        content = QWidget()
        content.setObjectName("dashboard_content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ===== METRICS ROW =====
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(8)

        self.balance_card = MetricCard(
            "Current Balance",
            "£0.00",
            accent_color="default"
        )
        self.balance_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        metrics_layout.addWidget(self.balance_card)

        self.month_card = MetricCard(
            "This Month",
            "£0.00",
            accent_color="default"
        )
        self.month_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        metrics_layout.addWidget(self.month_card)

        self.income_card = MetricCard(
            "Monthly Income",
            "£0.00",
            accent_color="danger"
        )
        self.income_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        metrics_layout.addWidget(self.income_card)

        self.expense_card = MetricCard(
            "Monthly Expenses",
            "£0.00",
            accent_color="success"
        )
        self.expense_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        metrics_layout.addWidget(self.expense_card)

        layout.addLayout(metrics_layout)

        # ===== CHARTS ROW =====
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(8)

        # Balance trend chart - Ignored policy allows shrinking
        self.balance_chart = BalanceTrendChart()
        balance_card = ChartCard("Balance Trend (90 days)", self.balance_chart)
        balance_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        balance_card.setMinimumSize(0, 0)
        charts_layout.addWidget(balance_card, 1)

        # Income vs Expenses chart - Ignored policy allows shrinking
        self.income_expense_chart = IncomeVsExpenseChart()
        income_expense_card = ChartCard("Income vs Expenses", self.income_expense_chart)
        income_expense_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        income_expense_card.setMinimumSize(0, 0)
        charts_layout.addWidget(income_expense_card, 1)

        # Pending approvals widget
        self.pending_list = PendingApprovalList(
            "Pending Approvals",
            "No pending transactions"
        )
        pending_card = ChartCard("Pending Approvals", self.pending_list)
        pending_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        pending_card.setMinimumSize(0, 0)
        charts_layout.addWidget(pending_card, 1)

        layout.addLayout(charts_layout, 1)

        # ===== ACTIVITY LISTS =====
        activity_layout = QHBoxLayout()
        activity_layout.setSpacing(8)

        self.recent_list = ActivityList(
            "Recent Transactions",
            "No recent transactions"
        )
        self.recent_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        activity_layout.addWidget(self.recent_list)

        self.upcoming_list = ActivityList(
            "Upcoming Planned",
            "No upcoming transactions"
        )
        self.upcoming_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        activity_layout.addWidget(self.upcoming_list)

        layout.addLayout(activity_layout)

        # Set scroll content
        scroll.setWidget(content)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._context.state.transactions.changed.connect(self._on_transactions_changed)
        self._context.state.planned_templates.changed.connect(self._on_planned_changed)

        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_shortcut.activated.connect(self._on_undo_shortcut)

    def _on_transactions_changed(self, transactions: list[Transaction]) -> None:
        """Handle transactions list change."""
        self._update_dashboard()

    def _on_planned_changed(self, templates: list) -> None:
        """Handle planned templates change."""
        self._update_dashboard()

    def _update_dashboard(self) -> None:
        """Update all dashboard statistics and lists."""
        transactions = self._context.state.transactions.value

        # Current balance
        current_balance = self._context.balance_service.compute_total(transactions)
        fy_period = self._context.financial_year_service.get_current_period()
        self.balance_card.set_value(
            f"£{current_balance:,.2f}",
            f"FY {fy_period.label}"
        )

        # Update charts
        self.balance_chart.update_data(
            transactions,
            self._context.balance_service,
            days=90
        )
        self.income_expense_chart.update_data(transactions)  # Uses default last ~6 months

        # This month calculations
        today = date.today()
        month_start = today.replace(day=1)
        month_transactions = [
            t for t in transactions
            if month_start <= t.date <= today
        ]

        month_income = sum(
            t.amount for t in month_transactions
            if t.type == TransactionType.INCOME
        )
        month_expenses = sum(
            t.amount for t in month_transactions
            if t.type == TransactionType.EXPENSE
        )
        month_net = month_income - month_expenses

        # Update metric cards
        net_sign = "+" if month_net >= 0 else ""
        self.month_card.set_value(
            f"{net_sign}£{month_net:,.2f}",
            f"Net for {today.strftime('%B %Y')}"
        )

        self.income_card.set_value(
            f"£{month_income:,.2f}",
            f"{sum(1 for t in month_transactions if t.type == TransactionType.INCOME)} transactions"
        )

        self.expense_card.set_value(
            f"£{month_expenses:,.2f}",
            f"{sum(1 for t in month_transactions if t.type == TransactionType.EXPENSE)} transactions"
        )

        # Recent transactions (cap at 3)
        self.recent_list.clear()
        recent_source = [
            t for t in transactions
            if t.status not in (ApprovalStatus.PENDING, ApprovalStatus.REJECTED)
        ]
        # Normalize created_at for sorting (handle mix of tz-aware and tz-naive)
        def recent_sort_key(t):
            created = t.created_at
            if created and created.tzinfo is not None:
                created = created.replace(tzinfo=None)
            return (t.date, created)
        recent = sorted(recent_source, key=recent_sort_key, reverse=True)[:3]
        for t in recent:
            self.recent_list.add_item(
                t.description,
                t.date.strftime("%b %d, %Y"),
                self._format_signed_amount(t),
                is_income=(t.type == TransactionType.INCOME)
            )
        if recent:
            self.recent_list.finish_adding()

        # Upcoming planned
        self.upcoming_list.clear()
        templates = self._context.state.planned_templates.value
        horizon = today + timedelta(days=30)

        upcoming_instances = []
        for template in templates:
            instances = self._context.forecast_service.expand_template(
                template,
                horizon,
                include_past=False
            )
            upcoming_instances.extend(instances)

        upcoming_instances.sort(key=lambda t: t.date)
        for t in upcoming_instances[:3]:
            self.upcoming_list.add_item(
                t.description,
                t.date.strftime("%b %d, %Y"),
                self._format_signed_amount(t),
                is_income=(t.type == TransactionType.INCOME)
            )
        if upcoming_instances:
            self.upcoming_list.finish_adding()

        # Pending approvals (all sheets)
        self._update_pending_list(transactions)

    @staticmethod
    def _format_signed_amount(transaction: Transaction) -> str:
        """Format amount with explicit sign by transaction type."""
        sign = "+" if transaction.type == TransactionType.INCOME else "-"
        return f"{sign}£{transaction.amount:,.2f}"

    def _update_pending_list(self, transactions: list[Transaction]) -> None:
        """Update pending approvals widget."""
        pending = [
            t for t in transactions
            if t.status == ApprovalStatus.PENDING
            and t.status != ApprovalStatus.PLANNED
        ]
        # Normalize created_at for sorting (handle mix of tz-aware and tz-naive)
        def sort_key(t):
            created = t.created_at
            if created and created.tzinfo is not None:
                created = created.replace(tzinfo=None)
            return (t.date, created)
        pending.sort(key=sort_key)

        self.pending_list.clear()

        max_items = 5
        for t in pending[:max_items]:
            self.pending_list.add_item(t, self._approve_pending, self._reject_pending)

        if len(pending) > max_items:
            self.pending_list.add_footer(f"{len(pending) - max_items} more pending…")
            self.pending_list.ensure_spacer()
        elif pending:
            self.pending_list.ensure_spacer()

    def _approve_pending(self, transaction: Transaction) -> None:
        self._trigger_set_status.emit(transaction, ApprovalStatus.APPROVED)

    def _reject_pending(self, transaction: Transaction) -> None:
        self._trigger_set_status.emit(transaction, ApprovalStatus.REJECTED)

    def _on_undo_shortcut(self) -> None:
        self._trigger_undo.emit()

    @qasync.asyncSlot(object, object)
    async def _handle_set_status(self, transaction: Transaction, status: ApprovalStatus) -> None:
        """Handle async set status (via signal)."""
        try:
            await self._set_pending_status(transaction, status)
        except RuntimeError as e:
            if "Cannot enter into task" not in str(e):
                raise

    @qasync.asyncSlot()
    async def _handle_undo(self) -> None:
        """Handle async undo (via signal)."""
        try:
            await self._undo_last_action()
        except RuntimeError as e:
            if "Cannot enter into task" not in str(e):
                raise

    async def _set_pending_status(self, transaction: Transaction, status: ApprovalStatus) -> None:
        """Approve or reject a pending transaction."""
        try:
            old_states = [transaction]

            # Build updates - optionally set date to today on approval
            updates = {"status": status}
            if (status == ApprovalStatus.APPROVED and
                    self._context.settings.transactions.date_on_approve):
                updates["date"] = date.today()

            new_states = [transaction.with_updates(**updates)]
            command = BulkEditCommand(
                self._context.transaction_repo,
                old_states,
                new_states,
                audit_service=self._context.audit_service,
            )
            await self._context.undo_stack.execute(command)
            await self._reload_transactions()
        except ConcurrencyError:
            await self._reload_transactions()
        except Exception:
            await self._reload_transactions()

    async def _undo_last_action(self) -> None:
        """Undo last action via shared undo stack."""
        try:
            if self._context.undo_stack.can_undo:
                await self._context.undo_stack.undo()
                await self._reload_transactions()
        except Exception:
            await self._reload_transactions()

    async def _reload_transactions(self) -> None:
        """Reload all transactions into state."""
        try:
            transactions = await self._context.transaction_repo.get_all()
            self._context.state.transactions.set(transactions)
        except Exception:
            pass

    def refresh_theme(self) -> None:
        """Refresh chart colors after theme change."""
        self.balance_chart.refresh_theme()
        self.income_expense_chart.refresh_theme()
