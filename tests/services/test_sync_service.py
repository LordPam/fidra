"""Tests for SyncService - background sync with event-driven push."""

import asyncio
import json
import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fidra.data.sync_queue import SyncQueue, SyncOperation
from fidra.data.caching_repository import (
    CachingTransactionRepository,
    CachingPlannedRepository,
    CachingSheetRepository,
    CachingCategoryRepository,
)
from fidra.data.sqlite_repo import (
    SQLiteTransactionRepository,
    SQLitePlannedRepository,
    SQLiteSheetRepository,
    SQLiteCategoryRepository,
)
from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.services.sync_service import SyncService, ConflictStrategy


class FakeConnectionState:
    """Fake connection state service for testing."""

    def __init__(self, connected=True):
        self._connected = connected
        self.status_changed = MagicMock()  # Fake signal

    @property
    def is_connected(self):
        return self._connected

    @property
    def status(self):
        mock = MagicMock()
        mock.value = "connected" if self._connected else "disconnected"
        return mock

    def report_network_error(self):
        pass


@pytest.fixture
async def sync_env(tmp_path):
    """Set up a complete sync environment with local repos and queue."""
    cache_path = tmp_path / "cache.db"
    queue_path = tmp_path / "queue.db"

    # Local repos
    local_trans = SQLiteTransactionRepository(cache_path)
    await local_trans.connect()
    local_planned = SQLitePlannedRepository(local_trans._conn)
    local_sheet = SQLiteSheetRepository(local_trans._conn)
    local_cat = SQLiteCategoryRepository(cache_path)
    local_cat.set_connection(local_trans._conn)

    # Sync queue
    queue = SyncQueue(queue_path)
    await queue.initialize()

    # Mock cloud repos
    cloud_trans = AsyncMock()
    cloud_planned = AsyncMock()
    cloud_sheet = AsyncMock()
    cloud_cat = AsyncMock()

    # Caching repos
    trans_repo = CachingTransactionRepository(cloud_trans, local_trans, queue)
    planned_repo = CachingPlannedRepository(cloud_planned, local_planned, queue)
    sheet_repo = CachingSheetRepository(cloud_sheet, local_sheet, queue)
    cat_repo = CachingCategoryRepository(cloud_cat, local_cat, queue)

    conn_state = FakeConnectionState(connected=True)

    yield {
        "queue": queue,
        "trans_repo": trans_repo,
        "planned_repo": planned_repo,
        "sheet_repo": sheet_repo,
        "cat_repo": cat_repo,
        "conn_state": conn_state,
        "cloud_trans": cloud_trans,
        "cloud_planned": cloud_planned,
        "cloud_sheet": cloud_sheet,
        "cloud_cat": cloud_cat,
    }

    await queue.close()
    await local_trans.close()


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


class TestSyncServiceLifecycle:
    """Test start/stop and basic lifecycle."""

    def test_start_and_stop(self, sync_env):
        env = sync_env
        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )

        service.start()
        assert service._running is True
        assert service._sync_timer is not None
        assert env["queue"].on_change is not None

        service.stop()
        assert service._running is False
        assert service._sync_timer is None
        assert env["queue"].on_change is None

    def test_start_idempotent(self, sync_env):
        env = sync_env
        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )

        service.start()
        service.start()  # Should not raise
        service.stop()


class TestSyncNow:
    """Test the sync_now() method directly."""

    @pytest.mark.asyncio
    async def test_sync_empty_queue(self, sync_env):
        env = sync_env
        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        count = await service.sync_now()
        assert count == 0

    @pytest.mark.asyncio
    async def test_sync_transaction_create(self, sync_env):
        env = sync_env
        trans = _make_transaction(description="Sync me")

        # Save to local cache (also enqueues)
        await env["trans_repo"].save(trans)

        # Mock cloud save to return the transaction
        env["cloud_trans"].save = AsyncMock(return_value=trans)

        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        count = await service.sync_now()
        assert count == 1
        env["cloud_trans"].save.assert_called_once()

        # Queue should be empty after sync
        assert await env["queue"].get_pending_count() == 0

    @pytest.mark.asyncio
    async def test_sync_transaction_delete(self, sync_env):
        env = sync_env
        trans = _make_transaction()
        await env["trans_repo"].save(trans)
        # Simulate: the create was already synced
        await env["queue"].clear_all()
        # Now delete
        await env["trans_repo"].delete(trans.id)

        env["cloud_trans"].delete = AsyncMock()
        env["cloud_trans"].delete_versioned = AsyncMock(return_value=True)

        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        count = await service.sync_now()
        assert count == 1
        # Version-checked delete should be used when version > 0
        env["cloud_trans"].delete_versioned.assert_called()

    @pytest.mark.asyncio
    async def test_sync_skipped_when_not_connected(self, sync_env):
        env = sync_env
        env["conn_state"]._connected = False

        await env["trans_repo"].save(_make_transaction())

        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        count = await service.sync_now()
        assert count == 0
        # Queue should still have the pending change
        assert await env["queue"].get_pending_count() == 1

    @pytest.mark.asyncio
    async def test_sync_skipped_when_not_running(self, sync_env):
        env = sync_env
        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        # Not started
        service._running = False

        count = await service.sync_now()
        assert count == 0

    @pytest.mark.asyncio
    async def test_sync_skipped_when_already_syncing(self, sync_env):
        env = sync_env
        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True
        service._is_syncing = True

        count = await service.sync_now()
        assert count == 0


