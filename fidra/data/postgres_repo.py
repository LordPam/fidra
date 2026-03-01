"""PostgreSQL implementation of repository interfaces using asyncpg.

Works with any PostgreSQL database (Supabase, self-hosted, etc.)
"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union, TYPE_CHECKING
from uuid import UUID

import asyncpg

from fidra.data.repository import (
    ActivityNotesRepository,
    AttachmentRepository,
    AuditRepository,
    CategoryRepository,
    ConcurrencyError,
    EntityDeletedError,
    PlannedRepository,
    SheetRepository,
    TransactionRepository,
)
from fidra.domain.models import (
    ApprovalStatus,
    Attachment,
    AuditAction,
    AuditEntry,
    Frequency,
    PlannedTemplate,
    Sheet,
    Transaction,
    TransactionType,
)

if TYPE_CHECKING:
    from fidra.data.cloud_connection import CloudConnection


class PostgresTransactionRepository(TransactionRepository):
    """PostgreSQL implementation of TransactionRepository."""

    def __init__(self, pool_or_connection: Union[asyncpg.Pool, "CloudConnection"]):
        """Initialize with either a pool or CloudConnection.

        Args:
            pool_or_connection: Either an asyncpg.Pool directly, or a CloudConnection
                                that provides dynamic pool access (preferred for reconnection support)
        """
        self._pool_or_connection = pool_or_connection

    @property
    def _pool(self) -> asyncpg.Pool:
        """Get the current pool, supporting both direct pool and CloudConnection."""
        if hasattr(self._pool_or_connection, 'pool'):
            # It's a CloudConnection - get current pool
            return self._pool_or_connection.pool
        # It's a direct pool reference
        return self._pool_or_connection

    async def get_all(self, sheet: Optional[str] = None) -> list[Transaction]:
        """Get all transactions, optionally filtered by sheet."""
        query = "SELECT * FROM transactions"
        params = []

        if sheet and sheet != "All Sheets":
            query += " WHERE sheet = $1"
            params.append(sheet)

        query += " ORDER BY date DESC, created_at DESC"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [self._row_to_transaction(row) for row in rows]

    async def get_by_id(self, id: UUID) -> Optional[Transaction]:
        """Get a single transaction by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM transactions WHERE id = $1", id
            )
            return self._row_to_transaction(row) if row else None

    async def save(self, transaction: Transaction) -> Transaction:
        """Save (insert or update) a transaction.

        Uses a single connection for version check + write to avoid TOCTOU races.
        The ON CONFLICT UPDATE includes a WHERE version guard so the upsert is
        atomic: another device can't sneak in between check and write.
        """
        async with self._pool.acquire() as conn:
            # Check current state on the same connection we'll use for the write
            existing_version = await conn.fetchval(
                "SELECT version FROM transactions WHERE id = $1", transaction.id
            )

            if existing_version is not None:
                if existing_version != transaction.version - 1:
                    raise ConcurrencyError(
                        f"Version conflict: expected DB version {transaction.version - 1}, found {existing_version}"
                    )
            elif transaction.version > 1:
                raise EntityDeletedError(
                    f"Transaction {transaction.id} was deleted on server (local version {transaction.version})"
                )

            # For new inserts (version == 1), use plain ON CONFLICT upsert.
            # For updates, add WHERE version guard to make the check+write atomic.
            if existing_version is not None:
                result = await conn.execute(
                    """
                    UPDATE transactions SET
                        date = $2, description = $3, amount = $4, type = $5,
                        status = $6, sheet = $7, category = $8, party = $9,
                        notes = $10, reference = $11, activity = $12,
                        version = $13, modified_at = $14, modified_by = $15
                    WHERE id = $1 AND version = $16
                    """,
                    transaction.id,
                    transaction.date,
                    transaction.description,
                    transaction.amount,
                    transaction.type.value,
                    transaction.status.value,
                    transaction.sheet,
                    transaction.category,
                    transaction.party,
                    transaction.notes,
                    transaction.reference,
                    transaction.activity,
                    transaction.version,
                    transaction.modified_at,
                    transaction.modified_by,
                    existing_version,  # WHERE version = this
                )
                if result == "UPDATE 0":
                    raise ConcurrencyError(
                        f"Concurrent update to transaction {transaction.id}"
                    )
            else:
                await conn.execute(
                    """
                    INSERT INTO transactions
                    (id, date, description, amount, type, status, sheet,
                     category, party, notes, reference, activity, version, created_at, modified_at, modified_by)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                    ON CONFLICT (id) DO UPDATE SET
                        date = EXCLUDED.date,
                        description = EXCLUDED.description,
                        amount = EXCLUDED.amount,
                        type = EXCLUDED.type,
                        status = EXCLUDED.status,
                        sheet = EXCLUDED.sheet,
                        category = EXCLUDED.category,
                        party = EXCLUDED.party,
                        notes = EXCLUDED.notes,
                        reference = EXCLUDED.reference,
                        activity = EXCLUDED.activity,
                        version = EXCLUDED.version,
                        modified_at = EXCLUDED.modified_at,
                        modified_by = EXCLUDED.modified_by
                    """,
                    transaction.id,
                    transaction.date,
                    transaction.description,
                    transaction.amount,
                    transaction.type.value,
                    transaction.status.value,
                    transaction.sheet,
                    transaction.category,
                    transaction.party,
                    transaction.notes,
                    transaction.reference,
                    transaction.activity,
                    transaction.version,
                    transaction.created_at,
                    transaction.modified_at,
                    transaction.modified_by,
                )
        return transaction

    async def delete(self, id: UUID) -> bool:
        """Delete a transaction."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM transactions WHERE id = $1", id
            )
            return result == "DELETE 1"

    async def delete_versioned(self, id: UUID, expected_version: int) -> bool:
        """Delete a transaction with version check.

        Args:
            id: Transaction UUID to delete
            expected_version: Expected version number

        Returns:
            True if deleted

        Raises:
            ConcurrencyError: If the row exists but has a different version
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM transactions WHERE id = $1 AND version = $2",
                id, expected_version,
            )
            if result == "DELETE 1":
                return True
            # Check if row still exists (version mismatch vs already gone)
            row = await conn.fetchrow(
                "SELECT version FROM transactions WHERE id = $1", id
            )
            if row:
                raise ConcurrencyError(
                    f"Delete version conflict: expected {expected_version}, found {row['version']}"
                )
            # Row already gone — concurrent delete is fine
            return True

    async def bulk_save(self, transactions: list[Transaction]) -> list[Transaction]:
        """Save multiple transactions atomically.

        Note: Each save acquires its own connection for version checking.
        Wrapping in a pool-level transaction is not possible across connections,
        so this provides best-effort ordering but not true atomicity for the
        PostgreSQL backend. Use individual saves for version-checked writes.
        """
        for trans in transactions:
            await self.save(trans)
        return transactions

    async def bulk_delete(self, ids: list[UUID]) -> int:
        """Delete multiple transactions."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM transactions WHERE id = ANY($1::uuid[])",
                ids,
            )
            # Parse "DELETE N" result
            return int(result.split()[1]) if result else 0

    async def get_version(self, id: UUID) -> Optional[int]:
        """Get current version for optimistic concurrency."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT version FROM transactions WHERE id = $1", id
            )
            return row["version"] if row else None

    def _row_to_transaction(self, row: asyncpg.Record) -> Transaction:
        """Convert database row to Transaction model."""
        return Transaction(
            id=row["id"],
            date=row["date"],
            description=row["description"],
            amount=Decimal(str(row["amount"])),
            type=TransactionType(row["type"]),
            status=ApprovalStatus(row["status"]),
            sheet=row["sheet"],
            category=row["category"],
            party=row["party"],
            notes=row["notes"],
            reference=row["reference"],
            activity=row.get("activity"),
            version=row["version"],
            created_at=row["created_at"],
            modified_at=row["modified_at"],
            modified_by=row["modified_by"],
        )


