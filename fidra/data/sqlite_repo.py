"""SQLite implementation of repository interfaces."""

import aiosqlite
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import UUID

from fidra.data.repository import (
    ActivityNotesRepository,
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


class SQLiteTransactionRepository(TransactionRepository):
    """SQLite implementation of TransactionRepository."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Connect to database and ensure schema exists."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._ensure_schema()

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()

    async def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                status TEXT NOT NULL CHECK (status IN ('--', 'pending', 'approved', 'rejected', 'planned')),
                sheet TEXT NOT NULL,
                category TEXT,
                party TEXT,
                reference TEXT,
                activity TEXT,
                notes TEXT,
                version INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                modified_at TEXT,
                modified_by TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
            CREATE INDEX IF NOT EXISTS idx_transactions_sheet ON transactions(sheet);
            CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
            CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);

            CREATE TABLE IF NOT EXISTS planned_templates (
                id TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                frequency TEXT NOT NULL CHECK (frequency IN ('once', 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly')),
                target_sheet TEXT NOT NULL,
                category TEXT,
                party TEXT,
                activity TEXT,
                end_date TEXT,
                occurrence_count INTEGER,
                skipped_dates TEXT DEFAULT '[]',
                fulfilled_dates TEXT DEFAULT '[]',
                version INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_planned_start ON planned_templates(start_date);
            CREATE INDEX IF NOT EXISTS idx_planned_target ON planned_templates(target_sheet);

            CREATE TABLE IF NOT EXISTS sheets (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                is_virtual INTEGER DEFAULT 0,
                is_planned INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sheets_name ON sheets(name);

            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                mime_type TEXT,
                file_size INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_attachments_transaction
                ON attachments(transaction_id);

            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL CHECK (action IN ('create', 'update', 'delete')),
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                user TEXT NOT NULL,
                summary TEXT NOT NULL,
                details TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                name TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(type, name)
            );

            CREATE INDEX IF NOT EXISTS idx_categories_type ON categories(type);

            CREATE TABLE IF NOT EXISTS activity_notes (
                activity TEXT PRIMARY KEY,
                notes TEXT NOT NULL
            );
        """
        )
        await self._conn.commit()
        await self._run_migrations()

    async def _run_migrations(self) -> None:
        """Run database migrations for schema updates."""
        # Add reference column if it doesn't exist (for existing databases)
        async with self._conn.execute("PRAGMA table_info(transactions)") as cursor:
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

        if "reference" not in column_names:
            await self._conn.execute(
                "ALTER TABLE transactions ADD COLUMN reference TEXT"
            )
            await self._conn.commit()

        if "activity" not in column_names:
            await self._conn.execute(
                "ALTER TABLE transactions ADD COLUMN activity TEXT"
            )
            await self._conn.commit()

        # Add activity column to planned_templates if it doesn't exist
        async with self._conn.execute("PRAGMA table_info(planned_templates)") as cursor:
            pt_columns = await cursor.fetchall()
            pt_column_names = [col[1] for col in pt_columns]

        if "activity" not in pt_column_names:
            await self._conn.execute(
                "ALTER TABLE planned_templates ADD COLUMN activity TEXT"
            )
            await self._conn.commit()

    async def get_all(self, sheet: Optional[str] = None) -> list[Transaction]:
        """Get all transactions, optionally filtered by sheet."""
        query = "SELECT * FROM transactions"
        params = []

        if sheet and sheet != "All Sheets":
            query += " WHERE sheet = ?"
            params.append(sheet)

        query += " ORDER BY date DESC, created_at DESC"

        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_transaction(row) for row in rows]

    async def get_by_id(self, id: UUID) -> Optional[Transaction]:
        """Get a single transaction by ID."""
        async with self._conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (str(id),)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_transaction(row) if row else None

    async def save(self, transaction: Transaction, *, force: bool = False) -> Transaction:
        """Save (insert or update) a transaction.

        Args:
            transaction: Transaction to save.
            force: If True, skip version check (used for cache refresh from cloud).
        """
        if not force:
            # Check for version conflict
            # For updates: DB version should be transaction.version - 1
            # For inserts: DB version should be None
            existing_version = await self.get_version(transaction.id)
            if existing_version is not None:
                # This is an update - check that we're updating from the right version
                if existing_version != transaction.version - 1:
                    raise ConcurrencyError(
                        f"Version conflict: expected DB version {transaction.version - 1}, found {existing_version}"
                    )

        await self._conn.execute(
            """
            INSERT OR REPLACE INTO transactions
            (id, date, description, amount, type, status, sheet,
             category, party, reference, activity, notes, version, created_at, modified_at, modified_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                str(transaction.id),
                transaction.date.isoformat(),
                transaction.description,
                str(transaction.amount),
                transaction.type.value,
                transaction.status.value,
                transaction.sheet,
                transaction.category,
                transaction.party,
                transaction.reference,
                transaction.activity,
                transaction.notes,
                transaction.version,
                transaction.created_at.isoformat(),
                transaction.modified_at.isoformat() if transaction.modified_at else None,
                transaction.modified_by,
            ),
        )
        await self._conn.commit()
        return transaction

    async def delete(self, id: UUID) -> bool:
        """Delete a transaction."""
        cursor = await self._conn.execute(
            "DELETE FROM transactions WHERE id = ?", (str(id),)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def bulk_save(self, transactions: list[Transaction]) -> list[Transaction]:
        """Save multiple transactions atomically."""
        async with self._conn.execute("BEGIN"):
            for trans in transactions:
                await self.save(trans)
        return transactions

    async def bulk_delete(self, ids: list[UUID]) -> int:
        """Delete multiple transactions."""
        placeholders = ",".join("?" * len(ids))
        cursor = await self._conn.execute(
            f"DELETE FROM transactions WHERE id IN ({placeholders})",
            [str(id) for id in ids],
        )
        await self._conn.commit()
        return cursor.rowcount

    async def get_version(self, id: UUID) -> Optional[int]:
        """Get current version for optimistic concurrency."""
        async with self._conn.execute(
            "SELECT version FROM transactions WHERE id = ?", (str(id),)
        ) as cursor:
            row = await cursor.fetchone()
            return row["version"] if row else None

    def _row_to_transaction(self, row: aiosqlite.Row) -> Transaction:
        """Convert database row to Transaction model."""
        # Handle fields which may not exist in older databases
        try:
            reference = row["reference"]
        except (KeyError, IndexError):
            reference = None

        try:
            activity = row["activity"]
        except (KeyError, IndexError):
            activity = None

        return Transaction(
            id=UUID(row["id"]),
            date=date.fromisoformat(row["date"]),
            description=row["description"],
            amount=Decimal(row["amount"]),
            type=TransactionType(row["type"]),
            status=ApprovalStatus(row["status"]),
            sheet=row["sheet"],
            category=row["category"],
            party=row["party"],
            reference=reference,
            activity=activity,
            notes=row["notes"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            modified_at=(
                datetime.fromisoformat(row["modified_at"]) if row["modified_at"] else None
            ),
            modified_by=row["modified_by"],
        )


class SQLitePlannedRepository(PlannedRepository):
    """SQLite implementation of PlannedRepository."""

    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def get_all(self) -> list[PlannedTemplate]:
        """Get all planned templates."""
        async with self._conn.execute(
            "SELECT * FROM planned_templates ORDER BY start_date"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_template(row) for row in rows]

    async def get_by_id(self, id: UUID) -> Optional[PlannedTemplate]:
        """Get a single planned template by ID."""
        async with self._conn.execute(
            "SELECT * FROM planned_templates WHERE id = ?", (str(id),)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_template(row) if row else None

    async def save(self, template: PlannedTemplate) -> PlannedTemplate:
        """Save (insert or update) a planned template."""
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO planned_templates
            (id, start_date, description, amount, type, frequency, target_sheet,
             category, party, activity, end_date, occurrence_count, skipped_dates, fulfilled_dates,
             version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                str(template.id),
                template.start_date.isoformat(),
                template.description,
                str(template.amount),
                template.type.value,
                template.frequency.value,
                template.target_sheet,
                template.category,
                template.party,
                template.activity,
                template.end_date.isoformat() if template.end_date else None,
                template.occurrence_count,
                json.dumps([d.isoformat() for d in template.skipped_dates]),
                json.dumps([d.isoformat() for d in template.fulfilled_dates]),
                template.version,
                template.created_at.isoformat(),
            ),
        )
        await self._conn.commit()
        return template

    async def get_version(self, id: UUID) -> Optional[int]:
        """Get current version for optimistic concurrency."""
        async with self._conn.execute(
            "SELECT version FROM planned_templates WHERE id = ?", (str(id),)
        ) as cursor:
            row = await cursor.fetchone()
            return row["version"] if row else None

    async def delete(self, id: UUID) -> bool:
        """Delete a planned template."""
        cursor = await self._conn.execute(
            "DELETE FROM planned_templates WHERE id = ?", (str(id),)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_template(self, row: aiosqlite.Row) -> PlannedTemplate:
        """Convert database row to PlannedTemplate model."""
        skipped_dates = tuple(
            date.fromisoformat(d) for d in json.loads(row["skipped_dates"] or "[]")
        )
        fulfilled_dates = tuple(
            date.fromisoformat(d) for d in json.loads(row["fulfilled_dates"] or "[]")
        )

        return PlannedTemplate(
            id=UUID(row["id"]),
            start_date=date.fromisoformat(row["start_date"]),
            description=row["description"],
            amount=Decimal(row["amount"]),
            type=TransactionType(row["type"]),
            target_sheet=row["target_sheet"],
            frequency=Frequency(row["frequency"]),
            category=row["category"],
            party=row["party"],
            activity=row["activity"] if "activity" in row.keys() else None,
            end_date=date.fromisoformat(row["end_date"]) if row["end_date"] else None,
            occurrence_count=row["occurrence_count"],
            skipped_dates=skipped_dates,
            fulfilled_dates=fulfilled_dates,
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class SQLiteSheetRepository(SheetRepository):
    """SQLite implementation of SheetRepository."""

    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def get_all(self) -> list[Sheet]:
        """Get all sheets."""
        async with self._conn.execute(
            "SELECT * FROM sheets ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_sheet(row) for row in rows]

    async def get_by_id(self, id: UUID) -> Optional[Sheet]:
        """Get a single sheet by ID."""
        async with self._conn.execute(
            "SELECT * FROM sheets WHERE id = ?", (str(id),)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_sheet(row) if row else None

    async def get_by_name(self, name: str) -> Optional[Sheet]:
        """Get a single sheet by name."""
        async with self._conn.execute(
            "SELECT * FROM sheets WHERE name = ?", (name,)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_sheet(row) if row else None

    async def create(self, name: str, **kwargs: any) -> Sheet:
        """Create a new sheet."""
        sheet = Sheet.create(name, **kwargs)

        await self._conn.execute(
            """
            INSERT INTO sheets (id, name, is_virtual, is_planned, created_at)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                str(sheet.id),
                sheet.name,
                1 if sheet.is_virtual else 0,
                1 if sheet.is_planned else 0,
                sheet.created_at.isoformat(),
            ),
        )
        await self._conn.commit()
        return sheet

    async def save(self, sheet: Sheet) -> Sheet:
        """Save a sheet (insert or update)."""
        await self._conn.execute(
            """
            INSERT INTO sheets (id, name, is_virtual, is_planned, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                is_virtual = excluded.is_virtual,
                is_planned = excluded.is_planned
            """,
            (
                str(sheet.id),
                sheet.name,
                1 if sheet.is_virtual else 0,
                1 if sheet.is_planned else 0,
                sheet.created_at.isoformat(),
            ),
        )
        await self._conn.commit()
        return sheet

    async def delete(self, id: UUID) -> bool:
        """Delete a sheet."""
        cursor = await self._conn.execute("DELETE FROM sheets WHERE id = ?", (str(id),))
        await self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_sheet(self, row: aiosqlite.Row) -> Sheet:
        """Convert database row to Sheet model."""
        return Sheet(
            id=UUID(row["id"]),
            name=row["name"],
            is_virtual=bool(row["is_virtual"]),
            is_planned=bool(row["is_planned"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class SQLiteAttachmentRepository(AttachmentRepository):
    """SQLite implementation of AttachmentRepository."""

    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def save(self, attachment: Attachment) -> Attachment:
        """Save an attachment record."""
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO attachments
            (id, transaction_id, filename, stored_name, mime_type, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(attachment.id),
                str(attachment.transaction_id),
                attachment.filename,
                attachment.stored_name,
                attachment.mime_type,
                attachment.file_size,
                attachment.created_at.isoformat(),
            ),
        )
        await self._conn.commit()
        return attachment

    async def get_for_transaction(self, transaction_id: UUID) -> list[Attachment]:
        """Get all attachments for a transaction."""
        async with self._conn.execute(
            "SELECT * FROM attachments WHERE transaction_id = ? ORDER BY created_at",
            (str(transaction_id),),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_attachment(row) for row in rows]

    async def get_by_id(self, id: UUID) -> Optional[Attachment]:
        """Get a single attachment by ID."""
        async with self._conn.execute(
            "SELECT * FROM attachments WHERE id = ?", (str(id),)
        ) as cursor:
            row = await cursor.fetchone()
            return self._row_to_attachment(row) if row else None

    async def delete(self, id: UUID) -> bool:
        """Delete an attachment record."""
        cursor = await self._conn.execute(
            "DELETE FROM attachments WHERE id = ?", (str(id),)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def delete_for_transaction(self, transaction_id: UUID) -> int:
        """Delete all attachments for a transaction."""
        cursor = await self._conn.execute(
            "DELETE FROM attachments WHERE transaction_id = ?",
            (str(transaction_id),),
        )
        await self._conn.commit()
        return cursor.rowcount

    def _row_to_attachment(self, row: aiosqlite.Row) -> Attachment:
        """Convert database row to Attachment model."""
        return Attachment(
            id=UUID(row["id"]),
            transaction_id=UUID(row["transaction_id"]),
            filename=row["filename"],
            stored_name=row["stored_name"],
            mime_type=row["mime_type"],
            file_size=row["file_size"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class SQLiteAuditRepository(AuditRepository):
    """SQLite implementation of AuditRepository."""

    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def log(self, entry: AuditEntry) -> None:
        """Write an audit log entry."""
        await self._conn.execute(
            """
            INSERT INTO audit_log (id, timestamp, action, entity_type, entity_id, user, summary, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(entry.id),
                entry.timestamp.isoformat(),
                entry.action.value,
                entry.entity_type,
                str(entry.entity_id),
                entry.user,
                entry.summary,
                entry.details,
            ),
        )
        await self._conn.commit()

    async def get_all(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[UUID] = None,
        limit: int = 500,
    ) -> list[AuditEntry]:
        """Get audit log entries with optional filters."""
        query = "SELECT * FROM audit_log"
        params: list = []
        conditions = []

        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        if entity_id:
            conditions.append("entity_id = ?")
            params.append(str(entity_id))

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def get_for_entity(self, entity_id: UUID) -> list[AuditEntry]:
        """Get all audit entries for a specific entity."""
        async with self._conn.execute(
            "SELECT * FROM audit_log WHERE entity_id = ? ORDER BY timestamp DESC",
            (str(entity_id),),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    def _row_to_entry(self, row: aiosqlite.Row) -> AuditEntry:
        """Convert database row to AuditEntry model."""
        return AuditEntry(
            id=UUID(row["id"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            action=AuditAction(row["action"]),
            entity_type=row["entity_type"],
            entity_id=UUID(row["entity_id"]),
            user=row["user"],
            summary=row["summary"],
            details=row["details"],
        )


class SQLiteCategoryRepository(CategoryRepository):
    """SQLite implementation of CategoryRepository."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Connect to database."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()

    def set_connection(self, conn: aiosqlite.Connection) -> None:
        """Share connection from another repository."""
        self._conn = conn

    async def get_all(self, type: str) -> list[str]:
        """Get all categories for a transaction type."""
        async with self._conn.execute(
            "SELECT name FROM categories WHERE type = ? ORDER BY sort_order, name",
            (type,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [row["name"] for row in rows]

    async def add(self, type: str, name: str) -> None:
        """Add a category."""
        # Get max sort_order for this type
        async with self._conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 as next_order FROM categories WHERE type = ?",
            (type,),
        ) as cursor:
            row = await cursor.fetchone()
            sort_order = row["next_order"]

        await self._conn.execute(
            "INSERT OR IGNORE INTO categories (type, name, sort_order) VALUES (?, ?, ?)",
            (type, name, sort_order),
        )
        await self._conn.commit()

    async def remove(self, type: str, name: str) -> bool:
        """Remove a category."""
        cursor = await self._conn.execute(
            "DELETE FROM categories WHERE type = ? AND name = ?",
            (type, name),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def set_all(self, type: str, names: list[str]) -> None:
        """Replace all categories for a type."""
        # Delete existing
        await self._conn.execute("DELETE FROM categories WHERE type = ?", (type,))

        # Insert new with sort order
        for i, name in enumerate(names):
            await self._conn.execute(
                "INSERT INTO categories (type, name, sort_order) VALUES (?, ?, ?)",
                (type, name, i),
            )

        await self._conn.commit()


class SQLiteActivityNotesRepository(ActivityNotesRepository):
    """SQLite implementation of ActivityNotesRepository."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Connect to database."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            await self._conn.close()

    def set_connection(self, conn: aiosqlite.Connection) -> None:
        """Share connection from another repository."""
        self._conn = conn

    async def get_all(self) -> dict[str, str]:
        """Get all activity notes."""
        async with self._conn.execute(
            "SELECT activity, notes FROM activity_notes ORDER BY activity"
        ) as cursor:
            rows = await cursor.fetchall()
            return {row["activity"]: row["notes"] for row in rows}

    async def save(self, activity: str, notes: str) -> None:
        """Save notes for an activity."""
        await self._conn.execute(
            "INSERT OR REPLACE INTO activity_notes (activity, notes) VALUES (?, ?)",
            (activity, notes),
        )
        await self._conn.commit()

    async def delete(self, activity: str) -> None:
        """Delete notes for an activity."""
        await self._conn.execute(
            "DELETE FROM activity_notes WHERE activity = ?",
            (activity,),
        )
        await self._conn.commit()

    async def set_all(self, notes: dict[str, str]) -> None:
        """Replace all activity notes."""
        await self._conn.execute("DELETE FROM activity_notes")
        for activity, text in notes.items():
            await self._conn.execute(
                "INSERT INTO activity_notes (activity, notes) VALUES (?, ?)",
                (activity, text),
            )
        await self._conn.commit()
