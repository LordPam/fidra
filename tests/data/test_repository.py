"""Integration tests for SQLite repositories."""

import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fidra.data.factory import create_repositories
from fidra.data.repository import ConcurrencyError
from fidra.domain.models import (
    Transaction,
    TransactionType,
    ApprovalStatus,
    PlannedTemplate,
    Frequency,
    Sheet,
)


@pytest.fixture
async def repos(tmp_path):
    """Create repositories with temporary database."""
    db_path = tmp_path / "test.db"
    trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo, category_repo, sync_queue = (
        await create_repositories("sqlite", db_path)
    )
    yield trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo
    await trans_repo.close()


class TestTransactionRepository:
    """Tests for TransactionRepository (SQLite implementation)."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, repos):
        """Save a transaction and retrieve it."""
        trans_repo, *_ = repos

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Test Transaction",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        saved = await trans_repo.save(trans)
        assert saved.id == trans.id

        retrieved = await trans_repo.get_by_id(trans.id)
        assert retrieved is not None
        assert retrieved.description == "Test Transaction"
        assert retrieved.amount == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_get_all_transactions(self, repos):
        """Retrieve all transactions."""
        trans_repo, *_ = repos

        # Create 3 transactions
        for i in range(3):
            trans = Transaction.create(
                date=date(2024, 1, i + 1),
                description=f"Transaction {i+1}",
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                sheet="Main",
            )
            await trans_repo.save(trans)

        all_trans = await trans_repo.get_all()
        assert len(all_trans) == 3
        # Should be sorted by date DESC
        assert all_trans[0].description == "Transaction 3"

    @pytest.mark.asyncio
    async def test_get_all_filtered_by_sheet(self, repos):
        """Filter transactions by sheet."""
        trans_repo, *_ = repos

        # Create transactions in different sheets
        trans1 = Transaction.create(
            date=date(2024, 1, 1),
            description="Main Transaction",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )
        trans2 = Transaction.create(
            date=date(2024, 1, 2),
            description="Other Transaction",
            amount=Decimal("200.00"),
            type=TransactionType.EXPENSE,
            sheet="Other",
        )

        await trans_repo.save(trans1)
        await trans_repo.save(trans2)

        main_trans = await trans_repo.get_all(sheet="Main")
        assert len(main_trans) == 1
        assert main_trans[0].description == "Main Transaction"

    @pytest.mark.asyncio
    async def test_update_transaction(self, repos):
        """Update an existing transaction."""
        trans_repo, *_ = repos

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Original",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        await trans_repo.save(trans)

        # Update
        updated = trans.with_updates(description="Updated", amount=Decimal("200.00"))
        await trans_repo.save(updated)

        retrieved = await trans_repo.get_by_id(trans.id)
        assert retrieved.description == "Updated"
        assert retrieved.amount == Decimal("200.00")
        assert retrieved.version == 2

    @pytest.mark.asyncio
    async def test_delete_transaction(self, repos):
        """Delete a transaction."""
        trans_repo, *_ = repos

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="To Delete",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        await trans_repo.save(trans)
        deleted = await trans_repo.delete(trans.id)
        assert deleted is True

        retrieved = await trans_repo.get_by_id(trans.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_concurrency_error(self, repos):
        """Version conflict raises ConcurrencyError."""
        trans_repo, *_ = repos

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Original",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        await trans_repo.save(trans)

        # Simulate concurrent edit
        trans2 = trans.with_updates(description="Update 1")
        trans3 = trans.with_updates(description="Update 2")

        # First update succeeds
        await trans_repo.save(trans2)

        # Second update should fail (stale version)
        with pytest.raises(ConcurrencyError):
            await trans_repo.save(trans3)

    @pytest.mark.asyncio
    async def test_bulk_operations(self, repos):
        """Bulk save and delete operations."""
        trans_repo, *_ = repos

        transactions = [
            Transaction.create(
                date=date(2024, 1, i + 1),
                description=f"Trans {i+1}",
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                sheet="Main",
            )
            for i in range(3)
        ]

        # Bulk save
        saved = await trans_repo.bulk_save(transactions)
        assert len(saved) == 3

        all_trans = await trans_repo.get_all()
        assert len(all_trans) == 3

        # Bulk delete
        ids = [t.id for t in transactions]
        deleted_count = await trans_repo.bulk_delete(ids)
        assert deleted_count == 3

        all_trans = await trans_repo.get_all()
        assert len(all_trans) == 0


class TestPlannedRepository:
    """Tests for PlannedRepository."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_template(self, repos):
        """Save and retrieve a planned template."""
        _, planned_repo, *_ = repos

        template = PlannedTemplate.create(
            start_date=date(2024, 1, 1),
            description="Monthly Rent",
            amount=Decimal("800.00"),
            type=TransactionType.EXPENSE,
            target_sheet="Main",
            frequency=Frequency.MONTHLY,
        )

        await planned_repo.save(template)

        retrieved = await planned_repo.get_by_id(template.id)
        assert retrieved is not None
        assert retrieved.description == "Monthly Rent"
        assert retrieved.frequency == Frequency.MONTHLY

    @pytest.mark.asyncio
    async def test_save_template_with_skipped_dates(self, repos):
        """Save template with skipped dates."""
        _, planned_repo, *_ = repos

        template = PlannedTemplate.create(
            start_date=date(2024, 1, 1),
            description="Rent",
            amount=Decimal("800.00"),
            type=TransactionType.EXPENSE,
            target_sheet="Main",
            frequency=Frequency.MONTHLY,
        )

        # Skip an instance
        skipped = template.skip_instance(date(2024, 2, 1))
        await planned_repo.save(skipped)

        retrieved = await planned_repo.get_by_id(template.id)
        assert date(2024, 2, 1) in retrieved.skipped_dates
        assert retrieved.is_skipped(date(2024, 2, 1))


class TestSheetRepository:
    """Tests for SheetRepository."""

    @pytest.mark.asyncio
    async def test_create_and_retrieve_sheet(self, repos):
        """Create and retrieve a sheet."""
        _, _, sheet_repo, *_ = repos

        sheet = await sheet_repo.create("Main Transactions")

        retrieved = await sheet_repo.get_by_id(sheet.id)
        assert retrieved is not None
        assert retrieved.name == "Main Transactions"

    @pytest.mark.asyncio
    async def test_get_sheet_by_name(self, repos):
        """Retrieve sheet by name."""
        _, _, sheet_repo, *_ = repos

        await sheet_repo.create("Test Sheet")

        retrieved = await sheet_repo.get_by_name("Test Sheet")
        assert retrieved is not None
        assert retrieved.name == "Test Sheet"

    @pytest.mark.asyncio
    async def test_get_all_sheets(self, repos):
        """Retrieve all sheets."""
        _, _, sheet_repo, *_ = repos

        await sheet_repo.create("Sheet A")
        await sheet_repo.create("Sheet B")

        all_sheets = await sheet_repo.get_all()
        assert len(all_sheets) == 2
        # Should be sorted by name
        assert all_sheets[0].name == "Sheet A"
        assert all_sheets[1].name == "Sheet B"