class PostgresPlannedRepository(PlannedRepository):
    """PostgreSQL implementation of PlannedRepository."""

    def __init__(self, pool_or_connection: Union[asyncpg.Pool, "CloudConnection"]):
        self._pool_or_connection = pool_or_connection

    @property
    def _pool(self) -> asyncpg.Pool:
        if hasattr(self._pool_or_connection, 'pool'):
            return self._pool_or_connection.pool
        return self._pool_or_connection

    async def get_all(self) -> list[PlannedTemplate]:
        """Get all planned templates."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM planned_templates ORDER BY start_date"
            )
            return [self._row_to_template(row) for row in rows]

    async def get_by_id(self, id: UUID) -> Optional[PlannedTemplate]:
        """Get a single planned template by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM planned_templates WHERE id = $1", id
            )
            return self._row_to_template(row) if row else None

    async def get_version(self, id: UUID) -> Optional[int]:
        """Get current version for optimistic concurrency."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT version FROM planned_templates WHERE id = $1", id
            )
            return row["version"] if row else None

    async def save(self, template: PlannedTemplate) -> PlannedTemplate:
        """Save (insert or update) a planned template.

        Uses a single connection for version check + write to avoid TOCTOU races.
        """
        skipped_dates_json = json.dumps([d.isoformat() for d in template.skipped_dates])
        fulfilled_dates_json = json.dumps([d.isoformat() for d in template.fulfilled_dates])

        async with self._pool.acquire() as conn:
            existing_version = await conn.fetchval(
                "SELECT version FROM planned_templates WHERE id = $1", template.id
            )

            if existing_version is not None:
                if existing_version != template.version - 1:
                    raise ConcurrencyError(
                        f"PlannedTemplate version conflict: expected DB version {template.version - 1}, found {existing_version}"
                    )
                result = await conn.execute(
                    """
                    UPDATE planned_templates SET
                        start_date = $2, description = $3, amount = $4, type = $5,
                        frequency = $6, target_sheet = $7, category = $8, party = $9,
                        activity = $10, end_date = $11, occurrence_count = $12,
                        skipped_dates = $13, fulfilled_dates = $14, version = $15
                    WHERE id = $1 AND version = $16
                    """,
                    template.id,
                    template.start_date,
                    template.description,
                    template.amount,
                    template.type.value,
                    template.frequency.value,
                    template.target_sheet,
                    template.category,
                    template.party,
                    template.activity,
                    template.end_date,
                    template.occurrence_count,
                    skipped_dates_json,
                    fulfilled_dates_json,
                    template.version,
                    existing_version,  # WHERE version = this
                )
                if result == "UPDATE 0":
                    raise ConcurrencyError(
                        f"Concurrent update to planned template {template.id}"
                    )
            elif template.version > 1:
                raise EntityDeletedError(
                    f"PlannedTemplate {template.id} was deleted on server (local version {template.version})"
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO planned_templates
                    (id, start_date, description, amount, type, frequency, target_sheet,
                     category, party, activity, end_date, occurrence_count, skipped_dates, fulfilled_dates,
                     version, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                    ON CONFLICT (id) DO UPDATE SET
                        start_date = EXCLUDED.start_date,
                        description = EXCLUDED.description,
                        amount = EXCLUDED.amount,
                        type = EXCLUDED.type,
                        frequency = EXCLUDED.frequency,
                        target_sheet = EXCLUDED.target_sheet,
                        category = EXCLUDED.category,
                        party = EXCLUDED.party,
                        activity = EXCLUDED.activity,
                        end_date = EXCLUDED.end_date,
                        occurrence_count = EXCLUDED.occurrence_count,
                        skipped_dates = EXCLUDED.skipped_dates,
                        fulfilled_dates = EXCLUDED.fulfilled_dates,
                        version = EXCLUDED.version
                    """,
                    template.id,
                    template.start_date,
                    template.description,
                    template.amount,
                    template.type.value,
                    template.frequency.value,
                    template.target_sheet,
                    template.category,
                    template.party,
                    template.activity,
                    template.end_date,
                    template.occurrence_count,
                    skipped_dates_json,
                    fulfilled_dates_json,
                    template.version,
                    template.created_at,
                )
        return template

    async def delete(self, id: UUID) -> bool:
        """Delete a planned template."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM planned_templates WHERE id = $1", id
            )
            return result == "DELETE 1"

    async def delete_versioned(self, id: UUID, expected_version: int) -> bool:
        """Delete a planned template with version check.

        Args:
            id: PlannedTemplate UUID to delete
            expected_version: Expected version number

        Returns:
            True if deleted

        Raises:
            ConcurrencyError: If the row exists but has a different version
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM planned_templates WHERE id = $1 AND version = $2",
                id, expected_version,
            )
            if result == "DELETE 1":
                return True
            # Check if row still exists (version mismatch vs already gone)
            row = await conn.fetchrow(
                "SELECT version FROM planned_templates WHERE id = $1", id
            )
            if row:
                raise ConcurrencyError(
                    f"PlannedTemplate delete version conflict: expected {expected_version}, found {row['version']}"
                )
            # Row already gone — concurrent delete is fine
            return True

    def _row_to_template(self, row: asyncpg.Record) -> PlannedTemplate:
        """Convert database row to PlannedTemplate model."""
        # Parse JSONB arrays
        skipped_raw = row["skipped_dates"]
        fulfilled_raw = row["fulfilled_dates"]

        # Handle both string JSON and native JSONB
        if isinstance(skipped_raw, str):
            skipped_list = json.loads(skipped_raw)
        else:
            skipped_list = skipped_raw or []

        if isinstance(fulfilled_raw, str):
            fulfilled_list = json.loads(fulfilled_raw)
        else:
            fulfilled_list = fulfilled_raw or []

        skipped_dates = tuple(date.fromisoformat(d) for d in skipped_list)
        fulfilled_dates = tuple(date.fromisoformat(d) for d in fulfilled_list)

        return PlannedTemplate(
            id=row["id"],
            start_date=row["start_date"],
            description=row["description"],
            amount=Decimal(str(row["amount"])),
            type=TransactionType(row["type"]),
            target_sheet=row["target_sheet"],
            frequency=Frequency(row["frequency"]),
            category=row["category"],
            party=row["party"],
            activity=row.get("activity"),
            end_date=row["end_date"],
            occurrence_count=row["occurrence_count"],
            skipped_dates=skipped_dates,
            fulfilled_dates=fulfilled_dates,
            version=row["version"],
            created_at=row["created_at"],
        )


