"""Tests for CachingRepository wrappers - local cache + sync queue integration."""

import pytest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fidra.data.sqlite_repo import (
    SQLiteTransactionRepository,
    SQLitePlannedRepository,
    SQLiteSheetRepository,
    SQLiteCategoryRepository,
)
from fidra.data.caching_repository import (
    CachingTransactionRepository,
    CachingPlannedRepository,
    CachingSheetRepository,
    CachingCategoryRepository,
)
from fidra.data.sync_queue import SyncQueue
from fidra.domain.models import (
    Transaction,
    TransactionType,
    ApprovalStatus,
    PlannedTemplate,
    Frequency,
    Sheet,
)


@pytest.fixture
async def local_repos(tmp_path):
    """Create local SQLite repos sharing a single connection."""
    db_path = tmp_path / "cache.db"
    trans = SQLiteTransactionRepository(db_path)
    await trans.connect()
    planned = SQLitePlannedRepository(trans._conn)
    sheet = SQLiteSheetRepository(trans._conn)
    cat = SQLiteCategoryRepository(db_path)
    cat.set_connection(trans._conn)
    yield trans, planned, sheet, cat
    await trans.close()


@pytest.fixture
async def sync_queue(tmp_path):
    """Create a SyncQueue."""
    q = SyncQueue(tmp_path / "queue.db")
    await q.initialize()
    yield q
    await q.close()


def _make_transaction(**kwargs) -> Transaction:
    defaults = dict(
        date=date.today(),
        description="Test",
        amount=Decimal("100.00"),
        type=TransactionType.EXPENSE,
        sheet="Main",
    )
    defaults.update(kwargs)
    return Transaction.create(**defaults)


def _make_sheet(name="Main") -> Sheet:
    return Sheet.create(name=name)


def _make_planned(**kwargs) -> PlannedTemplate:
    defaults = dict(
        start_date=date.today(),
        description="Planned test",
        amount=Decimal("50.00"),
        type=TransactionType.EXPENSE,
        target_sheet="Main",
        frequency=Frequency.MONTHLY,
    )
    defaults.update(kwargs)
    return PlannedTemplate.create(**defaults)


class TestCachingTransactionRepository:
    """Test transaction caching: reads from local, writes queue for sync."""

    @pytest.mark.asyncio
    async def test_save_writes_to_local(self, local_repos, sync_queue):
        local_trans, *_ = local_repos
        repo = CachingTransactionRepository(
            cloud_repo=None, local_repo=local_trans, sync_queue=sync_queue,
        )

        trans = _make_transaction()
        saved = await repo.save(trans)
        assert saved.id == trans.id

        # Should be readable from local
        retrieved = await repo.get_by_id(trans.id)
        assert retrieved is not None
        assert retrieved.description == "Test"

    @pytest.mark.asyncio
    async def test_save_enqueues_to_sync_queue(self, local_repos, sync_queue):
        local_trans, *_ = local_repos
        repo = CachingTransactionRepository(
            cloud_repo=None, local_repo=local_trans, sync_queue=sync_queue,
        )

        trans = _make_transaction()
        await repo.save(trans)

        pending = await sync_queue.get_pending()
        assert len(pending) == 1
        assert pending[0].entity_type == "transaction"

    @pytest.mark.asyncio
    async def test_save_without_sync_queue(self, local_repos):
        """Save should work even without a sync queue (offline-only mode)."""
        local_trans, *_ = local_repos
        repo = CachingTransactionRepository(
            cloud_repo=None, local_repo=local_trans, sync_queue=None,
        )

        trans = _make_transaction()
        saved = await repo.save(trans)
        assert saved.id == trans.id

    @pytest.mark.asyncio
    async def test_delete_removes_from_local(self, local_repos, sync_queue):
        local_trans, *_ = local_repos
        repo = CachingTransactionRepository(
            cloud_repo=None, local_repo=local_trans, sync_queue=sync_queue,
        )

        trans = _make_transaction()
        await repo.save(trans)
        await repo.delete(trans.id)

        # Should be gone from local
        assert await repo.get_by_id(trans.id) is None

        # Entity was only created locally (never synced), so no cloud delete needed
        pending = await sync_queue.get_pending()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_delete_synced_entity_enqueues_delete(self, local_repos, sync_queue):
        """Deleting an entity that was already synced should queue a cloud delete."""
        local_trans, *_ = local_repos
        repo = CachingTransactionRepository(
            cloud_repo=None, local_repo=local_trans, sync_queue=sync_queue,
        )

        trans = _make_transaction()
        await repo.save(trans)
        # Simulate: the create was already synced (clear queue)
        await sync_queue.clear_all()

        await repo.delete(trans.id)

        pending = await sync_queue.get_pending()
        assert len(pending) == 1
        assert pending[0].operation.value == "delete"

    @pytest.mark.asyncio
    async def test_get_all_reads_from_local(self, local_repos, sync_queue):
        local_trans, *_ = local_repos
        repo = CachingTransactionRepository(
            cloud_repo=None, local_repo=local_trans, sync_queue=sync_queue,
        )

        for i in range(3):
            await repo.save(_make_transaction(description=f"T{i}"))

        all_trans = await repo.get_all()
        assert len(all_trans) == 3

    @pytest.mark.asyncio
    async def test_bulk_save_enqueues_all(self, local_repos, sync_queue):
        local_trans, *_ = local_repos
        repo = CachingTransactionRepository(
            cloud_repo=None, local_repo=local_trans, sync_queue=sync_queue,
        )

        transactions = [_make_transaction(description=f"T{i}") for i in range(3)]
        await repo.bulk_save(transactions)

        pending = await sync_queue.get_pending()
        assert len(pending) == 3

    @pytest.mark.asyncio
    async def test_bulk_delete_local_only_no_queue(self, local_repos, sync_queue):
        """Bulk delete of never-synced entities produces no queue entries."""
        local_trans, *_ = local_repos
        repo = CachingTransactionRepository(
            cloud_repo=None, local_repo=local_trans, sync_queue=sync_queue,
        )

        transactions = [_make_transaction(description=f"T{i}") for i in range(3)]
        await repo.bulk_save(transactions)
        ids = [t.id for t in transactions]
        await repo.bulk_delete(ids)

        pending = await sync_queue.get_pending()
        deletes = [p for p in pending if p.operation.value == "delete"]
        assert len(deletes) == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_synced_entities_enqueues(self, local_repos, sync_queue):
        """Bulk delete of already-synced entities queues cloud deletes."""
        local_trans, *_ = local_repos
        repo = CachingTransactionRepository(
            cloud_repo=None, local_repo=local_trans, sync_queue=sync_queue,
        )

        transactions = [_make_transaction(description=f"T{i}") for i in range(3)]
        await repo.bulk_save(transactions)
        # Simulate: all creates were synced
        await sync_queue.clear_all()

        ids = [t.id for t in transactions]
        await repo.bulk_delete(ids)

        pending = await sync_queue.get_pending()
        deletes = [p for p in pending if p.operation.value == "delete"]
        assert len(deletes) == 3


