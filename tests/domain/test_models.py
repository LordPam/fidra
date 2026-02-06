"""Unit tests for domain models."""

import pytest
from datetime import date
from decimal import Decimal
from fidra.domain.models import (
    Transaction,
    TransactionType,
    ApprovalStatus,
    PlannedTemplate,
    Frequency,
    Sheet,
    Category,
)


class TestTransaction:
    """Tests for Transaction model."""

    def test_create_expense_transaction(self):
        """Expense transactions default to PENDING status."""
        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Coffee",
            amount=Decimal("4.50"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        assert trans.description == "Coffee"
        assert trans.amount == Decimal("4.50")
        assert trans.type == TransactionType.EXPENSE
        assert trans.status == ApprovalStatus.PENDING
        assert trans.version == 1

    def test_create_income_transaction(self):
        """Income transactions default to AUTO status."""
        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Salary",
            amount=Decimal("2500.00"),
            type=TransactionType.INCOME,
            sheet="Main",
        )

        assert trans.status == ApprovalStatus.AUTO

    def test_transaction_immutability(self, make_transaction):
        """Transactions are immutable - updates create new instances."""
        trans = make_transaction(amount=Decimal("100.00"))
        updated = trans.with_updates(amount=Decimal("200.00"))

        assert trans.amount == Decimal("100.00")  # Original unchanged
        assert updated.amount == Decimal("200.00")
        assert updated.version == trans.version + 1
        assert updated.id == trans.id  # Same ID

    def test_invalid_amount_raises_error(self):
        """Transaction amount must be positive."""
        with pytest.raises(ValueError, match="Amount must be positive"):
            Transaction.create(
                date=date(2024, 1, 15),
                description="Test",
                amount=Decimal("0.00"),  # Invalid: zero
                type=TransactionType.EXPENSE,
                sheet="Main",
            )

        with pytest.raises(ValueError, match="Amount must be positive"):
            Transaction.create(
                date=date(2024, 1, 15),
                description="Test",
                amount=Decimal("-50.00"),  # Invalid: negative
                type=TransactionType.EXPENSE,
                sheet="Main",
            )

    def test_empty_description_raises_error(self):
        """Transaction description cannot be empty."""
        with pytest.raises(ValueError, match="Description cannot be empty"):
            Transaction.create(
                date=date(2024, 1, 15),
                description="   ",  # Invalid: whitespace only
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                sheet="Main",
            )

    def test_empty_sheet_raises_error(self):
        """Transaction sheet cannot be empty."""
        with pytest.raises(ValueError, match="Sheet cannot be empty"):
            Transaction.create(
                date=date(2024, 1, 15),
                description="Test",
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                sheet="",  # Invalid: empty
            )

    def test_transaction_with_optional_fields(self):
        """Transactions can have optional category, party, and notes."""
        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Fuel",
            amount=Decimal("50.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
            category="Travel",
            party="Shell Station",
            notes="For diving trip",
        )

        assert trans.category == "Travel"
        assert trans.party == "Shell Station"
        assert trans.notes == "For diving trip"