class PostgresSheetRepository(SheetRepository):
    """PostgreSQL implementation of SheetRepository."""

    def __init__(self, pool_or_connection: Union[asyncpg.Pool, "CloudConnection"]):
        self._pool_or_connection = pool_or_connection

    @property
    def _pool(self) -> asyncpg.Pool:
        if hasattr(self._pool_or_connection, 'pool'):
            return self._pool_or_connection.pool
        return self._pool_or_connection

    async def get_all(self) -> list[Sheet]:
        """Get all sheets."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM sheets ORDER BY name")
            return [self._row_to_sheet(row) for row in rows]

    async def get_by_id(self, id: UUID) -> Optional[Sheet]:
        """Get a single sheet by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM sheets WHERE id = $1", id)
            return self._row_to_sheet(row) if row else None

    async def get_by_name(self, name: str) -> Optional[Sheet]:
        """Get a single sheet by name."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM sheets WHERE name = $1", name)
            return self._row_to_sheet(row) if row else None

    async def create(self, name: str, **kwargs) -> Sheet:
        """Create a new sheet."""
        sheet = Sheet.create(name, **kwargs)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sheets (id, name, is_virtual, is_planned, created_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                sheet.id,
                sheet.name,
                sheet.is_virtual,
                sheet.is_planned,
                sheet.created_at,
            )
        return sheet

    async def save(self, sheet: Sheet) -> Sheet:
        """Save a sheet (insert or update)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sheets (id, name, is_virtual, is_planned, created_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    is_virtual = EXCLUDED.is_virtual,
                    is_planned = EXCLUDED.is_planned
                """,
                sheet.id,
                sheet.name,
                sheet.is_virtual,
                sheet.is_planned,
                sheet.created_at,
            )
        return sheet

    async def delete(self, id: UUID) -> bool:
        """Delete a sheet."""
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM sheets WHERE id = $1", id)
            return result == "DELETE 1"

    def _row_to_sheet(self, row: asyncpg.Record) -> Sheet:
        """Convert database row to Sheet model."""
        return Sheet(
            id=row["id"],
            name=row["name"],
            is_virtual=row["is_virtual"],
            is_planned=row["is_planned"],
            created_at=row["created_at"],
        )


class PostgresAttachmentRepository(AttachmentRepository):
    """PostgreSQL implementation of AttachmentRepository."""

    def __init__(self, pool_or_connection: Union[asyncpg.Pool, "CloudConnection"]):
        self._pool_or_connection = pool_or_connection

    @property
    def _pool(self) -> asyncpg.Pool:
        if hasattr(self._pool_or_connection, 'pool'):
            return self._pool_or_connection.pool
        return self._pool_or_connection

    async def save(self, attachment: Attachment) -> Attachment:
        """Save an attachment record."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO attachments
                (id, transaction_id, filename, stored_name, mime_type, file_size, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    filename = EXCLUDED.filename,
                    stored_name = EXCLUDED.stored_name,
                    mime_type = EXCLUDED.mime_type,
                    file_size = EXCLUDED.file_size
                """,
                attachment.id,
                attachment.transaction_id,
                attachment.filename,
                attachment.stored_name,
                attachment.mime_type,
                attachment.file_size,
                attachment.created_at,
            )
        return attachment

    async def get_for_transaction(self, transaction_id: UUID) -> list[Attachment]:
        """Get all attachments for a transaction."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM attachments WHERE transaction_id = $1 ORDER BY created_at",
                transaction_id,
            )
            return [self._row_to_attachment(row) for row in rows]

    async def get_by_id(self, id: UUID) -> Optional[Attachment]:
        """Get a single attachment by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM attachments WHERE id = $1", id)
            return self._row_to_attachment(row) if row else None

    async def delete(self, id: UUID) -> bool:
        """Delete an attachment record."""
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM attachments WHERE id = $1", id)
            return result == "DELETE 1"

    async def delete_for_transaction(self, transaction_id: UUID) -> int:
        """Delete all attachments for a transaction."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM attachments WHERE transaction_id = $1",
                transaction_id,
            )
            return int(result.split()[1]) if result else 0

    def _row_to_attachment(self, row: asyncpg.Record) -> Attachment:
        """Convert database row to Attachment model."""
        return Attachment(
            id=row["id"],
            transaction_id=row["transaction_id"],
            filename=row["filename"],
            stored_name=row["stored_name"],
            mime_type=row["mime_type"],
            file_size=row["file_size"],
            created_at=row["created_at"],
        )


