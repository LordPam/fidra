"""Tests for SyncQueue - persistent queue for pending cloud sync operations."""

import pytest
from datetime import datetime
from uuid import uuid4

from fidra.data.sync_queue import (
    SyncQueue,
    PendingChange,
    SyncOperation,
    SyncStatus,
)


@pytest.fixture
async def queue(tmp_path):
    """Create a SyncQueue with a temporary database."""
    q = SyncQueue(tmp_path / "sync_queue.db")
    await q.initialize()
    yield q
    await q.close()


def _make_change(**kwargs) -> PendingChange:
    """Helper to create a PendingChange with defaults."""
    defaults = dict(
        id=uuid4(),
        entity_type="transaction",
        entity_id=uuid4(),
        operation=SyncOperation.CREATE,
        payload='{"description":"test"}',
        local_version=1,
        created_at=datetime.now(),
    )
    defaults.update(kwargs)
    return PendingChange(**defaults)


class TestSyncQueueBasic:
    """Basic enqueue/dequeue operations."""

    @pytest.mark.asyncio
    async def test_enqueue_and_get_pending(self, queue):
        change = _make_change()
        await queue.enqueue(change)

        pending = await queue.get_pending()
        assert len(pending) == 1
        assert pending[0].id == change.id
        assert pending[0].entity_type == "transaction"
        assert pending[0].operation == SyncOperation.CREATE

    @pytest.mark.asyncio
    async def test_dequeue_removes_change(self, queue):
        change = _make_change()
        await queue.enqueue(change)

        await queue.dequeue(change.id)

        pending = await queue.get_pending()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_pending_count(self, queue):
        assert await queue.get_pending_count() == 0

        await queue.enqueue(_make_change())
        await queue.enqueue(_make_change())
        assert await queue.get_pending_count() == 2

    @pytest.mark.asyncio
    async def test_fifo_ordering(self, queue):
        changes = []
        for i in range(3):
            c = _make_change(created_at=datetime(2024, 1, 1, 0, 0, i))
            changes.append(c)
            await queue.enqueue(c)

        pending = await queue.get_pending()
        assert [p.id for p in pending] == [c.id for c in changes]

    @pytest.mark.asyncio
    async def test_get_pending_with_limit(self, queue):
        for _ in range(5):
            await queue.enqueue(_make_change())

        pending = await queue.get_pending(limit=2)
        assert len(pending) == 2

    @pytest.mark.asyncio
    async def test_clear_all(self, queue):
        for _ in range(3):
            await queue.enqueue(_make_change())
        assert await queue.get_pending_count() == 3

        await queue.clear_all()
        assert await queue.get_pending_count() == 0


class TestSyncQueueStatuses:
    """Status transitions: pending -> processing, failed, conflict."""

    @pytest.mark.asyncio
    async def test_mark_processing(self, queue):
        change = _make_change()
        await queue.enqueue(change)

        await queue.mark_processing(change.id)

        # Processing items are NOT returned by get_pending
        pending = await queue.get_pending()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_mark_failed_increments_retry(self, queue):
        change = _make_change()
        await queue.enqueue(change)

        await queue.mark_failed(change.id, "network timeout")

        # Failed items go back to pending with incremented retry count
        pending = await queue.get_pending()
        assert len(pending) == 1
        assert pending[0].retry_count == 1
        assert pending[0].last_error == "network timeout"

    @pytest.mark.asyncio
    async def test_mark_conflict(self, queue):
        change = _make_change()
        await queue.enqueue(change)

        await queue.mark_conflict(change.id, "version mismatch")

        # Conflict items are NOT in pending
        pending = await queue.get_pending()
        assert len(pending) == 0

        # But ARE in conflicts
        conflicts = await queue.get_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].last_error == "version mismatch"

    @pytest.mark.asyncio
    async def test_resolve_conflict_use_local(self, queue):
        change = _make_change()
        await queue.enqueue(change)
        await queue.mark_conflict(change.id, "version mismatch")

        await queue.resolve_conflict(change.id, use_local=True)

        # Goes back to pending for retry
        pending = await queue.get_pending()
        assert len(pending) == 1
        assert pending[0].retry_count == 0

    @pytest.mark.asyncio
    async def test_resolve_conflict_use_server(self, queue):
        change = _make_change()
        await queue.enqueue(change)
        await queue.mark_conflict(change.id, "version mismatch")

        await queue.resolve_conflict(change.id, use_local=False)

        # Removed from queue entirely
        pending = await queue.get_pending()
        assert len(pending) == 0
        conflicts = await queue.get_conflicts()
        assert len(conflicts) == 0


