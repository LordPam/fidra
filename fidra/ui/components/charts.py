"""Chart widgets using pyqtgraph for financial visualizations."""

from typing import TYPE_CHECKING, Optional
from datetime import date, timedelta
from decimal import Decimal
from collections import defaultdict

import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, QSize

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.ui.theme.engine import get_theme_engine

if TYPE_CHECKING:
    from fidra.services.balance import BalanceService


# Configure pyqtgraph defaults
pg.setConfigOptions(antialias=True)


class ShrinkablePlotWidget(pg.PlotWidget):
    """PlotWidget subclass that allows vertical shrinking.

    pyqtgraph's PlotWidget inherits from QGraphicsView which has a default
    sizeHint of 640x480. This subclass overrides sizeHint to return a minimal
    size, allowing the widget to shrink properly in layouts.
    """

    def sizeHint(self) -> QSize:
        """Return a minimal size hint to allow shrinking."""
        return QSize(100, 80)

    def minimumSizeHint(self) -> QSize:
        """Return a minimal minimum size hint."""
        return QSize(50, 40)


class BalanceTrendChart(QWidget):
    """Line chart showing balance over time.

    Displays running balance for a period (e.g., 90 days).
    """

    def __init__(self, parent=None):
        """Initialize balance trend chart.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        # Store last data for redraw on theme change
        self._last_transactions = None
        self._last_balance_service = None
        self._last_days = 90
        self._last_start_date: Optional[date] = None
        self._last_end_date: Optional[date] = None
        self._plot_days: list[int] = []
        self._plot_balances: list[float] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the chart UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Allow this widget to shrink - use Ignored to allow any size
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.setMinimumSize(0, 0)

        # Get theme colors
        theme = get_theme_engine()
        bg_color = theme.get_color('bg_secondary')
        text_color = theme.get_color('text_primary')
        border_color = theme.get_color('border')

        # Create plot widget (using shrinkable version)
        self.plot_widget = ShrinkablePlotWidget()
        self.plot_widget.setTitle("Balance Trend", color=text_color)
        self.plot_widget.setLabel('left', 'Balance (£)', color=text_color)
        self.plot_widget.setLabel('bottom', 'Days', color=text_color)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setBackground(bg_color)
        self.plot_widget.getAxis('left').setPen(border_color)
        self.plot_widget.getAxis('bottom').setPen(border_color)
        self.plot_widget.getAxis('left').setTextPen(text_color)
        self.plot_widget.getAxis('bottom').setTextPen(text_color)

        # Disable interactivity for dashboard display
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.hideButtons()

        # Allow plot widget to shrink - Ignored policy allows any size
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.plot_widget.setMinimumSize(0, 0)

        layout.addWidget(self.plot_widget)

        # Hover tooltip support
        self._hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved,
        )

    def refresh_theme(self) -> None:
        """Refresh chart colors based on current theme."""
        theme = get_theme_engine()
        bg_color = theme.get_color('bg_secondary')
        text_color = theme.get_color('text_primary')
        border_color = theme.get_color('border')

        self.plot_widget.setBackground(bg_color)
        self.plot_widget.setTitle("Balance Trend", color=text_color)
        self.plot_widget.setLabel('left', 'Balance (£)', color=text_color)
        self.plot_widget.setLabel('bottom', 'Days', color=text_color)
        self.plot_widget.getAxis('left').setPen(border_color)
        self.plot_widget.getAxis('bottom').setPen(border_color)
        self.plot_widget.getAxis('left').setTextPen(text_color)
        self.plot_widget.getAxis('bottom').setTextPen(text_color)

        # Redraw data with new theme colors
        if self._last_transactions is not None and self._last_balance_service is not None:
            self.update_data(
                self._last_transactions,
                self._last_balance_service,
                self._last_days,
                self._last_start_date,
                self._last_end_date
            )

    def update_data(
        self,
        transactions: list[Transaction],
        balance_service: "BalanceService",
        days: int = 90,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> None:
        """Update chart with transaction data.

        Args:
            transactions: List of transactions
            balance_service: Balance service for calculations
            days: Number of days to show (default 90, ignored if start/end provided)
            start_date: Optional explicit start date
            end_date: Optional explicit end date
        """
        # Store data for redraw on theme change
        self._last_transactions = transactions
        self._last_balance_service = balance_service
        self._last_days = days
        self._last_start_date = start_date
        self._last_end_date = end_date

        self.plot_widget.clear()

        if not transactions:
            return

        # Get date range - use explicit dates if provided, otherwise use days from today
        if start_date is not None and end_date is not None:
            pass  # Use provided dates
        else:
            end_date = date.today()
            start_date = end_date - timedelta(days=days)

        days = (end_date - start_date).days

        # Filter to valid transactions (not planned/rejected)
        valid_transactions = [
            t for t in transactions
            if t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
        ]

        if not valid_transactions:
            return

        # Calculate opening balance from all transactions BEFORE the chart window
        opening_balance = Decimal('0')
        for t in valid_transactions:
            if t.date < start_date:
                if t.type == TransactionType.INCOME:
                    opening_balance += t.amount
                else:
                    opening_balance -= t.amount

        # Filter transactions in range for the chart
        filtered = [
            t for t in valid_transactions
            if start_date <= t.date <= end_date
        ]

        # Sort by date and description for consistent ordering
        filtered.sort(key=lambda t: (t.date, t.description.lower()))

        # Calculate running balance for each day, starting from opening balance
        daily_balances = {}
        running_balance = opening_balance

        for t in filtered:
            if t.type == TransactionType.INCOME:
                running_balance += t.amount
            else:
                running_balance -= t.amount
            daily_balances[t.date] = float(running_balance)

        # Fill in missing days with previous balance
        all_dates = []
        all_balances = []
        current_balance = float(opening_balance)

        for i in range(days + 1):
            d = start_date + timedelta(days=i)
            if d in daily_balances:
                current_balance = daily_balances[d]
            all_dates.append(i)
            all_balances.append(current_balance)

        self._plot_days = all_dates
        self._plot_balances = all_balances

        # Plot line using theme chart colors
        theme = get_theme_engine()
        chart_accent = theme.get_color('chart_accent')
        chart_expense = theme.get_color('chart_expense')

        pen = pg.mkPen(color=chart_accent, width=2)
        self.plot_widget.plot(all_dates, all_balances, pen=pen)

        # Add zero line
        zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(chart_expense, style=Qt.DashLine))
        self.plot_widget.addItem(zero_line)

    def _on_mouse_moved(self, event) -> None:
        """Show nearest balance value on hover."""
        if not self._plot_days:
            self.plot_widget.setToolTip("")
            return

        pos = event[0]
        vb = self.plot_widget.getPlotItem().vb
        mouse_point = vb.mapSceneToView(pos)
        day_idx = int(round(mouse_point.x()))

        if day_idx < 0 or day_idx >= len(self._plot_days):
            self.plot_widget.setToolTip("")
            return

        balance = self._plot_balances[day_idx]
        self.plot_widget.setToolTip(f"Day {day_idx}: £{balance:,.2f}")


class ExpensesByCategoryChart(QWidget):
    """Bar chart showing expenses grouped by category."""

    def __init__(self, parent=None):
        """Initialize expenses by category chart.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        # Store last data for redraw on theme change
        self._last_transactions = None
        self._last_start_date = None
        self._last_end_date = None
        self._bar_categories: list[str] = []
        self._bar_amounts: list[float] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the chart UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Allow this widget to shrink - Ignored policy allows any size
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.setMinimumSize(0, 0)

        # Get theme colors
        theme = get_theme_engine()
        bg_color = theme.get_color('bg_secondary')
        text_color = theme.get_color('text_primary')
        border_color = theme.get_color('border')

        # Create plot widget (using shrinkable version)
        self.plot_widget = ShrinkablePlotWidget()
        self.plot_widget.setTitle("Expenses by Category", color=text_color)
        self.plot_widget.setLabel('left', 'Amount (£)', color=text_color)
        self.plot_widget.setLabel('bottom', 'Category', color=text_color)
        self.plot_widget.showGrid(x=False, y=True, alpha=0.3)
        self.plot_widget.setBackground(bg_color)
        self.plot_widget.getAxis('left').setPen(border_color)
        self.plot_widget.getAxis('bottom').setPen(border_color)
        self.plot_widget.getAxis('left').setTextPen(text_color)
        self.plot_widget.getAxis('bottom').setTextPen(text_color)

        # Disable interactivity for dashboard display
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.hideButtons()

        # Allow plot widget to shrink
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.plot_widget.setMinimumSize(0, 0)

        layout.addWidget(self.plot_widget)

        # Hover tooltip support (full category names + values)
        self._hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved,
        )

    def refresh_theme(self) -> None:
        """Refresh chart colors based on current theme."""
        theme = get_theme_engine()
        bg_color = theme.get_color('bg_secondary')
        text_color = theme.get_color('text_primary')
        border_color = theme.get_color('border')

        self.plot_widget.setBackground(bg_color)
        self.plot_widget.setTitle("Expenses by Category", color=text_color)
        self.plot_widget.setLabel('left', 'Amount (£)', color=text_color)
        self.plot_widget.setLabel('bottom', 'Category', color=text_color)
        self.plot_widget.getAxis('left').setPen(border_color)
        self.plot_widget.getAxis('bottom').setPen(border_color)
        self.plot_widget.getAxis('left').setTextPen(text_color)
        self.plot_widget.getAxis('bottom').setTextPen(text_color)

        # Redraw data with new theme colors
        if self._last_transactions is not None:
            self.update_data(self._last_transactions, self._last_start_date, self._last_end_date)

    def update_data(
        self,
        transactions: list[Transaction],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> None:
        """Update chart with transaction data.

        Args:
            transactions: List of transactions
            start_date: Optional start date filter
            end_date: Optional end date filter
        """
        # Store data for redraw on theme change
        self._last_transactions = transactions
        self._last_start_date = start_date
        self._last_end_date = end_date

        self.plot_widget.clear()

        if not transactions:
            return

        # Filter to expenses only
        expenses = [
            t for t in transactions
            if t.type == TransactionType.EXPENSE
            and t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
        ]

        # Apply date filter if provided
        if start_date:
            expenses = [t for t in expenses if t.date >= start_date]
        if end_date:
            expenses = [t for t in expenses if t.date <= end_date]

        if not expenses:
            return

        # Group by category
        category_totals = defaultdict(Decimal)
        for t in expenses:
            category = t.category or "Uncategorized"
            category_totals[category] += t.amount

        if not category_totals:
            return

        # Prepare data for bar chart: keep top categories + aggregate remainder.
        sorted_categories = sorted(
            category_totals.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        max_categories = 5
        if len(sorted_categories) > max_categories:
            top = sorted_categories[: max_categories - 1]
            other_total = sum(amount for _, amount in sorted_categories[max_categories - 1 :])
            sorted_categories = top + [("Other", other_total)]

        categories = [c for c, _ in sorted_categories]
        amounts = [float(amount) for _, amount in sorted_categories]
        self._bar_categories = categories
        self._bar_amounts = amounts

        # Create bar chart using brand chart color for expenses
        theme = get_theme_engine()
        chart_expense = theme.get_color('chart_expense')

        x = list(range(len(categories)))

        # Create bar graph item
        bg = pg.BarGraphItem(
            x=x,
            height=amounts,
            width=0.6,
            brush=chart_expense
        )
        self.plot_widget.addItem(bg)

        # Set x-axis labels
        ax = self.plot_widget.getAxis('bottom')
        ax.setStyle(
            tickTextOffset=8,
            autoExpandTextSpace=True,
            hideOverlappingLabels=True,
        )
        ax.setTicks([[(i, (cat[:9] + "…") if len(cat) > 9 else cat) for i, cat in enumerate(categories)]])

    def _on_mouse_moved(self, event) -> None:
        """Show full category name and amount on hover."""
        if not self._bar_categories:
            self.plot_widget.setToolTip("")
            return

        pos = event[0]
        vb = self.plot_widget.getPlotItem().vb
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        idx = int(round(x))

        if idx < 0 or idx >= len(self._bar_categories) or abs(x - idx) > 0.5:
            self.plot_widget.setToolTip("")
            return

        category = self._bar_categories[idx]
        amount = self._bar_amounts[idx]
        self.plot_widget.setToolTip(f"{category}\n£{amount:,.2f}")


class IncomeByCategoryChart(QWidget):
    """Bar chart showing income grouped by category."""

    def __init__(self, parent=None):
        """Initialize income by category chart.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._last_transactions = None
        self._last_start_date = None
        self._last_end_date = None
        self._bar_categories: list[str] = []
        self._bar_amounts: list[float] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the chart UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.setMinimumSize(0, 0)

        theme = get_theme_engine()
        bg_color = theme.get_color('bg_secondary')
        text_color = theme.get_color('text_primary')
        border_color = theme.get_color('border')

        self.plot_widget = ShrinkablePlotWidget()
        self.plot_widget.setTitle("Income by Category", color=text_color)
        self.plot_widget.setLabel('left', 'Amount (£)', color=text_color)
        self.plot_widget.setLabel('bottom', 'Category', color=text_color)
        self.plot_widget.showGrid(x=False, y=True, alpha=0.3)
        self.plot_widget.setBackground(bg_color)
        self.plot_widget.getAxis('left').setPen(border_color)
        self.plot_widget.getAxis('bottom').setPen(border_color)
        self.plot_widget.getAxis('left').setTextPen(text_color)
        self.plot_widget.getAxis('bottom').setTextPen(text_color)

        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.hideButtons()

        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.plot_widget.setMinimumSize(0, 0)

        layout.addWidget(self.plot_widget)

        self._hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved,
        )

    def refresh_theme(self) -> None:
        """Refresh chart colors based on current theme."""
        theme = get_theme_engine()
        bg_color = theme.get_color('bg_secondary')
        text_color = theme.get_color('text_primary')
        border_color = theme.get_color('border')

        self.plot_widget.setBackground(bg_color)
        self.plot_widget.setTitle("Income by Category", color=text_color)
        self.plot_widget.setLabel('left', 'Amount (£)', color=text_color)
        self.plot_widget.setLabel('bottom', 'Category', color=text_color)
        self.plot_widget.getAxis('left').setPen(border_color)
        self.plot_widget.getAxis('bottom').setPen(border_color)
        self.plot_widget.getAxis('left').setTextPen(text_color)
        self.plot_widget.getAxis('bottom').setTextPen(text_color)

        if self._last_transactions is not None:
            self.update_data(self._last_transactions, self._last_start_date, self._last_end_date)

    def update_data(
        self,
        transactions: list[Transaction],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> None:
        """Update chart with transaction data.

        Args:
            transactions: List of transactions
            start_date: Optional start date filter
            end_date: Optional end date filter
        """
        self._last_transactions = transactions
        self._last_start_date = start_date
        self._last_end_date = end_date

        self.plot_widget.clear()

        if not transactions:
            return

        income = [
            t for t in transactions
            if t.type == TransactionType.INCOME
            and t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
        ]

        if start_date:
            income = [t for t in income if t.date >= start_date]
        if end_date:
            income = [t for t in income if t.date <= end_date]

        if not income:
            return

        category_totals = defaultdict(Decimal)
        for t in income:
            category = t.category or "Uncategorized"
            category_totals[category] += t.amount

        if not category_totals:
            return

        sorted_categories = sorted(
            category_totals.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        max_categories = 5
        if len(sorted_categories) > max_categories:
            top = sorted_categories[: max_categories - 1]
            other_total = sum(amount for _, amount in sorted_categories[max_categories - 1 :])
            sorted_categories = top + [("Other", other_total)]

        categories = [c for c, _ in sorted_categories]
        amounts = [float(amount) for _, amount in sorted_categories]
        self._bar_categories = categories
        self._bar_amounts = amounts

        theme = get_theme_engine()
        chart_income = theme.get_color('chart_income')

        x = list(range(len(categories)))
        bg = pg.BarGraphItem(
            x=x,
            height=amounts,
            width=0.6,
            brush=chart_income
        )
        self.plot_widget.addItem(bg)

        ax = self.plot_widget.getAxis('bottom')
        ax.setStyle(
            tickTextOffset=8,
            autoExpandTextSpace=True,
            hideOverlappingLabels=True,
        )
        ax.setTicks([[(i, (cat[:9] + "…") if len(cat) > 9 else cat) for i, cat in enumerate(categories)]])

    def _on_mouse_moved(self, event) -> None:
        """Show full category name and amount on hover."""
        if not self._bar_categories:
            self.plot_widget.setToolTip("")
            return

        pos = event[0]
        vb = self.plot_widget.getPlotItem().vb
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        idx = int(round(x))

        if idx < 0 or idx >= len(self._bar_categories) or abs(x - idx) > 0.5:
            self.plot_widget.setToolTip("")
            return

        category = self._bar_categories[idx]
        amount = self._bar_amounts[idx]
        self.plot_widget.setToolTip(f"{category}\n£{amount:,.2f}")


class IncomeVsExpenseChart(QWidget):
    """Grouped bar chart comparing income and expenses by month."""

    def __init__(self, parent=None):
        """Initialize income vs expense chart.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        # Store last data for redraw on theme change
        self._last_transactions = None
        self._last_start_date: Optional[date] = None
        self._last_end_date: Optional[date] = None
        self._month_labels: list[str] = []
        self._income_data: list[float] = []
        self._expense_data: list[float] = []
        self._bar_width = 0.35
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the chart UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Allow this widget to shrink - Ignored policy allows any size
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.setMinimumSize(0, 0)

        # Get theme colors
        theme = get_theme_engine()
        bg_color = theme.get_color('bg_secondary')
        text_color = theme.get_color('text_primary')
        border_color = theme.get_color('border')

        # Create plot widget (using shrinkable version)
        self.plot_widget = ShrinkablePlotWidget()
        self.plot_widget.setTitle("Income vs Expenses", color=text_color)
        self.plot_widget.setLabel('left', 'Amount (£)', color=text_color)
        self.plot_widget.setLabel('bottom', 'Month', color=text_color)
        self.plot_widget.showGrid(x=False, y=True, alpha=0.3)
        self.plot_widget.setBackground(bg_color)
        self.plot_widget.getAxis('left').setPen(border_color)
        self.plot_widget.getAxis('bottom').setPen(border_color)
        self.plot_widget.getAxis('left').setTextPen(text_color)
        self.plot_widget.getAxis('bottom').setTextPen(text_color)
        # Disable interactivity for dashboard display
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.hideButtons()

        # Allow plot widget to shrink
        self.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.plot_widget.setMinimumSize(0, 0)

        layout.addWidget(self.plot_widget)

        # Static legend row to avoid overlap with plotted bars.
        self.legend_row = QWidget()
        self.legend_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.legend_row.setFixedHeight(20)
        legend_layout = QHBoxLayout(self.legend_row)
        legend_layout.setContentsMargins(2, 0, 2, 0)
        legend_layout.setSpacing(10)
        legend_layout.addStretch()

        self.legend_income = QLabel()
        self.legend_expense = QLabel()
        self.legend_income.setStyleSheet("font-size: 10px;")
        self.legend_expense.setStyleSheet("font-size: 10px;")
        legend_layout.addWidget(self.legend_income)
        legend_layout.addWidget(self.legend_expense)
        legend_layout.addStretch()
        layout.addWidget(self.legend_row)

        self._update_legend_colors()

        # Hover tooltip support
        self._hover_proxy = pg.SignalProxy(
            self.plot_widget.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved,
        )

    def _update_legend_colors(self) -> None:
        """Update legend swatch colors based on current theme."""
        theme = get_theme_engine()
        income = theme.get_color('chart_income')
        expense = theme.get_color('chart_expense')
        self.legend_income.setText(f"<span style='font-size:9px;color:{income}'>■</span> Income")
        self.legend_expense.setText(f"<span style='font-size:9px;color:{expense}'>■</span> Expenses")

    def refresh_theme(self) -> None:
        """Refresh chart colors based on current theme."""
        theme = get_theme_engine()
        bg_color = theme.get_color('bg_secondary')
        text_color = theme.get_color('text_primary')
        border_color = theme.get_color('border')

        self.plot_widget.setBackground(bg_color)
        self.plot_widget.setTitle("Income vs Expenses", color=text_color)
        self.plot_widget.setLabel('left', 'Amount (£)', color=text_color)
        self.plot_widget.setLabel('bottom', 'Month', color=text_color)
        self.plot_widget.getAxis('left').setPen(border_color)
        self.plot_widget.getAxis('bottom').setPen(border_color)
        self.plot_widget.getAxis('left').setTextPen(text_color)
        self.plot_widget.getAxis('bottom').setTextPen(text_color)
        self._update_legend_colors()

        # Redraw data with new theme colors
        if self._last_transactions is not None:
            self.update_data(self._last_transactions, self._last_start_date, self._last_end_date)

    def update_data(
        self,
        transactions: list[Transaction],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> None:
        """Update chart with transaction data.

        Args:
            transactions: List of transactions
            start_date: Start of date range (defaults to 6 months ago)
            end_date: End of date range (defaults to today)
        """
        # Store data for redraw on theme change
        self._last_transactions = transactions
        self._last_start_date = start_date
        self._last_end_date = end_date

        self.plot_widget.clear()

        if not transactions:
            return

        # Default to last 6 months if no dates provided
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date.replace(day=1) - timedelta(days=150)  # ~5 months back

        # Filter to approved transactions within date range
        valid = [
            t for t in transactions
            if t.status not in (ApprovalStatus.PLANNED, ApprovalStatus.REJECTED)
            and start_date <= t.date <= end_date
        ]

        if not valid:
            return

        # Build list of months in the range
        month_labels = []
        income_data = []
        expense_data = []

        # Start from the first day of start_date's month
        current_month = start_date.replace(day=1)
        end_month = end_date.replace(day=1)

        while current_month <= end_month:
            month_start = current_month

            # Get last day of this month
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)

            # Filter transactions for this month
            month_trans = [
                t for t in valid
                if month_start <= t.date <= month_end
            ]

            # Calculate totals
            income = sum(
                float(t.amount) for t in month_trans
                if t.type == TransactionType.INCOME
            )
            expense = sum(
                float(t.amount) for t in month_trans
                if t.type == TransactionType.EXPENSE
            )

            # Use "Mon 'YY" format if spanning multiple years, otherwise just "Mon"
            if start_date.year != end_date.year:
                month_labels.append(month_start.strftime("%b '%y"))
            else:
                month_labels.append(month_start.strftime('%b'))
            income_data.append(income)
            expense_data.append(expense)

            # Move to next month
            if current_month.month == 12:
                current_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                current_month = current_month.replace(month=current_month.month + 1)

        # Create grouped bar chart using brand chart colors
        theme = get_theme_engine()
        chart_income = theme.get_color('chart_income')
        chart_expense = theme.get_color('chart_expense')

        x = list(range(len(month_labels)))
        width = self._bar_width
        self._month_labels = month_labels
        self._income_data = income_data
        self._expense_data = expense_data

        # Income bars (gold)
        income_bars = pg.BarGraphItem(
            x=[i - width/2 for i in x],
            height=income_data,
            width=width,
            brush=chart_income,
        )
        self.plot_widget.addItem(income_bars)

        # Expense bars (dark blue)
        expense_bars = pg.BarGraphItem(
            x=[i + width/2 for i in x],
            height=expense_data,
            width=width,
            brush=chart_expense,
        )
        self.plot_widget.addItem(expense_bars)

        # Set x-axis labels
        ax = self.plot_widget.getAxis('bottom')
        ax.setTicks([[(i, label) for i, label in enumerate(month_labels)]])

    def _on_mouse_moved(self, event) -> None:
        """Show month and series value on hover."""
        if not self._month_labels:
            self.plot_widget.setToolTip("")
            return

        pos = event[0]
        vb = self.plot_widget.getPlotItem().vb
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        idx = int(round(x))

        if idx < 0 or idx >= len(self._month_labels):
            self.plot_widget.setToolTip("")
            return

        center_income = idx - self._bar_width / 2
        center_expense = idx + self._bar_width / 2
        dist_income = abs(x - center_income)
        dist_expense = abs(x - center_expense)

        month = self._month_labels[idx]
        if dist_income <= self._bar_width / 2:
            self.plot_widget.setToolTip(
                f"{month} Income\n£{self._income_data[idx]:,.2f}"
            )
            return

        if dist_expense <= self._bar_width / 2:
            self.plot_widget.setToolTip(
                f"{month} Expenses\n£{self._expense_data[idx]:,.2f}"
            )
            return

        self.plot_widget.setToolTip(
            f"{month}\nIncome: £{self._income_data[idx]:,.2f}\nExpenses: £{self._expense_data[idx]:,.2f}"
        )


class ChartWidget(QWidget):
    """Container widget that can display different chart types."""

    def __init__(self, parent=None):
        """Initialize chart container.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._current_chart = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

    def set_chart(self, chart_type: str, **kwargs) -> None:
        """Set the displayed chart type.

        Args:
            chart_type: Type of chart ('balance_trend', 'expenses_by_category', 'income_by_category', 'income_vs_expense')
            **kwargs: Arguments to pass to chart update_data method
        """
        # Remove current chart
        if self._current_chart:
            self.layout.removeWidget(self._current_chart)
            self._current_chart.deleteLater()
            self._current_chart = None

        # Create new chart
        if chart_type == 'balance_trend':
            self._current_chart = BalanceTrendChart()
        elif chart_type == 'expenses_by_category':
            self._current_chart = ExpensesByCategoryChart()
        elif chart_type == 'income_by_category':
            self._current_chart = IncomeByCategoryChart()
        elif chart_type == 'income_vs_expense':
            self._current_chart = IncomeVsExpenseChart()
        else:
            return

        self.layout.addWidget(self._current_chart)

        # Update data if provided
        if kwargs:
            self._current_chart.update_data(**kwargs)

    def update_data(self, **kwargs) -> None:
        """Update current chart data.

        Args:
            **kwargs: Arguments to pass to chart update_data method
        """
        if self._current_chart:
            self._current_chart.update_data(**kwargs)

    def refresh_theme(self) -> None:
        """Refresh chart colors based on current theme."""
        if self._current_chart and hasattr(self._current_chart, 'refresh_theme'):
            self._current_chart.refresh_theme()