class PostgresAuditRepository(AuditRepository):
    """PostgreSQL implementation of AuditRepository."""

    def __init__(self, pool_or_connection: Union[asyncpg.Pool, "CloudConnection"]):
        self._pool_or_connection = pool_or_connection

    @property
    def _pool(self) -> asyncpg.Pool:
        if hasattr(self._pool_or_connection, 'pool'):
            return self._pool_or_connection.pool
        return self._pool_or_connection

    async def log(self, entry: AuditEntry) -> None:
        """Write an audit log entry."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_log
                (id, timestamp, action, entity_type, entity_id, "user", summary, details)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                entry.id,
                entry.timestamp,
                entry.action.value,
                entry.entity_type,
                entry.entity_id,
                entry.user,
                entry.summary,
                entry.details,
            )

    async def get_all(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[UUID] = None,
        limit: int = 500,
    ) -> list[AuditEntry]:
        """Get audit log entries with optional filters."""
        query = "SELECT * FROM audit_log"
        params = []
        conditions = []

        if entity_type:
            conditions.append(f"entity_type = ${len(params) + 1}")
            params.append(entity_type)

        if entity_id:
            conditions.append(f"entity_id = ${len(params) + 1}")
            params.append(entity_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY timestamp DESC LIMIT ${len(params) + 1}"
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [self._row_to_entry(row) for row in rows]

    async def get_for_entity(self, entity_id: UUID) -> list[AuditEntry]:
        """Get all audit entries for a specific entity."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM audit_log WHERE entity_id = $1 ORDER BY timestamp DESC",
                entity_id,
            )
            return [self._row_to_entry(row) for row in rows]

    def _row_to_entry(self, row: asyncpg.Record) -> AuditEntry:
        """Convert database row to AuditEntry model."""
        return AuditEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            action=AuditAction(row["action"]),
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            user=row["user"],
            summary=row["summary"],
            details=row["details"],
        )


