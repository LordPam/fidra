"""Factory for creating repository instances."""

from pathlib import Path
from typing import Optional, Tuple, TYPE_CHECKING

from fidra.data.repository import (
    ActivityNotesRepository,
    AttachmentRepository,
    AuditRepository,
    CategoryRepository,
    PlannedRepository,
    SheetRepository,
    TransactionRepository,
)
from fidra.data.sqlite_repo import (
    SQLiteActivityNotesRepository,
    SQLiteAttachmentRepository,
    SQLiteAuditRepository,
    SQLiteCategoryRepository,
    SQLitePlannedRepository,
    SQLiteSheetRepository,
    SQLiteTransactionRepository,
)
from fidra.data.validation import DatabaseValidationError, validate_database

if TYPE_CHECKING:
    from fidra.data.cloud_connection import CloudConnection
    from fidra.data.sync_queue import SyncQueue
    from fidra.services.connection_state import ConnectionStateService


async def create_repositories(
    backend: str,
    file_path: Optional[Path] = None,
    cloud_connection: Optional["CloudConnection"] = None,
    enable_caching: bool = True,
    cache_dir: Optional[Path] = None,
    connection_state: Optional["ConnectionStateService"] = None,
) -> Tuple[
    TransactionRepository, PlannedRepository, SheetRepository,
    AuditRepository, AttachmentRepository, CategoryRepository,
    ActivityNotesRepository, Optional["SyncQueue"],
]:
    """Factory function to create appropriate repositories.

    Args:
        backend: Backend type ("sqlite" or "cloud")
        file_path: Path to database/file (required for sqlite)
        cloud_connection: Connected CloudConnection (required for cloud)
        enable_caching: Whether to enable local caching for cloud mode (default True)
        cache_dir: Directory for local cache database (defaults to user cache dir)
        connection_state: Connection state service for offline detection

    Returns:
        Tuple of (TransactionRepository, PlannedRepository, SheetRepository,
                  AuditRepository, AttachmentRepository, CategoryRepository,
                  ActivityNotesRepository, SyncQueue or None)

    Raises:
        ValueError: If backend is unknown or required params missing
        DatabaseValidationError: If database file is not compatible

    Example:
        >>> # SQLite (no sync queue)
        >>> repos = await create_repositories("sqlite", Path("fidra.db"))
        >>> trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo, category_repo, notes_repo, _ = repos
        >>> # Cloud PostgreSQL with caching
        >>> conn = CloudConnection(server_config)
        >>> await conn.connect()
        >>> repos = await create_repositories("cloud", cloud_connection=conn)
        >>> trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo, category_repo, notes_repo, sync_queue = repos
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
        category_repo = SQLiteCategoryRepository(file_path)
        category_repo.set_connection(trans_repo._conn)
        activity_notes_repo = SQLiteActivityNotesRepository(file_path)
        activity_notes_repo.set_connection(trans_repo._conn)

        return trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo, category_repo, activity_notes_repo, None

    elif backend == "cloud":
        if not cloud_connection:
            raise ValueError("cloud_connection required for cloud backend")

        from fidra.data.postgres_repo import (
            PostgresActivityNotesRepository,
            PostgresAttachmentRepository,
            PostgresAuditRepository,
            PostgresCategoryRepository,
            PostgresPlannedRepository,
            PostgresSheetRepository,
            PostgresTransactionRepository,
        )

        # Pass CloudConnection (not pool) to repos so they always get current pool
        # This is critical for reconnection - when pool changes, repos use the new one
        cloud_trans_repo = PostgresTransactionRepository(cloud_connection)
        cloud_planned_repo = PostgresPlannedRepository(cloud_connection)
        cloud_sheet_repo = PostgresSheetRepository(cloud_connection)
        cloud_audit_repo = PostgresAuditRepository(cloud_connection)
        cloud_attachment_repo = PostgresAttachmentRepository(cloud_connection)
        cloud_category_repo = PostgresCategoryRepository(cloud_connection)
        cloud_activity_notes_repo = PostgresActivityNotesRepository(cloud_connection)

        # Ensure tables exist
        await cloud_category_repo.ensure_table()
        await cloud_activity_notes_repo.ensure_table()

        if not enable_caching:
            # Return cloud repos directly without caching
            return (
                cloud_trans_repo, cloud_planned_repo, cloud_sheet_repo,
                cloud_audit_repo, cloud_attachment_repo, cloud_category_repo,
                cloud_activity_notes_repo, None
            )

        # Set up local cache directory
        if cache_dir is None:
            import platformdirs
            cache_dir = Path(platformdirs.user_cache_dir("Fidra", "Fidra"))
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Create local SQLite cache repositories
        cache_db_path = cache_dir / "cloud_cache.db"
        sync_queue_path = cache_dir / "sync_queue.db"

        # Initialize sync queue first to check for pending items
        from fidra.data.sync_queue import SyncQueue
        sync_queue = SyncQueue(sync_queue_path)
        await sync_queue.initialize()

        # Check if there are pending changes to sync
        pending_count = await sync_queue.get_pending_count()
        has_pending_changes = pending_count > 0

        import logging
        logger = logging.getLogger(__name__)

        if has_pending_changes:
            # Keep the cache - it has unsynced local changes
            logger.info(f"Found {pending_count} pending changes - preserving local cache")
        elif cache_db_path.exists():
            # No pending changes - safe to start fresh
            logger.info("No pending changes - clearing local cache for fresh sync...")
            cache_db_path.unlink()

        local_trans_repo = SQLiteTransactionRepository(cache_db_path)
        await local_trans_repo.connect()

        # Share connection for other local repositories
        local_planned_repo = SQLitePlannedRepository(local_trans_repo._conn)
        local_sheet_repo = SQLiteSheetRepository(local_trans_repo._conn)
        local_category_repo = SQLiteCategoryRepository(cache_db_path)
        local_category_repo.set_connection(local_trans_repo._conn)
        local_activity_notes_repo = SQLiteActivityNotesRepository(cache_db_path)
        local_activity_notes_repo.set_connection(local_trans_repo._conn)

        # Create caching repository wrappers
        from fidra.data.caching_repository import (
            CachingActivityNotesRepository,
            CachingTransactionRepository,
            CachingPlannedRepository,
            CachingSheetRepository,
            CachingCategoryRepository,
        )

        trans_repo = CachingTransactionRepository(
            cloud_trans_repo, local_trans_repo, sync_queue, connection_state
        )
        planned_repo = CachingPlannedRepository(
            cloud_planned_repo, local_planned_repo, sync_queue, connection_state
        )
        sheet_repo = CachingSheetRepository(
            cloud_sheet_repo, local_sheet_repo, sync_queue, connection_state
        )
        category_repo = CachingCategoryRepository(
            cloud_category_repo, local_category_repo, sync_queue, connection_state
        )
        activity_notes_repo = CachingActivityNotesRepository(
            cloud_activity_notes_repo, local_activity_notes_repo, sync_queue, connection_state
        )

        # Initialize caches from cloud data
        # Skip if we have pending changes - we'll sync first then refresh
        if not has_pending_changes:
            await trans_repo.initialize_cache()
            await planned_repo.initialize_cache()
            await sheet_repo.initialize_cache()
            await category_repo.initialize_cache()
            await activity_notes_repo.initialize_cache()
        else:
            # Mark caches as initialized so they read from local
            trans_repo._cache_initialized = True
            planned_repo._cache_initialized = True
            sheet_repo._cache_initialized = True
            category_repo._cache_initialized = True
            activity_notes_repo._cache_initialized = True
            logger.info("Using existing cache - will sync pending changes before refreshing")

        # Audit and attachment repos don't need local caching
        # (audit is write-only, attachments are large files)
        audit_repo = cloud_audit_repo
        attachment_repo = cloud_attachment_repo

        return (
            trans_repo, planned_repo, sheet_repo,
            audit_repo, attachment_repo, category_repo,
            activity_notes_repo, sync_queue
        )

    else:
        raise ValueError(f"Unknown backend: {backend}")