class TestSyncServiceErrorHandling:
    """Test how sync handles various error types."""

    @pytest.mark.asyncio
    async def test_transient_error_retries_later(self, sync_env):
        env = sync_env
        trans = _make_transaction()
        await env["trans_repo"].save(trans)

        # Cloud save raises transient error
        env["cloud_trans"].save = AsyncMock(
            side_effect=ConnectionError("connection reset")
        )

        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        count = await service.sync_now()
        assert count == 0

        # Change should still be pending (marked failed, back to pending)
        pending = await env["queue"].get_pending()
        assert len(pending) == 1
        assert pending[0].retry_count == 1

    @pytest.mark.asyncio
    async def test_permanent_error_marks_conflict(self, sync_env):
        env = sync_env
        trans = _make_transaction()
        await env["trans_repo"].save(trans)

        # Cloud save raises permanent error
        env["cloud_trans"].save = AsyncMock(
            side_effect=Exception("permission denied for table transactions")
        )

        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        count = await service.sync_now()
        assert count == 0

        # Change should be marked as conflict
        conflicts = await env["queue"].get_conflicts()
        assert len(conflicts) == 1


class TestSyncServiceCategorySync:
    """Test syncing category operations."""

    @pytest.mark.asyncio
    async def test_sync_category_add(self, sync_env):
        env = sync_env
        await env["cat_repo"].add("expense", "Fuel")

        env["cloud_cat"].add = AsyncMock()

        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        count = await service.sync_now()
        assert count == 1
        env["cloud_cat"].add.assert_called_once_with("expense", "Fuel")

    @pytest.mark.asyncio
    async def test_sync_category_remove(self, sync_env):
        env = sync_env
        await env["queue"].enqueue_category_remove("Fuel", "expense")

        env["cloud_cat"].remove = AsyncMock()

        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        count = await service.sync_now()
        assert count == 1
        env["cloud_cat"].remove.assert_called_once_with("expense", "Fuel")

    @pytest.mark.asyncio
    async def test_sync_category_reorder(self, sync_env):
        env = sync_env
        await env["queue"].enqueue_category_reorder(["C", "B", "A"], "expense")

        env["cloud_cat"].set_all = AsyncMock()

        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        count = await service.sync_now()
        assert count == 1
        env["cloud_cat"].set_all.assert_called_once_with("expense", ["C", "B", "A"])


class TestSyncServiceEventDriven:
    """Test event-driven push debounce."""

    def test_on_queue_changed_starts_debounce(self, sync_env):
        env = sync_env
        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        # QTimer.start() requires a QThread, so mock it to verify it's called
        from unittest.mock import patch
        with patch.object(service._push_debounce, 'start') as mock_start:
            service._on_queue_changed()
            mock_start.assert_called_once()

        service.stop()

    def test_on_queue_changed_ignored_when_stopped(self, sync_env):
        env = sync_env
        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = False

        service._on_queue_changed()
        assert not service._push_debounce.isActive()

    def test_on_push_debounce_emits_trigger(self, sync_env):
        env = sync_env
        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        triggered = []
        service._trigger_sync.connect(lambda: triggered.append(1))

        service._on_push_debounce()
        assert len(triggered) == 1

        service.stop()

    def test_on_push_debounce_skipped_when_disconnected(self, sync_env):
        env = sync_env
        env["conn_state"]._connected = False

        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service._running = True

        triggered = []
        service._trigger_sync.connect(lambda: triggered.append(1))

        service._on_push_debounce()
        assert len(triggered) == 0

        service.stop()

    def test_stop_clears_on_change_callback(self, sync_env):
        env = sync_env
        service = SyncService(
            sync_queue=env["queue"],
            transaction_repo=env["trans_repo"],
            planned_repo=env["planned_repo"],
            sheet_repo=env["sheet_repo"],
            category_repo=env["cat_repo"],
            connection_state=env["conn_state"],
        )
        service.start()
        assert env["queue"].on_change is not None

        service.stop()
        assert env["queue"].on_change is None
