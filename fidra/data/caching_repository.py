"""Caching repository wrappers for cloud backends.

Wraps cloud repositories with local SQLite cache for:
- Faster reads (no network round-trip)
- Offline capability (read from cache when disconnected)
- Optimistic updates (write locally first, sync in background)
"""

import logging
from typing import Optional, TYPE_CHECKING
from uuid import UUID

from fidra.data.repository import (
    ActivityNotesRepository,
    TransactionRepository,
    PlannedRepository,
    SheetRepository,
    AttachmentRepository,
    AuditRepository,
    CategoryRepository,
)
from fidra.domain.models import (
    Transaction,
    PlannedTemplate,
    Sheet,
    Attachment,
    AuditEntry,
)

if TYPE_CHECKING:
    from fidra.services.connection_state import ConnectionStateService
    from fidra.data.sync_queue import SyncQueue

logger = logging.getLogger(__name__)


class CachingTransactionRepository(TransactionRepository):
    """Transaction repository with local SQLite caching.

    Reads from local cache for fast access.
    Writes go to local cache first, then queued for cloud sync.
    """

    def __init__(
        self,
        cloud_repo: TransactionRepository,
        local_repo: TransactionRepository,
        sync_queue: Optional["SyncQueue"] = None,
        connection_state: Optional["ConnectionStateService"] = None,
    ):
        """Initialize caching repository.

        Args:
            cloud_repo: Cloud (PostgreSQL) repository
            local_repo: Local (SQLite) cache repository
            sync_queue: Optional queue for pending sync operations
            connection_state: Optional connection state service
        """
        self._cloud = cloud_repo
        self._local = local_repo
        self._sync_queue = sync_queue
        self._connection_state = connection_state
        self._cache_initialized = False

    async def initialize_cache(self) -> None:
        """Initialize local cache from cloud data.

        Call this once after connection is established.
        Uses refresh_from_cloud to also clean up stale local entities
        that were deleted on the server since the last session.
        """
        if self._cache_initialized:
            return

        logger.info("Initializing transaction cache from cloud...")
        try:
            refreshed = await self.refresh_from_cloud()
            self._cache_initialized = True
            logger.info(f"Transaction cache initialized ({refreshed} items refreshed)")
        except Exception as e:
            logger.error(f"Failed to initialize cache: {e}")
            raise

    async def get_all(self, sheet: Optional[str] = None) -> list[Transaction]:
        """Get all transactions from local cache."""
        return await self._local.get_all(sheet)

    async def get_by_id(self, id: UUID) -> Optional[Transaction]:
        """Get transaction by ID from local cache."""
        return await self._local.get_by_id(id)

    async def save(self, transaction: Transaction) -> Transaction:
        """Save transaction to local cache and queue for sync.

        Args:
            transaction: Transaction to save

        Returns:
            Saved transaction
        """
        # Save to local cache immediately
        print(f"[CACHE] Saving transaction {transaction.id} to local cache...")
        result = await self._local.save(transaction)
        print(f"[CACHE] Local save complete")

        # Queue for cloud sync
        if self._sync_queue:
            print(f"[CACHE] Queueing transaction {transaction.id} for sync...")
            await self._sync_queue.enqueue_save("transaction", transaction)
            print(f"[CACHE] Queued for sync")
        else:
            print(f"[CACHE] WARNING: No sync queue available!")

        return result

    async def delete(self, id: UUID) -> None:
        """Delete transaction from local cache and queue for sync."""
        print(f"[CACHE] Deleting transaction {id} from local cache...")
        # Get version before deleting for version-checked cloud delete
        version = await self._local.get_version(id) or 0
        # Delete from local cache
        await self._local.delete(id)
        print(f"[CACHE] Local delete complete")

        # Queue for cloud sync
        if self._sync_queue:
            print(f"[CACHE] Queueing delete for sync...")
            await self._sync_queue.enqueue_delete("transaction", id, version=version)
            print(f"[CACHE] Delete queued for sync")

    async def bulk_save(self, transactions: list[Transaction]) -> None:
        """Bulk save transactions to local cache and queue for sync."""
        await self._local.bulk_save(transactions)

        if self._sync_queue:
            for trans in transactions:
                await self._sync_queue.enqueue_save("transaction", trans)

    async def bulk_delete(self, ids: list[UUID]) -> None:
        """Bulk delete transactions from local cache and queue for sync."""
        # Capture versions before deleting for version-checked cloud deletes
        versions = {}
        if self._sync_queue:
            for id in ids:
                versions[id] = await self._local.get_version(id) or 0

        await self._local.bulk_delete(ids)

        if self._sync_queue:
            for id in ids:
                await self._sync_queue.enqueue_delete(
                    "transaction", id, version=versions.get(id, 0)
                )

    async def get_version(self, id: UUID) -> Optional[int]:
        """Get current version from local cache."""
        return await self._local.get_version(id)

    async def close(self) -> None:
        """Close both repositories."""
        await self._local.close()
        # Cloud repo closed separately via CloudConnection

    async def refresh_from_cloud(self) -> int:
        """Refresh local cache from cloud.

        Skips entities with pending local changes to avoid overwriting
        unsynced edits. Deletes local entities that no longer exist on server.

        Returns:
            Number of items refreshed
        """
        cloud_transactions = await self._cloud.get_all()
        cloud_ids = {t.id for t in cloud_transactions}
        refreshed = 0

        for trans in cloud_transactions:
            # Don't overwrite local edits that haven't synced yet
            if self._sync_queue:
                pending = await self._sync_queue.get_pending_for_entity(trans.id)
                if pending:
                    continue
            await self._local.save(trans, force=True)
            refreshed += 1

        # Remove local entities that were deleted on server
        local_transactions = await self._local.get_all()
        for local_trans in local_transactions:
            if local_trans.id not in cloud_ids:
                # Don't delete if there's a pending local change
                if self._sync_queue:
                    pending = await self._sync_queue.get_pending_for_entity(local_trans.id)
                    if pending:
                        continue
                await self._local.delete(local_trans.id)
                refreshed += 1

        return refreshed

    async def sync_to_cloud(self, transaction: Transaction) -> Transaction:
        """Sync a specific transaction to cloud (for sync service).

        Returns:
            Updated transaction from cloud (with new version)
        """
        return await self._cloud.save(transaction)

    async def delete_from_cloud(self, id: UUID) -> None:
        """Delete from cloud (for sync service)."""
        await self._cloud.delete(id)