class TestPlannedTemplate:
    """Tests for PlannedTemplate model."""

    def test_create_one_time_template(self):
        """One-time planned templates (frequency = ONCE)."""
        template = PlannedTemplate.create(
            start_date=date(2024, 2, 1),
            description="Equipment Purchase",
            amount=Decimal("500.00"),
            type=TransactionType.EXPENSE,
            target_sheet="Main",
            frequency=Frequency.ONCE,
        )

        assert template.frequency == Frequency.ONCE
        assert not template.is_recurring
        assert template.start_date == date(2024, 2, 1)

    def test_create_recurring_template(self):
        """Recurring planned templates."""
        template = PlannedTemplate.create(
            start_date=date(2024, 1, 1),
            description="Monthly Rent",
            amount=Decimal("800.00"),
            type=TransactionType.EXPENSE,
            target_sheet="Main",
            frequency=Frequency.MONTHLY,
            end_date=date(2024, 12, 31),
        )

        assert template.frequency == Frequency.MONTHLY
        assert template.is_recurring
        assert template.end_date == date(2024, 12, 31)

    def test_end_date_and_occurrence_count_mutually_exclusive(self):
        """Cannot specify both end_date and occurrence_count."""
        with pytest.raises(ValueError, match="Cannot specify both"):
            PlannedTemplate.create(
                start_date=date(2024, 1, 1),
                description="Test",
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                target_sheet="Main",
                frequency=Frequency.MONTHLY,
                end_date=date(2024, 12, 31),
                occurrence_count=12,  # Invalid: both specified
            )

    def test_skip_instance(self):
        """Skipping an instance adds it to skipped_dates."""
        template = PlannedTemplate.create(
            start_date=date(2024, 1, 1),
            description="Rent",
            amount=Decimal("800.00"),
            type=TransactionType.EXPENSE,
            target_sheet="Main",
            frequency=Frequency.MONTHLY,
        )

        skip_date = date(2024, 2, 1)
        updated = template.skip_instance(skip_date)

        assert skip_date in updated.skipped_dates
        assert updated.is_skipped(skip_date)
        assert template.skipped_dates == ()  # Original unchanged

    def test_unskip_instance(self):
        """Unskipping an instance removes it from skipped_dates."""
        template = PlannedTemplate.create(
            start_date=date(2024, 1, 1),
            description="Rent",
            amount=Decimal("800.00"),
            type=TransactionType.EXPENSE,
            target_sheet="Main",
            frequency=Frequency.MONTHLY,
        )

        skip_date = date(2024, 2, 1)
        skipped = template.skip_instance(skip_date)
        unskipped = skipped.unskip_instance(skip_date)

        assert skip_date not in unskipped.skipped_dates
        assert not unskipped.is_skipped(skip_date)

    def test_mark_fulfilled(self):
        """Marking an instance as fulfilled adds it to fulfilled_dates."""
        template = PlannedTemplate.create(
            start_date=date(2024, 1, 1),
            description="Rent",
            amount=Decimal("800.00"),
            type=TransactionType.EXPENSE,
            target_sheet="Main",
            frequency=Frequency.MONTHLY,
        )

        fulfill_date = date(2024, 1, 1)
        fulfilled = template.mark_fulfilled(fulfill_date)

        assert fulfill_date in fulfilled.fulfilled_dates
        assert fulfilled.is_fulfilled(fulfill_date)


class TestSheet:
    """Tests for Sheet model."""

    def test_create_sheet(self):
        """Create a basic sheet."""
        sheet = Sheet.create(name="Main Transactions")

        assert sheet.name == "Main Transactions"
        assert not sheet.is_virtual
        assert not sheet.is_planned

    def test_create_virtual_sheet(self):
        """Create a virtual sheet."""
        sheet = Sheet.create(name="All Transactions", is_virtual=True)

        assert sheet.is_virtual

    def test_empty_sheet_name_raises_error(self):
        """Sheet name cannot be empty."""
        with pytest.raises(ValueError, match="Sheet name cannot be empty"):
            Sheet.create(name="   ")


class TestCategory:
    """Tests for Category model."""

    def test_create_category(self):
        """Create a basic category."""
        category = Category.create(
            name="Equipment", type=TransactionType.EXPENSE, color="#ef4444"
        )

        assert category.name == "Equipment"
        assert category.type == TransactionType.EXPENSE
        assert category.color == "#ef4444"

    def test_invalid_color_raises_error(self):
        """Category color must be in hex format."""
        with pytest.raises(ValueError, match="Color must be in hex format"):
            Category.create(
                name="Equipment",
                type=TransactionType.EXPENSE,
                color="red",  # Invalid: not hex
            )

    def test_empty_category_name_raises_error(self):
        """Category name cannot be empty."""
        with pytest.raises(ValueError, match="Category name cannot be empty"):
            Category.create(name="", type=TransactionType.EXPENSE)
