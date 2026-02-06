"""Financial year service.

Calculates financial year periods and filters transactions by financial year.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from fidra.domain.models import Transaction


@dataclass(frozen=True)
class FinancialYearPeriod:
    """Represents a single financial year period."""

    start_date: date
    end_date: date
    label: str  # e.g., "2024/25" or "2024"

    def contains(self, d: date) -> bool:
        """Check if a date falls within this period."""
        return self.start_date <= d <= self.end_date


class FinancialYearService:
    """Service for financial year calculations.

    The financial year start month determines how years are sliced.
    For start_month=1, years are Jan-Dec (calendar year).
    For start_month=4, years are Apr-Mar (UK tax year style).
    """

    def __init__(self, start_month: int = 1):
        self._start_month = start_month

    @property
    def start_month(self) -> int:
        return self._start_month

    @start_month.setter
    def start_month(self, value: int) -> None:
        if not 1 <= value <= 12:
            raise ValueError("start_month must be 1-12")
        self._start_month = value

    def get_period_for_date(self, d: date) -> FinancialYearPeriod:
        """Get the financial year period containing a given date."""
        if self._start_month == 1:
            # Calendar year
            start = date(d.year, 1, 1)
            end = date(d.year, 12, 31)
            label = str(d.year)
        else:
            # Split year
            if d.month >= self._start_month:
                # We're in the first part of the financial year
                year_start = d.year
            else:
                # We're in the second part (after Jan)
                year_start = d.year - 1

            start = date(year_start, self._start_month, 1)

            # End is the last day of the month before start_month in the next year
            end_year = year_start + 1
            end_month = self._start_month - 1 if self._start_month > 1 else 12
            if end_month == 12:
                end = date(end_year - 1, 12, 31)
            else:
                # Last day of end_month
                if end_month in (4, 6, 9, 11):
                    end = date(end_year, end_month, 30)
                elif end_month == 2:
                    # Handle leap year
                    try:
                        end = date(end_year, 2, 29)
                    except ValueError:
                        end = date(end_year, 2, 28)
                else:
                    end = date(end_year, end_month, 31)

            short_year = str(end.year)[-2:]
            label = f"{year_start}/{short_year}"

        return FinancialYearPeriod(start_date=start, end_date=end, label=label)

    def get_current_period(self) -> FinancialYearPeriod:
        """Get the financial year period for today."""
        return self.get_period_for_date(date.today())

    def get_all_periods(
        self, transactions: list[Transaction]
    ) -> list[FinancialYearPeriod]:
        """Get all financial year periods that contain transactions.

        Returns periods sorted with most recent first.
        """
        if not transactions:
            return [self.get_current_period()]

        periods: dict[str, FinancialYearPeriod] = {}
        for t in transactions:
            period = self.get_period_for_date(t.date)
            periods[period.label] = period

        # Always include the current period
        current = self.get_current_period()
        periods[current.label] = current

        # Sort by start_date descending (most recent first)
        return sorted(periods.values(), key=lambda p: p.start_date, reverse=True)

    def filter_transactions(
        self,
        transactions: list[Transaction],
        period: Optional[FinancialYearPeriod] = None,
    ) -> list[Transaction]:
        """Filter transactions to a financial year period.

        Args:
            transactions: All transactions
            period: Period to filter by. If None, uses current period.

        Returns:
            Transactions within the period
        """
        if period is None:
            period = self.get_current_period()

        return [t for t in transactions if period.contains(t.date)]

    @staticmethod
    def month_name(month: int) -> str:
        """Get the name of a month."""
        names = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        return names[month]