class CachingPlannedRepository(PlannedRepository):
    """Planned template repository with local SQLite caching."""

    def __init__(
        self,
        cloud_repo: PlannedRepository,
        local_repo: PlannedRepository,
        sync_queue: Optional["SyncQueue"] = None,
        connection_state: Optional["ConnectionStateService"] = None,
    ):
        self._cloud = cloud_repo
        self._local = local_repo
        self._sync_queue = sync_queue
        self._connection_state = connection_state
        self._cache_initialized = False

    async def initialize_cache(self) -> None:
        """Initialize local cache from cloud data."""
        if self._cache_initialized:
            return

        logger.info("Initializing planned templates cache from cloud...")
        refreshed = await self.refresh_from_cloud()
        self._cache_initialized = True
        logger.info(f"Planned cache initialized ({refreshed} items refreshed)")

    async def get_all(self) -> list[PlannedTemplate]:
        return await self._local.get_all()

    async def get_by_id(self, id: UUID) -> Optional[PlannedTemplate]:
        return await self._local.get_by_id(id)

    async def save(self, template: PlannedTemplate) -> PlannedTemplate:
        result = await self._local.save(template)
        if self._sync_queue:
            await self._sync_queue.enqueue_save("planned_template", template)
        return result

    async def delete(self, id: UUID) -> None:
        version = 0
        if hasattr(self._local, 'get_version'):
            version = await self._local.get_version(id) or 0
        await self._local.delete(id)
        if self._sync_queue:
            await self._sync_queue.enqueue_delete("planned_template", id, version=version)

    async def get_version(self, id: UUID) -> Optional[int]:
        return await self._local.get_version(id)

    async def close(self) -> None:
        await self._local.close()

    async def refresh_from_cloud(self) -> int:
        cloud_templates = await self._cloud.get_all()
        cloud_ids = {t.id for t in cloud_templates}
        refreshed = 0

        for template in cloud_templates:
            if self._sync_queue:
                pending = await self._sync_queue.get_pending_for_entity(template.id)
                if pending:
                    continue
            await self._local.save(template)
            refreshed += 1

        # Remove local entities deleted on server
        local_templates = await self._local.get_all()
        for local_tmpl in local_templates:
            if local_tmpl.id not in cloud_ids:
                if self._sync_queue:
                    pending = await self._sync_queue.get_pending_for_entity(local_tmpl.id)
                    if pending:
                        continue
                await self._local.delete(local_tmpl.id)
                refreshed += 1

        return refreshed

    async def sync_to_cloud(self, template: PlannedTemplate) -> PlannedTemplate:
        return await self._cloud.save(template)

    async def delete_from_cloud(self, id: UUID) -> None:
        await self._cloud.delete(id)


