"""Tests for ForecastService."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from fidra.domain.models import (
    PlannedTemplate,
    TransactionType,
    ApprovalStatus,
    Frequency,
)
from fidra.services.forecast import ForecastService


@pytest.fixture
def service():
    """Create a ForecastService instance."""
    return ForecastService()


@pytest.fixture
def make_template():
    """Factory for creating planned templates."""
    def _make(
        start_date=None,
        frequency=Frequency.ONCE,
        end_date=None,
        occurrence_count=None,
        skipped_dates=None,
        **kwargs
    ):
        start_date = start_date or date.today()
        return PlannedTemplate.create(
            start_date=start_date,
            description=kwargs.get("description", "Test Template"),
            amount=kwargs.get("amount", Decimal("100.00")),
            type=kwargs.get("type", TransactionType.EXPENSE),
            target_sheet=kwargs.get("target_sheet", "Main"),
            frequency=frequency,
            end_date=end_date,
            occurrence_count=occurrence_count,
            skipped_dates=skipped_dates or [],
            category=kwargs.get("category"),
            party=kwargs.get("party"),
        )
    return _make


class TestExpandTemplate:
    """Test template expansion."""

    def test_expand_once_template(self, service, make_template):
        """One-time template expands to single instance."""
        today = date.today()
        template = make_template(
            start_date=today,
            frequency=Frequency.ONCE,
        )
        horizon = today + timedelta(days=365)

        instances = service.expand_template(template, horizon)

        assert len(instances) == 1
        assert instances[0].date == today
        assert instances[0].description == "Test Template"
        assert instances[0].amount == Decimal("100.00")
        assert instances[0].status == ApprovalStatus.PLANNED

    def test_expand_weekly_template(self, service, make_template):
        """Weekly template generates instances every 7 days."""
        template = make_template(
            start_date=date(2024, 1, 1),
            frequency=Frequency.WEEKLY,
        )
        horizon = date(2024, 1, 31)

        instances = service.expand_template(template, horizon, include_past=True)

        # January 2024: 1st, 8th, 15th, 22nd, 29th = 5 instances
        assert len(instances) == 5
        assert instances[0].date == date(2024, 1, 1)
        assert instances[1].date == date(2024, 1, 8)
        assert instances[4].date == date(2024, 1, 29)

    def test_expand_biweekly_template(self, service, make_template):
        """Biweekly template generates instances every 14 days."""
        template = make_template(
            start_date=date(2024, 1, 1),
            frequency=Frequency.BIWEEKLY,
        )
        horizon = date(2024, 2, 29)

        instances = service.expand_template(template, horizon, include_past=True)

        # Jan 1, Jan 15, Jan 29, Feb 12, Feb 26 = 5 instances
        assert len(instances) == 5
        assert instances[0].date == date(2024, 1, 1)
        assert instances[1].date == date(2024, 1, 15)
        assert instances[4].date == date(2024, 2, 26)

    def test_expand_monthly_template(self, service, make_template):
        """Monthly template generates instances on same day each month."""
        template = make_template(
            start_date=date(2024, 1, 15),
            frequency=Frequency.MONTHLY,
        )
        horizon = date(2024, 6, 30)

        instances = service.expand_template(template, horizon, include_past=True)

        # Jan 15, Feb 15, Mar 15, Apr 15, May 15, Jun 15 = 6 instances
        assert len(instances) == 6
        assert instances[0].date == date(2024, 1, 15)
        assert instances[1].date == date(2024, 2, 15)
        assert instances[5].date == date(2024, 6, 15)

    def test_expand_quarterly_template(self, service, make_template):
        """Quarterly template generates instances every 3 months."""
        template = make_template(
            start_date=date(2024, 1, 1),
            frequency=Frequency.QUARTERLY,
        )
        horizon = date(2024, 12, 31)

        instances = service.expand_template(template, horizon, include_past=True)

        # Jan 1, Apr 1, Jul 1, Oct 1 = 4 instances
        assert len(instances) == 4
        assert instances[0].date == date(2024, 1, 1)
        assert instances[1].date == date(2024, 4, 1)
        assert instances[3].date == date(2024, 10, 1)

    def test_expand_yearly_template(self, service, make_template):
        """Yearly template generates instances every 12 months."""
        template = make_template(
            start_date=date(2024, 1, 15),
            frequency=Frequency.YEARLY,
        )
        horizon = date(2027, 12, 31)

        instances = service.expand_template(template, horizon, include_past=True)

        # 2024, 2025, 2026, 2027 = 4 instances
        assert len(instances) == 4
        assert instances[0].date == date(2024, 1, 15)
        assert instances[1].date == date(2025, 1, 15)
        assert instances[3].date == date(2027, 1, 15)

    def test_expand_with_end_date(self, service, make_template):
        """Template stops at end_date."""
        template = make_template(
            start_date=date(2024, 1, 1),
            frequency=Frequency.WEEKLY,
            end_date=date(2024, 1, 15),
        )
        horizon = date(2024, 12, 31)

        instances = service.expand_template(template, horizon, include_past=True)

        # Jan 1, Jan 8, Jan 15 = 3 instances (stops at end_date)
        assert len(instances) == 3
        assert instances[-1].date <= date(2024, 1, 15)

    def test_expand_with_occurrence_count(self, service, make_template):
        """Template stops after occurrence_count."""
        template = make_template(
            start_date=date(2024, 1, 1),
            frequency=Frequency.MONTHLY,
            occurrence_count=3,
        )
        horizon = date(2024, 12, 31)

        instances = service.expand_template(template, horizon, include_past=True)

        # Exactly 3 instances
        assert len(instances) == 3
        assert instances[0].date == date(2024, 1, 1)
        assert instances[1].date == date(2024, 2, 1)
        assert instances[2].date == date(2024, 3, 1)

    def test_expand_skips_skipped_dates(self, service, make_template):
        """Skipped dates are excluded from instances."""
        template = make_template(
            start_date=date(2024, 1, 1),
            frequency=Frequency.WEEKLY,
            skipped_dates=[date(2024, 1, 8), date(2024, 1, 22)],
        )
        horizon = date(2024, 1, 31)

        instances = service.expand_template(template, horizon, include_past=True)

        # Jan 1, (skip 8), Jan 15, (skip 22), Jan 29 = 3 instances
        assert len(instances) == 3
        dates = [inst.date for inst in instances]
        assert date(2024, 1, 8) not in dates
        assert date(2024, 1, 22) not in dates
        assert date(2024, 1, 1) in dates
        assert date(2024, 1, 15) in dates
        assert date(2024, 1, 29) in dates

    def test_expand_excludes_past_dates_by_default(self, service, make_template):
        """Past dates are excluded unless include_past=True."""
        template = make_template(
            start_date=date(2020, 1, 1),
            frequency=Frequency.YEARLY,
        )
        horizon = date.today() + timedelta(days=365)

        instances = service.expand_template(template, horizon, include_past=False)

        # All instances should be today or later
        for inst in instances:
            assert inst.date >= date.today()

    def test_expand_includes_past_dates_when_requested(self, service, make_template):
        """Past dates included when include_past=True."""
        template = make_template(
            start_date=date(2023, 1, 1),
            frequency=Frequency.YEARLY,
        )
        horizon = date.today() + timedelta(days=365)

        instances = service.expand_template(template, horizon, include_past=True)

        # Should include past years
        dates = [inst.date for inst in instances]
        assert date(2023, 1, 1) in dates

    def test_expand_deterministic_ids(self, service, make_template):
        """Same template + date produces same instance ID."""
        today = date.today()
        template = make_template(
            start_date=today,
            frequency=Frequency.ONCE,
        )
        horizon = today + timedelta(days=365)

        instances1 = service.expand_template(template, horizon)
        instances2 = service.expand_template(template, horizon)

        # Same template, same date = same ID
        assert len(instances1) == 1
        assert len(instances2) == 1
        assert instances1[0].id == instances2[0].id


class TestProjectBalance:
    """Test balance projection."""

    def test_project_balance_empty_instances(self, service):
        """Project with no planned instances returns current balance."""
        current = Decimal("1000.00")
        projected = service.project_balance(current, [], date(2024, 12, 31))

        assert projected == Decimal("1000.00")

    def test_project_balance_includes_income(self, service, make_template):
        """Projected balance includes planned income."""
        current = Decimal("1000.00")

        template = make_template(
            start_date=date(2024, 1, 15),
            type=TransactionType.INCOME,
            amount=Decimal("2000.00"),
            frequency=Frequency.MONTHLY,
        )
        instances = service.expand_template(template, date(2024, 6, 30), include_past=True)

        projected = service.project_balance(current, instances, date(2024, 6, 30))

        # 1000 + (2000 * 6 months) = 13000
        assert projected == Decimal("13000.00")

    def test_project_balance_subtracts_expenses(self, service, make_template):
        """Projected balance subtracts planned expenses."""
        current = Decimal("5000.00")

        template = make_template(
            start_date=date(2024, 1, 1),
            type=TransactionType.EXPENSE,
            amount=Decimal("500.00"),
            frequency=Frequency.MONTHLY,
        )
        instances = service.expand_template(template, date(2024, 12, 31), include_past=True)

        projected = service.project_balance(current, instances, date(2024, 12, 31))

        # 5000 - (500 * 12 months) = -1000
        assert projected == Decimal("-1000.00")

    def test_project_balance_only_up_to_target_date(self, service, make_template):
        """Only instances up to target_date affect projection."""
        current = Decimal("1000.00")

        template = make_template(
            start_date=date(2024, 1, 1),
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            frequency=Frequency.MONTHLY,
        )
        instances = service.expand_template(template, date(2024, 12, 31), include_past=True)

        # Project only up to June
        projected = service.project_balance(current, instances, date(2024, 6, 30))

        # 1000 - (100 * 6 months) = 400
        assert projected == Decimal("400.00")
