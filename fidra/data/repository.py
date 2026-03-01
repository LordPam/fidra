"""Abstract repository interfaces for data access.

The repository pattern provides an abstraction over data storage,
allowing the application to work with different backends (SQLite, Excel)
without changing business logic.
"""

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from fidra.domain.models import Attachment, AuditEntry, PlannedTemplate, Sheet, Transaction


class TransactionRepository(ABC):
    """Abstract interface for transaction storage."""

    @abstractmethod
    async def get_all(self, sheet: Optional[str] = None) -> list[Transaction]:
        """Get all transactions, optionally filtered by sheet.

        Args:
            sheet: Optional sheet name to filter by. None returns all transactions.

        Returns:
            List of transactions sorted by date descending
        """
        ...

    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[Transaction]:
        """Get a single transaction by ID.

        Args:
            id: Transaction UUID

        Returns:
            Transaction if found, None otherwise
        """
        ...

    @abstractmethod
    async def save(self, transaction: Transaction) -> Transaction:
        """Save (insert or update) a transaction.

        Args:
            transaction: Transaction to save

        Returns:
            Saved transaction instance

        Raises:
            ConcurrencyError: If version conflict detected
        """
        ...

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete a transaction.

        Args:
            id: Transaction UUID to delete

        Returns:
            True if deleted, False if not found
        """
        ...

    @abstractmethod
    async def bulk_save(self, transactions: list[Transaction]) -> list[Transaction]:
        """Save multiple transactions atomically.

        Args:
            transactions: List of transactions to save

        Returns:
            List of saved transactions
        """
        ...

    @abstractmethod
    async def bulk_delete(self, ids: list[UUID]) -> int:
        """Delete multiple transactions.

        Args:
            ids: List of transaction UUIDs to delete

        Returns:
            Count of transactions deleted
        """
        ...

    @abstractmethod
    async def get_version(self, id: UUID) -> Optional[int]:
        """Get current version for optimistic concurrency.

        Args:
            id: Transaction UUID

        Returns:
            Current version number, or None if not found
        """
        ...


class PlannedRepository(ABC):
    """Abstract interface for planned template storage."""

    @abstractmethod
    async def get_all(self) -> list[PlannedTemplate]:
        """Get all planned templates.

        Returns:
            List of planned templates sorted by start_date
        """
        ...

    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[PlannedTemplate]:
        """Get a single planned template by ID.

        Args:
            id: PlannedTemplate UUID

        Returns:
            PlannedTemplate if found, None otherwise
        """
        ...

    @abstractmethod
    async def save(self, template: PlannedTemplate) -> PlannedTemplate:
        """Save (insert or update) a planned template.

        Args:
            template: PlannedTemplate to save

        Returns:
            Saved template instance
        """
        ...

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete a planned template.

        Args:
            id: PlannedTemplate UUID to delete

        Returns:
            True if deleted, False if not found
        """
        ...


class SheetRepository(ABC):
    """Abstract interface for sheet management."""

    @abstractmethod
    async def get_all(self) -> list[Sheet]:
        """Get all sheets.

        Returns:
            List of sheets sorted by name
        """
        ...

    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[Sheet]:
        """Get a single sheet by ID.

        Args:
            id: Sheet UUID

        Returns:
            Sheet if found, None otherwise
        """
        ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Sheet]:
        """Get a single sheet by name.

        Args:
            name: Sheet name

        Returns:
            Sheet if found, None otherwise
        """
        ...

    @abstractmethod
    async def create(self, name: str, **kwargs: any) -> Sheet:
        """Create a new sheet.

        Args:
            name: Sheet name
            **kwargs: Optional fields (is_virtual, is_planned)

        Returns:
            Created sheet
        """
        ...

    @abstractmethod
    async def save(self, sheet: Sheet) -> Sheet:
        """Save a sheet (insert or update).

        Args:
            sheet: Sheet to save

        Returns:
            Saved sheet
        """
        ...

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete a sheet.

        Args:
            id: Sheet UUID to delete

        Returns:
            True if deleted, False if not found
        """
        ...


class AttachmentRepository(ABC):
    """Abstract interface for attachment metadata storage."""

    @abstractmethod
    async def save(self, attachment: Attachment) -> Attachment:
        """Save an attachment record."""
        ...

    @abstractmethod
    async def get_for_transaction(self, transaction_id: UUID) -> list[Attachment]:
        """Get all attachments for a transaction."""
        ...

    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[Attachment]:
        """Get a single attachment by ID."""
        ...

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete an attachment record."""
        ...

    @abstractmethod
    async def delete_for_transaction(self, transaction_id: UUID) -> int:
        """Delete all attachments for a transaction."""
        ...


class AuditRepository(ABC):
    """Abstract interface for audit log storage."""

    @abstractmethod
    async def log(self, entry: AuditEntry) -> None:
        """Write an audit log entry.

        Args:
            entry: Audit entry to persist
        """
        ...

    @abstractmethod
    async def get_all(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[UUID] = None,
        limit: int = 500,
    ) -> list[AuditEntry]:
        """Get audit log entries with optional filters.

        Args:
            entity_type: Filter by entity type
            entity_id: Filter by specific entity
            limit: Max entries to return

        Returns:
            List of audit entries, most recent first
        """
        ...

    @abstractmethod
    async def get_for_entity(self, entity_id: UUID) -> list[AuditEntry]:
        """Get all audit entries for a specific entity.

        Args:
            entity_id: Entity UUID

        Returns:
            List of audit entries for the entity
        """
        ...


class CategoryRepository(ABC):
    """Abstract interface for category storage."""

    @abstractmethod
    async def get_all(self, type: str) -> list[str]:
        """Get all categories for a transaction type.

        Args:
            type: 'income' or 'expense'

        Returns:
            List of category names
        """
        ...

    @abstractmethod
    async def add(self, type: str, name: str) -> None:
        """Add a category.

        Args:
            type: 'income' or 'expense'
            name: Category name
        """
        ...

    @abstractmethod
    async def remove(self, type: str, name: str) -> bool:
        """Remove a category.

        Args:
            type: 'income' or 'expense'
            name: Category name

        Returns:
            True if removed, False if not found
        """
        ...

    @abstractmethod
    async def set_all(self, type: str, names: list[str]) -> None:
        """Replace all categories for a type.

        Args:
            type: 'income' or 'expense'
            names: List of category names
        """
        ...


class ActivityNotesRepository(ABC):
    """Abstract interface for activity notes storage."""

    @abstractmethod
    async def get_all(self) -> dict[str, str]:
        """Get all activity notes.

        Returns:
            Dict mapping activity name to notes text
        """
        ...

    @abstractmethod
    async def save(self, activity: str, notes: str) -> None:
        """Save notes for an activity.

        Args:
            activity: Activity name
            notes: Notes text
        """
        ...

    @abstractmethod
    async def delete(self, activity: str) -> None:
        """Delete notes for an activity.

        Args:
            activity: Activity name
        """
        ...

    @abstractmethod
    async def set_all(self, notes: dict[str, str]) -> None:
        """Replace all activity notes (bulk, for cache init).

        Args:
            notes: Dict mapping activity name to notes text
        """
        ...


class ConcurrencyError(Exception):
    """Raised when a version conflict is detected during save."""

    pass


class EntityDeletedError(ConcurrencyError):
    """Raised when trying to save an entity that was deleted on the server."""

    pass