class CachingSheetRepository(SheetRepository):
    """Sheet repository with local SQLite caching."""

    def __init__(
        self,
        cloud_repo: SheetRepository,
        local_repo: SheetRepository,
        sync_queue: Optional["SyncQueue"] = None,
        connection_state: Optional["ConnectionStateService"] = None,
    ):
        self._cloud = cloud_repo
        self._local = local_repo
        self._sync_queue = sync_queue
        self._connection_state = connection_state
        self._cache_initialized = False

    async def initialize_cache(self) -> None:
        """Initialize local cache from cloud data."""
        if self._cache_initialized:
            return

        logger.info("Initializing sheets cache from cloud...")
        refreshed = await self.refresh_from_cloud()
        self._cache_initialized = True
        logger.info(f"Sheets cache initialized ({refreshed} items refreshed)")

    async def get_all(self) -> list[Sheet]:
        return await self._local.get_all()

    async def get_by_id(self, id: UUID) -> Optional[Sheet]:
        return await self._local.get_by_id(id)

    async def get_by_name(self, name: str) -> Optional[Sheet]:
        return await self._local.get_by_name(name)

    async def create(self, name: str, **kwargs) -> Sheet:
        result = await self._local.create(name, **kwargs)
        if self._sync_queue:
            await self._sync_queue.enqueue_save("sheet", result)
        return result

    async def save(self, sheet: Sheet) -> Sheet:
        result = await self._local.save(sheet)
        if self._sync_queue:
            await self._sync_queue.enqueue_save("sheet", sheet)
        return result

    async def delete(self, id: UUID) -> None:
        await self._local.delete(id)
        if self._sync_queue:
            await self._sync_queue.enqueue_delete("sheet", id)

    async def close(self) -> None:
        await self._local.close()

    async def refresh_from_cloud(self) -> int:
        cloud_sheets = await self._cloud.get_all()
        cloud_ids = {s.id for s in cloud_sheets}
        refreshed = 0

        for sheet in cloud_sheets:
            if self._sync_queue:
                pending = await self._sync_queue.get_pending_for_entity(sheet.id)
                if pending:
                    continue
            await self._local.save(sheet)
            refreshed += 1

        # Remove local sheets deleted on server
        local_sheets = await self._local.get_all()
        for local_sheet in local_sheets:
            if local_sheet.id not in cloud_ids:
                if self._sync_queue:
                    pending = await self._sync_queue.get_pending_for_entity(local_sheet.id)
                    if pending:
                        continue
                await self._local.delete(local_sheet.id)
                refreshed += 1

        return refreshed

    async def sync_to_cloud(self, sheet: Sheet) -> Sheet:
        return await self._cloud.save(sheet)

    async def delete_from_cloud(self, id: UUID) -> None:
        await self._cloud.delete(id)


