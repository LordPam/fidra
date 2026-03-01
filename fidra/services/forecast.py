"""Forecast service for expanding planned templates into transaction instances."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid5, NAMESPACE_OID

from dateutil.relativedelta import relativedelta

from fidra.domain.models import (
    Transaction,
    PlannedTemplate,
    TransactionType,
    ApprovalStatus,
    Frequency,
)


class ForecastService:
    """Expands planned templates and projects future balances.

    This service generates transaction instances from planned templates
    based on frequency rules, and can project future balance with those instances.
    """

    def expand_template(
        self,
        template: PlannedTemplate,
        horizon: date,
        include_past: bool = False,
    ) -> list[Transaction]:
        """Generate transaction instances from a template.

        Args:
            template: The planned template to expand
            horizon: Generate instances up to this date
            include_past: If False, skip dates before today

        Returns:
            List of transaction instances with PLANNED status

        Example:
            >>> template = PlannedTemplate.create(...)
            >>> service = ForecastService()
            >>> instances = service.expand_template(template, date(2024, 12, 31))
        """
        instances = []
        current = template.start_date
        today = date.today()
        count = 0

        while current <= horizon:
            # Skip past dates unless include_past is True
            if current >= today or include_past:
                # Skip if this date is in the skipped_dates or fulfilled_dates list
                if current not in template.skipped_dates and current not in template.fulfilled_dates:
                    instances.append(self._create_instance(template, current))

            # Check occurrence limit
            count += 1
            if template.occurrence_count and count >= template.occurrence_count:
                break

            # Check end date
            if template.end_date and current >= template.end_date:
                break

            # Advance to next occurrence
            current = self._next_occurrence(current, template.frequency)

            # If frequency is ONCE, we're done
            if template.frequency == Frequency.ONCE:
                break

        return instances

    def _next_occurrence(self, current: date, frequency: Frequency) -> date:
        """Calculate next occurrence date based on frequency.

        Args:
            current: Current occurrence date
            frequency: Frequency enum value

        Returns:
            Next occurrence date

        Example:
            >>> service = ForecastService()
            >>> next_date = service._next_occurrence(date(2024, 1, 15), Frequency.MONTHLY)
            >>> # Returns date(2024, 2, 15)
        """
        if frequency == Frequency.ONCE:
            return date.max  # No more occurrences
        elif frequency == Frequency.WEEKLY:
            return current + timedelta(weeks=1)
        elif frequency == Frequency.BIWEEKLY:
            return current + timedelta(weeks=2)
        elif frequency == Frequency.MONTHLY:
            return current + relativedelta(months=1)
        elif frequency == Frequency.QUARTERLY:
            return current + relativedelta(months=3)
        elif frequency == Frequency.YEARLY:
            return current + relativedelta(years=1)
        else:
            raise ValueError(f"Unknown frequency: {frequency}")

    def _create_instance(
        self,
        template: PlannedTemplate,
        occurrence_date: date,
    ) -> Transaction:
        """Create a transaction instance from template.

        The instance has a deterministic ID based on template ID + date,
        so the same template + date always produces the same instance ID.

        Args:
            template: Source planned template
            occurrence_date: Date for this instance

        Returns:
            Transaction with PLANNED status
        """
        # Deterministic ID based on template + date
        instance_id = uuid5(
            NAMESPACE_OID,
            f"{template.id}_{occurrence_date.isoformat()}"
        )

        return Transaction(
            id=instance_id,
            date=occurrence_date,
            description=template.description,
            amount=template.amount,
            type=template.type,
            status=ApprovalStatus.PLANNED,
            sheet=template.target_sheet,
            category=template.category,
            party=template.party,
            activity=template.activity,
            notes=None,  # Instances don't inherit notes from template
            is_one_time_planned=template.frequency == Frequency.ONCE,
            version=1,
        )

    def project_balance(
        self,
        current_balance: Decimal,
        planned_instances: list[Transaction],
        target_date: date,
    ) -> Decimal:
        """Project balance at a future date including planned transactions.

        Args:
            current_balance: Starting balance (from actuals only)
            planned_instances: List of planned transaction instances
            target_date: Project balance up to this date

        Returns:
            Projected balance at target_date

        Example:
            >>> current = Decimal("1000.00")
            >>> instances = service.expand_template(template, date(2024, 12, 31))
            >>> projected = service.project_balance(current, instances, date(2024, 6, 30))
        """
        balance = current_balance

        for t in planned_instances:
            if t.date <= target_date:
                if t.type == TransactionType.INCOME:
                    balance += t.amount
                else:
                    balance -= t.amount

        return balance