class TestCachingSheetRepository:

    @pytest.mark.asyncio
    async def test_create_and_get_all(self, local_repos, sync_queue):
        _, _, local_sheet, _ = local_repos
        repo = CachingSheetRepository(
            cloud_repo=None, local_repo=local_sheet, sync_queue=sync_queue,
        )

        sheet = _make_sheet("Q1 2024")
        await repo.save(sheet)

        sheets = await repo.get_all()
        assert len(sheets) == 1
        assert sheets[0].name == "Q1 2024"

    @pytest.mark.asyncio
    async def test_save_enqueues(self, local_repos, sync_queue):
        _, _, local_sheet, _ = local_repos
        repo = CachingSheetRepository(
            cloud_repo=None, local_repo=local_sheet, sync_queue=sync_queue,
        )

        await repo.save(_make_sheet("Test"))
        pending = await sync_queue.get_pending()
        assert len(pending) == 1
        assert pending[0].entity_type == "sheet"


class TestCachingPlannedRepository:

    @pytest.mark.asyncio
    async def test_save_and_retrieve(self, local_repos, sync_queue):
        _, local_planned, _, _ = local_repos
        repo = CachingPlannedRepository(
            cloud_repo=None, local_repo=local_planned, sync_queue=sync_queue,
        )

        template = _make_planned()
        await repo.save(template)

        result = await repo.get_by_id(template.id)
        assert result is not None
        assert result.description == "Planned test"

    @pytest.mark.asyncio
    async def test_delete_synced_enqueues(self, local_repos, sync_queue):
        _, local_planned, _, _ = local_repos
        repo = CachingPlannedRepository(
            cloud_repo=None, local_repo=local_planned, sync_queue=sync_queue,
        )

        template = _make_planned()
        await repo.save(template)
        # Simulate: the create was synced
        await sync_queue.clear_all()

        await repo.delete(template.id)

        pending = await sync_queue.get_pending()
        assert len(pending) == 1
        assert pending[0].operation.value == "delete"


class TestCachingCategoryRepository:

    @pytest.mark.asyncio
    async def test_add_and_get_all(self, local_repos, sync_queue):
        _, _, _, local_cat = local_repos
        repo = CachingCategoryRepository(
            cloud_repo=None, local_repo=local_cat, sync_queue=sync_queue,
        )

        await repo.add("expense", "Fuel")
        await repo.add("expense", "Food")

        cats = await repo.get_all("expense")
        assert set(cats) == {"Fuel", "Food"}

    @pytest.mark.asyncio
    async def test_add_enqueues_category_add(self, local_repos, sync_queue):
        _, _, _, local_cat = local_repos
        repo = CachingCategoryRepository(
            cloud_repo=None, local_repo=local_cat, sync_queue=sync_queue,
        )

        await repo.add("expense", "Fuel")

        pending = await sync_queue.get_pending()
        assert len(pending) == 1
        assert pending[0].entity_type == "category"

    @pytest.mark.asyncio
    async def test_remove_enqueues_category_remove(self, local_repos, sync_queue):
        _, _, _, local_cat = local_repos
        repo = CachingCategoryRepository(
            cloud_repo=None, local_repo=local_cat, sync_queue=sync_queue,
        )

        await repo.add("expense", "Fuel")
        # Clear queue from the add
        await sync_queue.clear_all()

        await repo.remove("expense", "Fuel")

        pending = await sync_queue.get_pending()
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_set_all_enqueues_reorder(self, local_repos, sync_queue):
        _, _, _, local_cat = local_repos
        repo = CachingCategoryRepository(
            cloud_repo=None, local_repo=local_cat, sync_queue=sync_queue,
        )

        await repo.set_all("expense", ["C", "B", "A"])

        cats = await repo.get_all("expense")
        assert cats == ["C", "B", "A"]

        pending = await sync_queue.get_pending()
        assert len(pending) == 1