class CachingCategoryRepository(CategoryRepository):
    """Category repository with local SQLite caching."""

    def __init__(
        self,
        cloud_repo: CategoryRepository,
        local_repo: CategoryRepository,
        sync_queue: Optional["SyncQueue"] = None,
        connection_state: Optional["ConnectionStateService"] = None,
    ):
        self._cloud = cloud_repo
        self._local = local_repo
        self._sync_queue = sync_queue
        self._connection_state = connection_state
        self._cache_initialized = False

    async def initialize_cache(self) -> None:
        """Initialize local cache from cloud data."""
        if self._cache_initialized:
            return

        logger.info("Initializing categories cache from cloud...")
        income_cats = await self._cloud.get_all("income")
        expense_cats = await self._cloud.get_all("expense")
        await self._local.set_all("income", income_cats)
        await self._local.set_all("expense", expense_cats)
        self._cache_initialized = True
        logger.info(
            f"Categories cache initialized: {len(income_cats)} income, {len(expense_cats)} expense"
        )

    async def get_all(self, type: str) -> list[str]:
        return await self._local.get_all(type)

    async def add(self, type: str, name: str) -> None:
        await self._local.add(type, name)
        if self._sync_queue:
            await self._sync_queue.enqueue_category_add(name, type)

    async def remove(self, type: str, name: str) -> bool:
        result = await self._local.remove(type, name)
        if self._sync_queue:
            await self._sync_queue.enqueue_category_remove(name, type)
        return result

    async def set_all(self, type: str, names: list[str]) -> None:
        await self._local.set_all(type, names)
        if self._sync_queue:
            await self._sync_queue.enqueue_category_reorder(names, type)

    async def close(self) -> None:
        await self._local.close()

    def set_connection(self, conn) -> None:
        """Set connection for local repo."""
        self._local.set_connection(conn)

    async def refresh_from_cloud(self) -> int:
        # Don't overwrite local categories if there are pending category changes
        if self._sync_queue:
            has_pending = await self._sync_queue.has_pending_for_type("category")
            if has_pending:
                logger.debug("Skipping category refresh — pending local changes")
                return 0

        income_cats = await self._cloud.get_all("income")
        expense_cats = await self._cloud.get_all("expense")
        await self._local.set_all("income", income_cats)
        await self._local.set_all("expense", expense_cats)
        return len(income_cats) + len(expense_cats)


class CachingActivityNotesRepository(ActivityNotesRepository):
    """Activity notes repository with local SQLite caching."""

    def __init__(
        self,
        cloud_repo: ActivityNotesRepository,
        local_repo: ActivityNotesRepository,
        sync_queue: Optional["SyncQueue"] = None,
        connection_state: Optional["ConnectionStateService"] = None,
    ):
        self._cloud = cloud_repo
        self._local = local_repo
        self._sync_queue = sync_queue
        self._connection_state = connection_state
        self._cache_initialized = False

    async def initialize_cache(self) -> None:
        """Initialize local cache from cloud data."""
        if self._cache_initialized:
            return

        logger.info("Initializing activity notes cache from cloud...")
        cloud_notes = await self._cloud.get_all()
        await self._local.set_all(cloud_notes)
        self._cache_initialized = True
        logger.info(f"Activity notes cache initialized ({len(cloud_notes)} items)")

    async def get_all(self) -> dict[str, str]:
        return await self._local.get_all()

    async def save(self, activity: str, notes: str) -> None:
        await self._local.save(activity, notes)
        if self._sync_queue:
            await self._sync_queue.enqueue_activity_note_save(activity, notes)

    async def delete(self, activity: str) -> None:
        await self._local.delete(activity)
        if self._sync_queue:
            await self._sync_queue.enqueue_activity_note_delete(activity)

    async def set_all(self, notes: dict[str, str]) -> None:
        await self._local.set_all(notes)

    async def close(self) -> None:
        await self._local.close()

    def set_connection(self, conn) -> None:
        """Set connection for local repo."""
        self._local.set_connection(conn)

    async def refresh_from_cloud(self) -> int:
        if self._sync_queue:
            has_pending = await self._sync_queue.has_pending_for_type("activity_note")
            if has_pending:
                logger.debug("Skipping activity notes refresh — pending local changes")
                return 0

        cloud_notes = await self._cloud.get_all()
        await self._local.set_all(cloud_notes)
        return len(cloud_notes)
