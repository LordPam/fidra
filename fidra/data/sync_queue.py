"""Sync queue for managing pending cloud synchronization.

Stores pending changes in SQLite for persistence across app restarts.
Changes are queued when offline and processed when connection is restored.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

import aiosqlite

logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    """Status of a sync operation."""

    PENDING = "pending"
    PROCESSING = "processing"
    CONFLICT = "conflict"
    FAILED = "failed"


class SyncOperation(Enum):
    """Type of sync operation."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class PendingChange:
    """Represents a change waiting to be synced to the cloud."""

    id: UUID
    entity_type: str  # "transaction", "planned_template", "sheet", "category"
    entity_id: UUID
    operation: SyncOperation
    payload: str  # JSON serialized entity or operation data
    local_version: int
    created_at: datetime
    retry_count: int = 0
    last_error: Optional[str] = None
    status: SyncStatus = SyncStatus.PENDING


class SyncQueue:
    """Manages a queue of pending sync operations in SQLite.

    Persists changes to disk so they survive app restarts.
    Provides FIFO ordering for processing.
    """

    def __init__(self, db_path: Path):
        """Initialize sync queue.

        Args:
            db_path: Path to SQLite database file for queue storage
        """
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        # Callback fired whenever a change is enqueued (for event-driven sync)
        self.on_change: Optional[callable] = None

    async def initialize(self) -> None:
        """Initialize the queue database."""
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._ensure_schema()
        await self._recover_stuck_processing()
        logger.info(f"Sync queue initialized at {self._db_path}")

    async def _recover_stuck_processing(self) -> None:
        """Reset any items stuck in 'processing' from a previous crash.

        If the app crashes mid-sync, items remain in 'processing' status
        and are never retried. Reset them back to 'pending'.
        """
        cursor = await self._conn.execute(
            "UPDATE sync_queue SET status = 'pending' WHERE status = 'processing'"
        )
        await self._conn.commit()
        if cursor.rowcount and cursor.rowcount > 0:
            logger.info(f"Recovered {cursor.rowcount} stuck processing items")

    async def _ensure_schema(self) -> None:
        """Create sync queue tables if they don't exist."""
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_queue (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                payload TEXT NOT NULL,
                local_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                last_error TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sync_queue_status
            ON sync_queue(status)
        """)
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sync_queue_entity
            ON sync_queue(entity_type, entity_id)
        """)

        # Metadata table for tracking sync state
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await self._conn.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def enqueue(self, change: PendingChange) -> None:
        """Add a change to the queue.

        Args:
            change: The pending change to enqueue
        """
        await self._conn.execute(
            """
            INSERT INTO sync_queue
            (id, entity_type, entity_id, operation, payload, local_version,
             created_at, retry_count, last_error, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(change.id),
                change.entity_type,
                str(change.entity_id),
                change.operation.value,
                change.payload,
                change.local_version,
                change.created_at.isoformat(),
                change.retry_count,
                change.last_error,
                change.status.value,
            ),
        )
        await self._conn.commit()
        logger.debug(f"Enqueued {change.operation.value} for {change.entity_type} {change.entity_id}")
        if self.on_change:
            self.on_change()

    async def enqueue_save(self, entity_type: str, entity: Any) -> None:
        """Convenience method to enqueue a save (create/update) operation.

        Args:
            entity_type: Type of entity ("transaction", "planned_template", etc.)
            entity: The entity to save
        """
        logger.debug(f"enqueue_save called for {entity_type} {entity.id}")
        # Check if this is an update (existing entity in queue)
        existing = await self.get_pending_for_entity(entity.id)

        # Serialize entity
        payload = self._serialize_entity(entity)
        version = getattr(entity, "version", 1)

        if existing:
            # Update existing queue entry
            await self._conn.execute(
                """
                UPDATE sync_queue
                SET payload = ?, local_version = ?, status = 'pending',
                    retry_count = 0, last_error = NULL
                WHERE entity_id = ? AND entity_type = ?
                """,
                (payload, version, str(entity.id), entity_type),
            )
            await self._conn.commit()
            if self.on_change:
                self.on_change()
        else:
            # New entry
            operation = SyncOperation.CREATE if version == 1 else SyncOperation.UPDATE
            change = PendingChange(
                id=uuid4(),
                entity_type=entity_type,
                entity_id=entity.id,
                operation=operation,
                payload=payload,
                local_version=version,
                created_at=datetime.now(),
            )
            await self.enqueue(change)

    async def enqueue_delete(
        self, entity_type: str, entity_id: UUID, version: int = 0
    ) -> None:
        """Convenience method to enqueue a delete operation.

        Args:
            entity_type: Type of entity
            entity_id: ID of entity to delete
            version: Expected server version for version-checked delete (0 = skip check)
        """
        # Check BEFORE removing: was this entity only ever created locally?
        existing = await self.get_pending_for_entity(entity_id)
        was_only_local = existing and existing.operation == SyncOperation.CREATE

        # Remove any pending creates/updates for this entity
        await self._conn.execute(
            """
            DELETE FROM sync_queue
            WHERE entity_id = ? AND entity_type = ? AND operation != 'delete'
            """,
            (str(entity_id), entity_type),
        )
        await self._conn.commit()

        # If it was never synced (only a pending CREATE), no cloud delete needed
        if was_only_local:
            return

        change = PendingChange(
            id=uuid4(),
            entity_type=entity_type,
            entity_id=entity_id,
            operation=SyncOperation.DELETE,
            payload="{}",
            local_version=version,
            created_at=datetime.now(),
        )
        await self.enqueue(change)

    async def enqueue_category_add(self, name: str, type: str) -> None:
        """Queue a category add operation."""
        change = PendingChange(
            id=uuid4(),
            entity_type="category",
            entity_id=uuid4(),  # Categories don't have UUIDs, use placeholder
            operation=SyncOperation.CREATE,
            payload=json.dumps({"name": name, "type": type, "action": "add"}),
            local_version=1,
            created_at=datetime.now(),
        )
        await self.enqueue(change)

    async def enqueue_category_remove(self, name: str, type: str) -> None:
        """Queue a category remove operation."""
        change = PendingChange(
            id=uuid4(),
            entity_type="category",
            entity_id=uuid4(),
            operation=SyncOperation.DELETE,
            payload=json.dumps({"name": name, "type": type, "action": "remove"}),
            local_version=1,
            created_at=datetime.now(),
        )
        await self.enqueue(change)

    async def enqueue_category_reorder(self, names: list[str], type: str) -> None:
        """Queue a category reorder operation."""
        change = PendingChange(
            id=uuid4(),
            entity_type="category",
            entity_id=uuid4(),
            operation=SyncOperation.UPDATE,
            payload=json.dumps({"names": names, "type": type, "action": "reorder"}),
            local_version=1,
            created_at=datetime.now(),
        )
        await self.enqueue(change)

    async def dequeue(self, id: UUID) -> None:
        """Remove a change from the queue (after successful sync).

        Args:
            id: ID of the pending change to remove
        """
        await self._conn.execute(
            "DELETE FROM sync_queue WHERE id = ?",
            (str(id),),
        )
        await self._conn.commit()
        logger.debug(f"Dequeued change {id}")

    async def get_pending(self, limit: int = 100) -> list[PendingChange]:
        """Get pending changes in FIFO order.

        Args:
            limit: Maximum number of changes to return

        Returns:
            List of pending changes ordered by creation time
        """
        cursor = await self._conn.execute(
            """
            SELECT id, entity_type, entity_id, operation, payload, local_version,
                   created_at, retry_count, last_error, status
            FROM sync_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_change(row) for row in rows]

    async def get_pending_count(self) -> int:
        """Get the number of pending changes.

        Returns:
            Count of pending changes
        """
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM sync_queue WHERE status = 'pending'"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_by_id(self, change_id: UUID) -> Optional[PendingChange]:
        """Get a change by its queue entry ID.

        Args:
            change_id: Queue entry ID

        Returns:
            PendingChange if exists, None otherwise
        """
        cursor = await self._conn.execute(
            """
            SELECT id, entity_type, entity_id, operation, payload, local_version,
                   created_at, retry_count, last_error, status
            FROM sync_queue
            WHERE id = ?
            """,
            (str(change_id),),
        )
        row = await cursor.fetchone()
        return self._row_to_change(row) if row else None

    async def has_pending_for_type(self, entity_type: str) -> bool:
        """Check if any pending or processing changes exist for an entity type.

        Args:
            entity_type: Type of entity (e.g. "category", "transaction")

        Returns:
            True if pending changes exist for this type
        """
        cursor = await self._conn.execute(
            "SELECT 1 FROM sync_queue WHERE entity_type = ? AND status IN ('pending', 'processing') LIMIT 1",
            (entity_type,),
        )
        row = await cursor.fetchone()
        return row is not None

    async def get_pending_for_entity(self, entity_id: UUID) -> Optional[PendingChange]:
        """Get pending change for a specific entity.

        Args:
            entity_id: Entity ID to look up

        Returns:
            Pending change if exists, None otherwise
        """
        cursor = await self._conn.execute(
            """
            SELECT id, entity_type, entity_id, operation, payload, local_version,
                   created_at, retry_count, last_error, status
            FROM sync_queue
            WHERE entity_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (str(entity_id),),
        )
        row = await cursor.fetchone()
        return self._row_to_change(row) if row else None

    async def mark_processing(self, id: UUID) -> None:
        """Mark a change as being processed.

        Args:
            id: Change ID
        """
        await self._conn.execute(
            "UPDATE sync_queue SET status = 'processing' WHERE id = ?",
            (str(id),),
        )
        await self._conn.commit()

    async def mark_conflict(self, id: UUID, error: str) -> None:
        """Mark a change as having a conflict.

        Args:
            id: Change ID
            error: Description of the conflict
        """
        await self._conn.execute(
            """
            UPDATE sync_queue
            SET status = 'conflict', last_error = ?
            WHERE id = ?
            """,
            (error, str(id)),
        )
        await self._conn.commit()
        logger.warning(f"Change {id} marked as conflict: {error}")

    async def mark_failed(self, id: UUID, error: str) -> None:
        """Mark a change as failed and increment retry count.

        Args:
            id: Change ID
            error: Error message
        """
        await self._conn.execute(
            """
            UPDATE sync_queue
            SET status = 'pending', retry_count = retry_count + 1, last_error = ?
            WHERE id = ?
            """,
            (error, str(id)),
        )
        await self._conn.commit()
        logger.warning(f"Change {id} failed: {error}")

    async def get_conflicts(self) -> list[PendingChange]:
        """Get all changes with conflicts.

        Returns:
            List of conflicting changes
        """
        cursor = await self._conn.execute(
            """
            SELECT id, entity_type, entity_id, operation, payload, local_version,
                   created_at, retry_count, last_error, status
            FROM sync_queue
            WHERE status = 'conflict'
            ORDER BY created_at ASC
            """
        )
        rows = await cursor.fetchall()
        return [self._row_to_change(row) for row in rows]

    async def resolve_conflict(self, id: UUID, use_local: bool) -> None:
        """Resolve a conflict.

        Args:
            id: Change ID
            use_local: If True, retry with local version. If False, discard local change.
        """
        if use_local:
            # Reset to pending for retry
            await self._conn.execute(
                """
                UPDATE sync_queue
                SET status = 'pending', retry_count = 0, last_error = NULL
                WHERE id = ?
                """,
                (str(id),),
            )
        else:
            # Discard local change
            await self.dequeue(id)
        await self._conn.commit()

    async def clear_all(self) -> None:
        """Clear all pending changes (use with caution)."""
        await self._conn.execute("DELETE FROM sync_queue")
        await self._conn.commit()
        logger.info("Sync queue cleared")

    def _row_to_change(self, row: tuple) -> PendingChange:
        """Convert database row to PendingChange object."""
        return PendingChange(
            id=UUID(row[0]),
            entity_type=row[1],
            entity_id=UUID(row[2]),
            operation=SyncOperation(row[3]),
            payload=row[4],
            local_version=row[5],
            created_at=datetime.fromisoformat(row[6]),
            retry_count=row[7],
            last_error=row[8],
            status=SyncStatus(row[9]),
        )

    def _serialize_entity(self, entity: Any) -> str:
        """Serialize an entity to JSON.

        Args:
            entity: Entity to serialize

        Returns:
            JSON string
        """
        data = asdict(entity) if hasattr(entity, "__dataclass_fields__") else {}

        # Convert non-JSON-serializable types
        from decimal import Decimal

        def convert(obj):
            if isinstance(obj, UUID):
                return str(obj)
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "isoformat"):  # date
                return obj.isoformat()
            if hasattr(obj, "value"):  # Enum
                return obj.value
            if isinstance(obj, tuple):
                return list(obj)
            return obj

        def convert_dict(d):
            if isinstance(d, dict):
                return {k: convert_dict(v) for k, v in d.items()}
            elif isinstance(d, (list, tuple)):
                return [convert_dict(i) for i in d]
            else:
                return convert(d)

        return json.dumps(convert_dict(data))

    # Metadata methods

    async def set_metadata(self, key: str, value: str) -> None:
        """Set a metadata value.

        Args:
            key: Metadata key
            value: Metadata value
        """
        await self._conn.execute(
            """
            INSERT INTO sync_metadata (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self._conn.commit()

    async def get_metadata(self, key: str) -> Optional[str]:
        """Get a metadata value.

        Args:
            key: Metadata key

        Returns:
            Metadata value or None
        """
        cursor = await self._conn.execute(
            "SELECT value FROM sync_metadata WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None
