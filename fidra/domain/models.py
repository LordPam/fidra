"""Domain models for Fidra financial ledger application.

All models are immutable (frozen dataclasses) to ensure data consistency and
enable safe concurrent access.
"""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class TransactionType(Enum):
    """Type of financial transaction."""

    INCOME = "income"
    EXPENSE = "expense"


class ApprovalStatus(Enum):
    """Approval status for transactions."""

    AUTO = "--"  # Auto-approved (income)
    PENDING = "pending"  # Awaiting approval
    APPROVED = "approved"  # Approved
    REJECTED = "rejected"  # Rejected
    PLANNED = "planned"  # Generated from template


class Frequency(Enum):
    """Recurrence frequency for planned transactions."""

    ONCE = "once"  # One-time, no recurrence (default)
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass(frozen=True, slots=True)
class Transaction:
    """Immutable transaction record.

    Represents a single financial transaction with full audit trail.
    Immutability ensures thread safety and enables safe undo/redo.
    """

    id: UUID
    date: date
    description: str
    amount: Decimal
    type: TransactionType
    status: ApprovalStatus
    sheet: str
    category: Optional[str] = None
    party: Optional[str] = None
    reference: Optional[str] = None  # Bank statement reference for matching
    activity: Optional[str] = None  # Activity/project tag for grouping related transactions
    notes: Optional[str] = None
    is_one_time_planned: Optional[bool] = None  # True for ONCE planned instances
    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: Optional[datetime] = None
    modified_by: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate transaction data."""
        if self.amount <= 0:
            raise ValueError("Amount must be positive")

        if not self.description.strip():
            raise ValueError("Description cannot be empty")

        if not self.sheet.strip():
            raise ValueError("Sheet cannot be empty")

    def with_updates(self, **changes: any) -> "Transaction":
        """Create new instance with updated fields.

        Args:
            **changes: Field names and new values

        Returns:
            New Transaction instance with updates applied

        Example:
            >>> trans = Transaction.create(...)
            >>> updated = trans.with_updates(amount=Decimal("200.00"))
        """
        current = asdict(self)
        current.update(changes)
        current["version"] = self.version + 1
        current["modified_at"] = datetime.now()
        return Transaction(**current)

    @classmethod
    def create(
        cls,
        date: date,
        description: str,
        amount: Decimal,
        type: TransactionType,
        sheet: str,
        **kwargs: any,
    ) -> "Transaction":
        """Factory method with sensible defaults.

        Income transactions are automatically approved (status = AUTO).
        Expense transactions default to PENDING status.

        Args:
            date: Transaction date
            description: Description of transaction
            amount: Transaction amount (must be positive)
            type: TransactionType (INCOME or EXPENSE)
            sheet: Sheet/account name
            **kwargs: Optional fields (category, party, notes, status, etc.)

        Returns:
            New Transaction instance

        Example:
            >>> trans = Transaction.create(
            ...     date=date(2024, 1, 15),
            ...     description="Coffee",
            ...     amount=Decimal("4.50"),
            ...     type=TransactionType.EXPENSE,
            ...     sheet="Main",
            ...     category="Food"
            ... )
        """
        status = kwargs.pop("status", None)
        if status is None:
            status = (
                ApprovalStatus.AUTO
                if type == TransactionType.INCOME
                else ApprovalStatus.PENDING
            )

        return cls(
            id=uuid4(),
            date=date,
            description=description,
            amount=amount,
            type=type,
            status=status,
            sheet=sheet,
            **kwargs,
        )


@dataclass(frozen=True, slots=True)
class PlannedTemplate:
    """Template for future expected transactions (one-time or recurring).

    Planned templates define transactions that are expected to occur in the
    future. They can be one-time (ONCE frequency) or recurring.

    For recurring templates, instances are generated up to a specified horizon
    date and can be individually skipped or marked as fulfilled.
    """

    id: UUID
    start_date: date
    description: str
    amount: Decimal
    type: TransactionType
    target_sheet: str
    frequency: Frequency = Frequency.ONCE  # Default to one-time
    category: Optional[str] = None
    party: Optional[str] = None
    activity: Optional[str] = None  # Activity/project tag for grouping
    end_date: Optional[date] = None  # For recurring: when to stop
    occurrence_count: Optional[int] = None  # Alternative: stop after N occurrences
    skipped_dates: tuple[date, ...] = ()  # Instances to exclude from projections
    fulfilled_dates: tuple[date, ...] = ()  # Instances converted to actual transactions
    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Validate planned template data."""
        if self.amount <= 0:
            raise ValueError("Amount must be positive")

        if not self.description.strip():
            raise ValueError("Description cannot be empty")

        if not self.target_sheet.strip():
            raise ValueError("Target sheet cannot be empty")

        # Validate end conditions: end_date and occurrence_count are mutually exclusive
        if self.frequency != Frequency.ONCE:
            if self.end_date and self.occurrence_count:
                raise ValueError("Cannot specify both end_date and occurrence_count")

    @property
    def is_recurring(self) -> bool:
        """Check if this is a recurring template."""
        return self.frequency != Frequency.ONCE

    def is_skipped(self, instance_date: date) -> bool:
        """Check if a specific instance is skipped."""
        return instance_date in self.skipped_dates

    def is_fulfilled(self, instance_date: date) -> bool:
        """Check if a specific instance has been converted to actual."""
        return instance_date in self.fulfilled_dates

    def with_updates(self, **changes: any) -> "PlannedTemplate":
        """Create new instance with updated fields."""
        current = asdict(self)
        current.update(changes)
        current["version"] = self.version + 1
        return PlannedTemplate(**current)

    def skip_instance(self, instance_date: date) -> "PlannedTemplate":
        """Mark an instance as skipped."""
        if instance_date in self.skipped_dates:
            return self
        return self.with_updates(skipped_dates=self.skipped_dates + (instance_date,))

    def unskip_instance(self, instance_date: date) -> "PlannedTemplate":
        """Remove skip marking from an instance."""
        if instance_date not in self.skipped_dates:
            return self
        return self.with_updates(
            skipped_dates=tuple(d for d in self.skipped_dates if d != instance_date)
        )

    def mark_fulfilled(self, instance_date: date) -> "PlannedTemplate":
        """Mark an instance as converted to actual transaction."""
        if instance_date in self.fulfilled_dates:
            return self
        return self.with_updates(fulfilled_dates=self.fulfilled_dates + (instance_date,))

    @classmethod
    def create(
        cls,
        start_date: date,
        description: str,
        amount: Decimal,
        type: TransactionType,
        target_sheet: str,
        frequency: Frequency = Frequency.ONCE,
        **kwargs: any,
    ) -> "PlannedTemplate":
        """Factory method for creating planned templates.

        Args:
            start_date: Date of first occurrence
            description: Transaction description
            amount: Transaction amount
            type: TransactionType (INCOME or EXPENSE)
            target_sheet: Target sheet/account
            frequency: Recurrence frequency (default: ONCE)
            **kwargs: Optional fields (category, party, end_date, occurrence_count)

        Returns:
            New PlannedTemplate instance
        """
        return cls(
            id=uuid4(),
            start_date=start_date,
            description=description,
            amount=amount,
            type=type,
            target_sheet=target_sheet,
            frequency=frequency,
            **kwargs,
        )


