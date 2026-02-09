"""Factory for creating repository instances."""

from pathlib import Path
from typing import Tuple

from fidra.data.repository import (
    AttachmentRepository,
    AuditRepository,
    PlannedRepository,
    SheetRepository,
    TransactionRepository,
)
from fidra.data.sqlite_repo import (
    SQLiteAttachmentRepository,
    SQLiteAuditRepository,
    SQLitePlannedRepository,
    SQLiteSheetRepository,
    SQLiteTransactionRepository,
)
from fidra.data.validation import DatabaseValidationError, validate_database


async def create_repositories(
    backend: str, file_path: Path
) -> Tuple[
    TransactionRepository, PlannedRepository, SheetRepository,
    AuditRepository, AttachmentRepository,
]:
    """Factory function to create appropriate repositories.

    Args:
        backend: Backend type ("sqlite" or "excel")
        file_path: Path to database/file

    Returns:
        Tuple of (TransactionRepository, PlannedRepository, SheetRepository,
                  AuditRepository, AttachmentRepository)

    Raises:
        ValueError: If backend is unknown
        DatabaseValidationError: If database file is not compatible

    Example:
        >>> trans_repo, planned_repo, sheet_repo, audit_repo = await create_repositories(
        ...     "sqlite", Path("fidra.db")
        ... )
    """
    if backend == "sqlite":
        # Validate database before connecting
        validate_database(file_path)
        trans_repo = SQLiteTransactionRepository(file_path)
        await trans_repo.connect()

        # Share connection for other repositories
        planned_repo = SQLitePlannedRepository(trans_repo._conn)
        sheet_repo = SQLiteSheetRepository(trans_repo._conn)
        audit_repo = SQLiteAuditRepository(trans_repo._conn)
        attachment_repo = SQLiteAttachmentRepository(trans_repo._conn)

        return trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo

    elif backend == "excel":
        # Excel adapter not yet implemented
        raise NotImplementedError("Excel backend not yet implemented")

    else:
        raise ValueError(f"Unknown backend: {backend}")