class PostgresCategoryRepository(CategoryRepository):
    """PostgreSQL implementation of CategoryRepository."""

    def __init__(self, pool_or_connection: Union[asyncpg.Pool, "CloudConnection"]):
        self._pool_or_connection = pool_or_connection

    @property
    def _pool(self) -> asyncpg.Pool:
        if hasattr(self._pool_or_connection, 'pool'):
            return self._pool_or_connection.pool
        return self._pool_or_connection

    async def ensure_table(self) -> None:
        """Ensure the categories table exists."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                    name TEXT NOT NULL,
                    sort_order INTEGER DEFAULT 0,
                    UNIQUE(type, name)
                )
            """)
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_categories_type ON categories(type)"
            )

    async def get_all(self, type: str) -> list[str]:
        """Get all categories for a transaction type."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name FROM categories WHERE type = $1 ORDER BY sort_order, name",
                type,
            )
            return [row["name"] for row in rows]

    async def add(self, type: str, name: str) -> None:
        """Add a category."""
        async with self._pool.acquire() as conn:
            # Get max sort_order for this type
            row = await conn.fetchrow(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 as next_order FROM categories WHERE type = $1",
                type,
            )
            sort_order = row["next_order"]

            await conn.execute(
                "INSERT INTO categories (type, name, sort_order) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                type, name, sort_order,
            )

    async def remove(self, type: str, name: str) -> bool:
        """Remove a category."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM categories WHERE type = $1 AND name = $2",
                type, name,
            )
            return result == "DELETE 1"

    async def set_all(self, type: str, names: list[str]) -> None:
        """Replace all categories for a type atomically."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Delete existing
                await conn.execute("DELETE FROM categories WHERE type = $1", type)

                # Insert new with sort order
                for i, name in enumerate(names):
                    await conn.execute(
                        "INSERT INTO categories (type, name, sort_order) VALUES ($1, $2, $3)",
                        type, name, i,
                    )


class PostgresActivityNotesRepository(ActivityNotesRepository):
    """PostgreSQL implementation of ActivityNotesRepository."""

    def __init__(self, pool_or_connection: Union[asyncpg.Pool, "CloudConnection"]):
        self._pool_or_connection = pool_or_connection

    @property
    def _pool(self) -> asyncpg.Pool:
        if hasattr(self._pool_or_connection, 'pool'):
            return self._pool_or_connection.pool
        return self._pool_or_connection

    async def ensure_table(self) -> None:
        """Ensure the activity_notes table exists."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS activity_notes (
                    activity TEXT PRIMARY KEY,
                    notes TEXT NOT NULL
                )
            """)

    async def get_all(self) -> dict[str, str]:
        """Get all activity notes."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT activity, notes FROM activity_notes ORDER BY activity"
            )
            return {row["activity"]: row["notes"] for row in rows}

    async def save(self, activity: str, notes: str) -> None:
        """Save notes for an activity."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO activity_notes (activity, notes) VALUES ($1, $2)
                ON CONFLICT (activity) DO UPDATE SET notes = EXCLUDED.notes
                """,
                activity, notes,
            )

    async def delete(self, activity: str) -> None:
        """Delete notes for an activity."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM activity_notes WHERE activity = $1",
                activity,
            )

    async def set_all(self, notes: dict[str, str]) -> None:
        """Replace all activity notes atomically."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM activity_notes")
                for activity, text in notes.items():
                    await conn.execute(
                        "INSERT INTO activity_notes (activity, notes) VALUES ($1, $2)",
                        activity, text,
                    )