@dataclass(frozen=True, slots=True)
class Sheet:
    """A sheet/account for organizing transactions.

    Sheets represent different accounts, funds, or transaction categories.
    Special sheets can be marked as virtual (e.g., "All Transactions") or
    planned (e.g., "Planned_Transactions").
    """

    id: UUID
    name: str
    is_virtual: bool = False  # True for "All Transactions"
    is_planned: bool = False  # True for "Planned_Transactions"
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Validate sheet data."""
        if not self.name.strip():
            raise ValueError("Sheet name cannot be empty")

    @classmethod
    def create(cls, name: str, **kwargs: any) -> "Sheet":
        """Factory method for creating sheets.

        Args:
            name: Sheet name
            **kwargs: Optional fields (is_virtual, is_planned)

        Returns:
            New Sheet instance
        """
        return cls(id=uuid4(), name=name, **kwargs)

    def with_updates(self, **changes: any) -> "Sheet":
        """Create a new Sheet with updated fields.

        Args:
            **changes: Fields to update

        Returns:
            New Sheet with updates applied
        """
        from dataclasses import asdict
        current = asdict(self)
        current.update(changes)
        return Sheet(**current)


@dataclass(frozen=True, slots=True)
class Category:
    """Transaction category for income or expenses.

    Categories help organize transactions and generate reports.
    Each category is associated with either income or expense type.
    """

    id: UUID
    name: str
    type: TransactionType  # Income or expense category
    color: Optional[str] = None  # Optional hex color for UI

    def __post_init__(self) -> None:
        """Validate category data."""
        if not self.name.strip():
            raise ValueError("Category name cannot be empty")

        # Validate color format if provided
        if self.color:
            if not self.color.startswith("#") or len(self.color) != 7:
                raise ValueError("Color must be in hex format (#RRGGBB)")

    @classmethod
    def create(
        cls, name: str, type: TransactionType, color: Optional[str] = None
    ) -> "Category":
        """Factory method for creating categories.

        Args:
            name: Category name
            type: TransactionType (INCOME or EXPENSE)
            color: Optional hex color (#RRGGBB)

        Returns:
            New Category instance
        """
        return cls(id=uuid4(), name=name, type=type, color=color)


@dataclass(frozen=True, slots=True)
class Attachment:
    """A file attachment linked to a transaction.

    Stores metadata about an attached file (receipt, invoice, etc.).
    The actual file is stored in an attachments directory alongside the database.
    """

    id: UUID
    transaction_id: UUID
    filename: str  # Original filename
    stored_name: str  # Name in storage directory (UUID-based to avoid conflicts)
    mime_type: Optional[str] = None
    file_size: int = 0  # Bytes
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        transaction_id: UUID,
        filename: str,
        stored_name: str,
        mime_type: Optional[str] = None,
        file_size: int = 0,
    ) -> "Attachment":
        """Factory method for creating attachments."""
        return cls(
            id=uuid4(),
            transaction_id=transaction_id,
            filename=filename,
            stored_name=stored_name,
            mime_type=mime_type,
            file_size=file_size,
        )


class AuditAction(Enum):
    """Type of audit log action."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Immutable audit log entry recording a change.

    Tracks who changed what, when, and provides a summary of the change.
    """

    id: UUID
    timestamp: datetime
    action: AuditAction
    entity_type: str  # "transaction", "planned_template", "sheet"
    entity_id: UUID
    user: str
    summary: str  # Human-readable description of the change
    details: Optional[str] = None  # JSON with old/new values

    @classmethod
    def create(
        cls,
        action: AuditAction,
        entity_type: str,
        entity_id: UUID,
        user: str,
        summary: str,
        details: Optional[str] = None,
    ) -> "AuditEntry":
        """Factory method for creating audit entries."""
        return cls(
            id=uuid4(),
            timestamp=datetime.now(),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user=user,
            summary=summary,
            details=details,
        )


@dataclass(frozen=True, slots=True)
class BackupMetadata:
    """Metadata about a backup.

    Stored as metadata.json within each backup folder.
    """

    id: UUID
    created_at: datetime
    db_name: str
    db_size: int  # Bytes
    attachments_count: int
    attachments_size: int  # Bytes
    trigger: str  # "manual", "auto_close", "pre_restore"
    fidra_version: str

    @classmethod
    def create(
        cls,
        db_name: str,
        db_size: int,
        attachments_count: int,
        attachments_size: int,
        trigger: str,
        fidra_version: str,
    ) -> "BackupMetadata":
        """Factory method for creating backup metadata."""
        return cls(
            id=uuid4(),
            created_at=datetime.now(),
            db_name=db_name,
            db_size=db_size,
            attachments_count=attachments_count,
            attachments_size=attachments_size,
            trigger=trigger,
            fidra_version=fidra_version,
        )
