"""Factory for creating repository instances."""

from pathlib import Path
from typing import Optional, Tuple, TYPE_CHECKING

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

if TYPE_CHECKING:
    from fidra.domain.settings import SupabaseSettings
    from fidra.data.supabase_connection import SupabaseConnection


async def create_repositories(
    backend: str,
    file_path: Optional[Path] = None,
    supabase_connection: Optional["SupabaseConnection"] = None,
) -> Tuple[
    TransactionRepository, PlannedRepository, SheetRepository,
    AuditRepository, AttachmentRepository,
]:
    """Factory function to create appropriate repositories.

    Args:
        backend: Backend type ("sqlite", "supabase", or "excel")
        file_path: Path to database/file (required for sqlite)
        supabase_connection: Connected SupabaseConnection (required for supabase)

    Returns:
        Tuple of (TransactionRepository, PlannedRepository, SheetRepository,
                  AuditRepository, AttachmentRepository)

    Raises:
        ValueError: If backend is unknown or required params missing
        DatabaseValidationError: If database file is not compatible

    Example:
        >>> # SQLite
        >>> trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo = await create_repositories(
        ...     "sqlite", Path("fidra.db")
        ... )
        >>> # Supabase
        >>> conn = SupabaseConnection(config)
        >>> await conn.connect()
        >>> repos = await create_repositories("supabase", supabase_connection=conn)
    """
    if backend == "sqlite":
        if not file_path:
            raise ValueError("file_path required for sqlite backend")

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

    elif backend == "supabase":
        if not supabase_connection:
            raise ValueError("supabase_connection required for supabase backend")

        from fidra.data.supabase_repo import (
            SupabaseAttachmentRepository,
            SupabaseAuditRepository,
            SupabasePlannedRepository,
            SupabaseSheetRepository,
            SupabaseTransactionRepository,
        )

        pool = supabase_connection.pool
        trans_repo = SupabaseTransactionRepository(pool)
        planned_repo = SupabasePlannedRepository(pool)
        sheet_repo = SupabaseSheetRepository(pool)
        audit_repo = SupabaseAuditRepository(pool)
        attachment_repo = SupabaseAttachmentRepository(pool)

        return trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo

    elif backend == "excel":
        # Excel adapter not yet implemented
        raise NotImplementedError("Excel backend not yet implemented")

    else:
        raise ValueError(f"Unknown backend: {backend}")