class TestSyncQueueConvenience:
    """High-level enqueue_save, enqueue_delete, category operations."""

    @pytest.mark.asyncio
    async def test_enqueue_save_new_entity(self, queue):
        from dataclasses import dataclass
        from decimal import Decimal

        entity_id = uuid4()

        @dataclass
        class FakeEntity:
            id: uuid4
            description: str
            amount: Decimal
            version: int = 1

        entity = FakeEntity(id=entity_id, description="test", amount=Decimal("50"))
        await queue.enqueue_save("transaction", entity)

        pending = await queue.get_pending()
        assert len(pending) == 1
        assert pending[0].operation == SyncOperation.CREATE
        assert pending[0].entity_id == entity_id

    @pytest.mark.asyncio
    async def test_enqueue_save_updates_existing(self, queue):
        from dataclasses import dataclass
        from decimal import Decimal

        entity_id = uuid4()

        @dataclass
        class FakeEntity:
            id: uuid4
            description: str
            amount: Decimal
            version: int = 1

        entity = FakeEntity(id=entity_id, description="v1", amount=Decimal("50"))
        await queue.enqueue_save("transaction", entity)

        # Update the same entity
        entity2 = FakeEntity(id=entity_id, description="v2", amount=Decimal("75"), version=2)
        await queue.enqueue_save("transaction", entity2)

        # Should still be just one entry (updated in place)
        pending = await queue.get_pending()
        assert len(pending) == 1
        assert '"v2"' in pending[0].payload

    @pytest.mark.asyncio
    async def test_enqueue_delete(self, queue):
        entity_id = uuid4()
        await queue.enqueue_delete("transaction", entity_id)

        pending = await queue.get_pending()
        assert len(pending) == 1
        assert pending[0].operation == SyncOperation.DELETE
        assert pending[0].entity_id == entity_id

    @pytest.mark.asyncio
    async def test_enqueue_delete_cancels_pending_create(self, queue):
        from dataclasses import dataclass

        entity_id = uuid4()

        @dataclass
        class FakeEntity:
            id: uuid4
            version: int = 1

        entity = FakeEntity(id=entity_id)
        await queue.enqueue_save("transaction", entity)
        assert await queue.get_pending_count() == 1

        # Delete the same entity - should cancel the create
        await queue.enqueue_delete("transaction", entity_id)

        # The create was removed; no delete needed since it was never synced
        pending = await queue.get_pending()
        # Should have the delete queued (since enqueue_delete removes non-delete
        # entries first, then checks if the remaining one was a CREATE)
        # After removing the CREATE, nothing remains, so no delete is needed
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_enqueue_category_add(self, queue):
        await queue.enqueue_category_add("Fuel", "expense")

        pending = await queue.get_pending()
        assert len(pending) == 1
        assert pending[0].entity_type == "category"
        assert pending[0].operation == SyncOperation.CREATE
        assert '"Fuel"' in pending[0].payload

    @pytest.mark.asyncio
    async def test_enqueue_category_remove(self, queue):
        await queue.enqueue_category_remove("Fuel", "expense")

        pending = await queue.get_pending()
        assert len(pending) == 1
        assert pending[0].operation == SyncOperation.DELETE

    @pytest.mark.asyncio
    async def test_enqueue_category_reorder(self, queue):
        await queue.enqueue_category_reorder(["A", "B", "C"], "expense")

        pending = await queue.get_pending()
        assert len(pending) == 1
        assert pending[0].operation == SyncOperation.UPDATE


class TestSyncQueueOnChange:
    """Test the on_change callback for event-driven sync."""

    @pytest.mark.asyncio
    async def test_on_change_fires_on_enqueue(self, queue):
        calls = []
        queue.on_change = lambda: calls.append(1)

        await queue.enqueue(_make_change())
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_on_change_fires_on_enqueue_save_update(self, queue):
        from dataclasses import dataclass

        calls = []

        @dataclass
        class FakeEntity:
            id: uuid4
            version: int = 1

        entity_id = uuid4()
        entity = FakeEntity(id=entity_id)
        await queue.enqueue_save("transaction", entity)

        # Now set callback and update
        queue.on_change = lambda: calls.append(1)
        entity2 = FakeEntity(id=entity_id, version=2)
        await queue.enqueue_save("transaction", entity2)

        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_on_change_not_called_when_none(self, queue):
        queue.on_change = None
        # Should not raise
        await queue.enqueue(_make_change())


class TestSyncQueueMetadata:
    """Test metadata storage."""

    @pytest.mark.asyncio
    async def test_set_and_get_metadata(self, queue):
        await queue.set_metadata("last_sync", "2024-01-01T00:00:00")
        value = await queue.get_metadata("last_sync")
        assert value == "2024-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_get_metadata_nonexistent(self, queue):
        value = await queue.get_metadata("nonexistent")
        assert value is None

    @pytest.mark.asyncio
    async def test_set_metadata_upsert(self, queue):
        await queue.set_metadata("key", "v1")
        await queue.set_metadata("key", "v2")
        assert await queue.get_metadata("key") == "v2"


class TestSyncQueuePersistence:
    """Test that queue survives close/reopen."""

    @pytest.mark.asyncio
    async def test_data_persists_across_reopen(self, tmp_path):
        path = tmp_path / "persist.db"

        # Write
        q1 = SyncQueue(path)
        await q1.initialize()
        await q1.enqueue(_make_change())
        await q1.close()

        # Reopen
        q2 = SyncQueue(path)
        await q2.initialize()
        pending = await q2.get_pending()
        assert len(pending) == 1
        await q2.close()
