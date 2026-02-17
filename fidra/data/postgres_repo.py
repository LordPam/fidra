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
    AttachmentRepository,
    AuditRepository,
    CategoryRepository,
    ConcurrencyError,
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
        """Save (insert or update) a transaction."""
        # Check for version conflict
        existing_version = await self.get_version(transaction.id)
        if existing_version is not None:
            if existing_version != transaction.version - 1:
                raise ConcurrencyError(
                    f"Version conflict: expected DB version {transaction.version - 1}, found {existing_version}"
                )

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO transactions
                (id, date, description, amount, type, status, sheet,
                 category, party, notes, reference, version, created_at, modified_at, modified_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
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

    async def bulk_save(self, transactions: list[Transaction]) -> list[Transaction]:
        """Save multiple transactions atomically."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
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

    async def save(self, template: PlannedTemplate) -> PlannedTemplate:
        """Save (insert or update) a planned template."""
        # Convert date tuples to JSON arrays
        skipped_dates_json = [d.isoformat() for d in template.skipped_dates]
        fulfilled_dates_json = [d.isoformat() for d in template.fulfilled_dates]

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO planned_templates
                (id, start_date, description, amount, type, frequency, target_sheet,
                 category, party, end_date, occurrence_count, skipped_dates, fulfilled_dates,
                 version, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (id) DO UPDATE SET
                    start_date = EXCLUDED.start_date,
                    description = EXCLUDED.description,
                    amount = EXCLUDED.amount,
                    type = EXCLUDED.type,
                    frequency = EXCLUDED.frequency,
                    target_sheet = EXCLUDED.target_sheet,
                    category = EXCLUDED.category,
                    party = EXCLUDED.party,
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
                template.end_date,
                template.occurrence_count,
                json.dumps(skipped_dates_json),
                json.dumps(fulfilled_dates_json),
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
        """Replace all categories for a type."""
        async with self._pool.acquire() as conn:
            # Delete existing
            await conn.execute("DELETE FROM categories WHERE type = $1", type)

            # Insert new with sort order
            for i, name in enumerate(names):
                await conn.execute(
                    "INSERT INTO categories (type, name, sort_order) VALUES ($1, $2, $3)",
                    type, name, i,
                )
