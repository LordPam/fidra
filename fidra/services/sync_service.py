"""Background sync service for cloud synchronization.

Processes pending changes from the sync queue and syncs them to the cloud.
Handles conflicts, retries, and offline/online transitions.
"""

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Optional, TYPE_CHECKING
from uuid import UUID

from PySide6.QtCore import QObject, QTimer, Signal, Slot
import qasync

from fidra.data.sync_queue import PendingChange, SyncOperation, SyncStatus
from fidra.data.resilience import classify_error, ErrorCategory
from fidra.data.repository import EntityDeletedError
from fidra.domain.models import Transaction, PlannedTemplate, Sheet

if TYPE_CHECKING:
    from fidra.data.sync_queue import SyncQueue
    from fidra.data.caching_repository import (
        CachingActivityNotesRepository,
        CachingTransactionRepository,
        CachingPlannedRepository,
        CachingSheetRepository,
        CachingCategoryRepository,
    )
    from fidra.services.connection_state import ConnectionStateService, ConnectionStatus

logger = logging.getLogger(__name__)


class ConflictStrategy(Enum):
    """Strategy for handling sync conflicts."""

    LAST_WRITE_WINS = "last_write_wins"  # Most recent change wins
    SERVER_WINS = "server_wins"  # Server version always wins
    CLIENT_WINS = "client_wins"  # Local version always wins
    ASK_USER = "ask_user"  # Prompt user to choose


class SyncService(QObject):
    """Background service for syncing changes to the cloud.

    Runs periodically when connected and processes pending changes.
    Handles conflicts according to configured strategy.

    Signals:
        sync_started: Emitted when sync begins
        sync_completed(int): Emitted when sync completes (count of synced changes)
        sync_failed(str): Emitted when sync fails (error message)
        pending_count_changed(int): Emitted when pending count changes
        conflict_detected(UUID, object, object): Emitted for user-resolved conflicts
    """

    sync_started = Signal()
    sync_completed = Signal(int)
    sync_failed = Signal(str)
    pending_count_changed = Signal(int)
    conflict_detected = Signal(object, object, object)  # change_id, local, server
    _trigger_sync = Signal()  # Internal signal to trigger async sync from timer

    def __init__(
        self,
        sync_queue: "SyncQueue",
        transaction_repo: "CachingTransactionRepository",
        planned_repo: "CachingPlannedRepository",
        sheet_repo: "CachingSheetRepository",
        category_repo: "CachingCategoryRepository",
        connection_state: "ConnectionStateService",
        activity_notes_repo: Optional["CachingActivityNotesRepository"] = None,
        conflict_strategy: ConflictStrategy = ConflictStrategy.LAST_WRITE_WINS,
        sync_interval_ms: int = 30000,  # 30s safety net (event-driven handles fast path)
        parent: Optional[QObject] = None,
    ):
        """Initialize sync service.

        Args:
            sync_queue: Queue of pending changes
            transaction_repo: Caching transaction repository
            planned_repo: Caching planned repository
            sheet_repo: Caching sheet repository
            category_repo: Caching category repository
            connection_state: Connection state service
            activity_notes_repo: Caching activity notes repository
            conflict_strategy: How to handle conflicts
            sync_interval_ms: Interval between sync attempts (ms)
            parent: Qt parent
        """
        super().__init__(parent)
        self._queue = sync_queue
        self._transaction_repo = transaction_repo
        self._planned_repo = planned_repo
        self._sheet_repo = sheet_repo
        self._category_repo = category_repo
        self._activity_notes_repo = activity_notes_repo
        self._connection_state = connection_state
        self._conflict_strategy = conflict_strategy
        self._sync_interval = sync_interval_ms

        self._is_syncing = False
        self._last_pending_count = 0
        self._running = False
        self._sync_timer: Optional[QTimer] = None
        self._loop_count = 0
        self._max_retries = 10  # After this many transient failures, escalate to conflict

        # Debounce timer for event-driven sync (triggered by queue changes)
        self._push_debounce = QTimer(self)
        self._push_debounce.setSingleShot(True)
        self._push_debounce.setInterval(1000)  # 1 second debounce
        self._push_debounce.timeout.connect(self._on_push_debounce)

    def start(self) -> None:
        """Start the background sync service using QTimer."""
        if self._running:
            return

        self._running = True
        self._loop_count = 0

        # Connect internal signal to async handler
        self._trigger_sync.connect(self._handle_sync_trigger)

        # Safety-net timer: periodic sync in case event-driven triggers are missed
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._on_sync_timer)
        self._sync_timer.start(self._sync_interval)

        # Register for event-driven sync: queue notifies us immediately on changes
        self._queue.on_change = self._on_queue_changed

        print(f"[SYNC] Service started (interval: {self._sync_interval}ms)")
        logger.info(f"Sync service started (interval: {self._sync_interval}ms)")

    def stop(self) -> None:
        """Stop the background sync service."""
        self._running = False

        # Stop event-driven push debounce
        self._push_debounce.stop()
        self._queue.on_change = None

        if self._sync_timer:
            self._sync_timer.stop()
            self._sync_timer = None
        # Disconnect signal to prevent any pending triggers
        try:
            self._trigger_sync.disconnect(self._handle_sync_trigger)
        except (TypeError, RuntimeError):
            pass  # Already disconnected or not connected

        # Process any pending events so queued signal deliveries are
        # consumed while _running is False (prevents orphaned coroutines
        # during shutdown).
        from PySide6.QtCore import QCoreApplication
        app = QCoreApplication.instance()
        if app:
            app.processEvents()

        logger.info("Sync service stopped")

    async def stop_async(self) -> None:
        """Stop the background sync service and wait for cleanup."""
        self.stop()

    def _on_queue_changed(self) -> None:
        """Called by SyncQueue when a change is enqueued.

        Restarts the debounce timer so that rapid changes are batched
        into a single sync attempt ~1s after the last change.
        """
        if not self._running:
            return
        self._push_debounce.start()  # (re)starts the 1s single-shot timer

    def _on_push_debounce(self) -> None:
        """Debounce timer fired - trigger an immediate sync."""
        if not self._running:
            return
        if self._connection_state.is_connected and not self._is_syncing:
            self._trigger_sync.emit()

    def _on_sync_timer(self) -> None:
        """Handle sync timer tick - emit signal to trigger async sync."""
        if not self._running:
            return

        self._loop_count += 1
        is_connected = self._connection_state.is_connected

        if is_connected and not self._is_syncing:
            # Emit signal to trigger async sync via qasync.asyncSlot
            self._trigger_sync.emit()

    @qasync.asyncSlot()
    async def _handle_sync_trigger(self) -> None:
        """Handle sync trigger signal - runs async sync."""
        # Early exit if stopped or event loop is closing
        if not self._running:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed() or not loop.is_running():
                return
        except RuntimeError:
            return  # No event loop available
        try:
            await self.sync_now()
        except RuntimeError as e:
            if "Cannot enter into task" in str(e):
                logger.debug("Sync: skipping due to qasync re-entrancy")
            else:
                print(f"[SYNC] Error: {e}")
                logger.error(f"Sync error: {e}")
        except Exception as e:
            print(f"[SYNC] Error: {e}")
            logger.error(f"Sync error: {e}")

    async def sync_now(self) -> int:
        """Perform sync immediately.

        Returns:
            Number of changes synced
        """
        # Early exit if service is stopped
        if not self._running:
            return 0

        if self._is_syncing:
            logger.debug("Skipping sync - already syncing")
            return 0

        if not self._connection_state.is_connected:
            logger.debug(f"Skipping sync - not connected (status: {self._connection_state.status.value})")
            return 0

        self._is_syncing = True
        self.sync_started.emit()

        try:
            synced_count = await self._process_pending_changes()
            if synced_count > 0:
                print(f"[SYNC] Synced {synced_count} changes")
            self.sync_completed.emit(synced_count)
            return synced_count
        except Exception as e:
            print(f"[SYNC] Failed: {e}")
            logger.error(f"Sync failed: {e}")
            self.sync_failed.emit(str(e))
            return 0
        finally:
            self._is_syncing = False
            await self._update_pending_count()

    async def _process_pending_changes(self) -> int:
        """Process all pending changes in the queue.

        Stops processing on the first transient (network) error to avoid
        burning through retry counts on all pending items when the connection
        is down. Conflicts and permanent errors only affect the single item.

        Returns:
            Number of successfully synced changes
        """
        pending = await self._queue.get_pending()
        if not pending:
            return 0

        print(f"[SYNC] Processing {len(pending)} pending changes...")
        synced = 0
        for change in pending:
            try:
                await self._queue.mark_processing(change.id)
                await self._sync_change(change)
                await self._queue.dequeue(change.id)
                synced += 1
            except Exception as e:
                await self._handle_sync_error(change, e)
                # Stop processing remaining items on transient errors (likely
                # network down). No point burning retry counts on every item.
                category = classify_error(e)
                if category == ErrorCategory.TRANSIENT:
                    logger.info("Stopping sync batch — transient error, will retry next cycle")
                    break

        logger.info(f"Synced {synced}/{len(pending)} changes")
        return synced

    async def _sync_change(self, change: PendingChange) -> None:
        """Sync a single change to the cloud.

        Args:
            change: The change to sync
        """
        logger.debug(f"Syncing {change.operation.value} for {change.entity_type} {change.entity_id}")

        if change.entity_type == "transaction":
            await self._sync_transaction(change)
        elif change.entity_type == "planned_template":
            await self._sync_planned(change)
        elif change.entity_type == "sheet":
            await self._sync_sheet(change)
        elif change.entity_type == "category":
            await self._sync_category(change)
        elif change.entity_type == "activity_note":
            await self._sync_activity_note(change)
        else:
            logger.warning(f"Unknown entity type: {change.entity_type}")

    async def _sync_transaction(self, change: PendingChange) -> None:
        """Sync a transaction change."""
        if change.operation == SyncOperation.DELETE:
            if change.local_version > 0:
                await self._transaction_repo._cloud.delete_versioned(
                    change.entity_id, change.local_version
                )
            else:
                await self._transaction_repo.delete_from_cloud(change.entity_id)
        else:
            # Create or update
            data = json.loads(change.payload)
            transaction = self._deserialize_transaction(data)
            result = await self._transaction_repo.sync_to_cloud(transaction)
            # Keep local cache in sync with cloud response (has updated version/timestamps)
            await self._transaction_repo._local.save(result, force=True)

    async def _sync_planned(self, change: PendingChange) -> None:
        """Sync a planned template change."""
        if change.operation == SyncOperation.DELETE:
            if change.local_version > 0:
                await self._planned_repo._cloud.delete_versioned(
                    change.entity_id, change.local_version
                )
            else:
                await self._planned_repo.delete_from_cloud(change.entity_id)
        else:
            data = json.loads(change.payload)
            template = self._deserialize_planned(data)
            result = await self._planned_repo.sync_to_cloud(template)
            await self._planned_repo._local.save(result)

    async def _sync_sheet(self, change: PendingChange) -> None:
        """Sync a sheet change."""
        if change.operation == SyncOperation.DELETE:
            await self._sheet_repo.delete_from_cloud(change.entity_id)
        else:
            data = json.loads(change.payload)
            sheet = self._deserialize_sheet(data)
            result = await self._sheet_repo.sync_to_cloud(sheet)
            await self._sheet_repo._local.save(result)

    async def _sync_category(self, change: PendingChange) -> None:
        """Sync a category change.

        For add/remove: checks if the operation is still needed (idempotent).
        For reorder: fetches server list and merges any new categories that
        were added on another device but aren't in our reordered list.
        """
        data = json.loads(change.payload)
        action = data.get("action")
        name = data.get("name")
        type_ = data.get("type")

        if action == "add":
            # Idempotent — cloud add uses ON CONFLICT DO NOTHING
            await self._category_repo._cloud.add(type_, name)
        elif action == "remove":
            # Idempotent — removing a non-existent category is a no-op
            await self._category_repo._cloud.remove(type_, name)
        elif action == "reorder":
            names = data.get("names", [])
            # Merge: keep any server-side categories that we don't know about
            server_names = await self._category_repo._cloud.get_all(type_)
            local_set = set(names)
            # Append any server categories not in our list (added on another device)
            for sn in server_names:
                if sn not in local_set:
                    names.append(sn)
                    logger.info(f"Category merge: keeping server-added '{sn}' ({type_})")
            await self._category_repo._cloud.set_all(type_, names)
            # Update local cache to match merged result
            await self._category_repo._local.set_all(type_, names)

    async def _sync_activity_note(self, change: PendingChange) -> None:
        """Sync an activity note change.

        Idempotent: save upserts, delete of non-existent row is a no-op.
        """
        if not self._activity_notes_repo:
            logger.warning("Activity notes repo not available for sync")
            return

        data = json.loads(change.payload)
        action = data.get("action")
        activity = data.get("activity")

        if action == "save":
            notes = data.get("notes", "")
            await self._activity_notes_repo._cloud.save(activity, notes)
        elif action == "delete":
            await self._activity_notes_repo._cloud.delete(activity)

    async def _handle_sync_error(self, change: PendingChange, error: Exception) -> None:
        """Handle an error during sync.

        Args:
            change: The change that failed
            error: The exception
        """
        # Entity was deleted on server — accept the deletion locally
        if isinstance(error, EntityDeletedError):
            logger.info(f"Entity {change.entity_id} deleted on server, removing locally")
            await self._queue.dequeue(change.id)
            # Delete from local cache to match server state
            if change.entity_type == "transaction":
                await self._transaction_repo._local.delete(change.entity_id)
            elif change.entity_type == "planned_template":
                await self._planned_repo._local.delete(change.entity_id)
            elif change.entity_type == "sheet":
                await self._sheet_repo._local.delete(change.entity_id)
            return

        category = classify_error(error)

        if category == ErrorCategory.CONFLICT:
            await self._handle_conflict(change, error)
        elif category == ErrorCategory.TRANSIENT:
            # Check if we've exceeded retry limit
            if change.retry_count >= self._max_retries:
                await self._queue.mark_conflict(
                    change.id,
                    f"Max retries ({self._max_retries}) exceeded: {error}",
                )
                logger.error(
                    f"Change {change.entity_id} exceeded max retries, escalated to conflict"
                )
                return
            # Transient error (likely network) - report to connection state and retry later
            await self._queue.mark_failed(change.id, str(error))
            # Notify connection state service of potential network issue
            # Defer via QTimer to avoid Qt/GC lifecycle issues during exception handling
            if hasattr(self._connection_state, 'report_network_error'):
                QTimer.singleShot(0, self._connection_state.report_network_error)
        else:
            # Permanent error - mark as conflict for user review
            await self._queue.mark_conflict(change.id, str(error))
            logger.error(f"Permanent sync error for {change.entity_id}: {error}")

    async def _handle_conflict(self, change: PendingChange, error: Exception) -> None:
        """Handle a version conflict.

        Args:
            change: The conflicting change
            error: The conflict error
        """
        logger.warning(f"Conflict detected for {change.entity_type} {change.entity_id}")

        # Check for phantom conflict (identical content, only version differs)
        server_entity = await self._fetch_server_entity(change)
        if server_entity and self._is_same_content(change, server_entity):
            logger.info(f"Phantom conflict for {change.entity_id} — content identical, auto-resolving")
            await self._queue.dequeue(change.id)
            await self._refresh_entity(change.entity_type, change.entity_id)
            return

        if self._conflict_strategy == ConflictStrategy.SERVER_WINS:
            # Discard local change, refresh from cloud
            await self._queue.dequeue(change.id)
            await self._refresh_entity(change.entity_type, change.entity_id)

        elif self._conflict_strategy == ConflictStrategy.CLIENT_WINS:
            # Force push local version
            await self._force_push(change)

        elif self._conflict_strategy == ConflictStrategy.LAST_WRITE_WINS:
            # Compare timestamps and use most recent
            await self._resolve_by_timestamp(change)

        elif self._conflict_strategy == ConflictStrategy.ASK_USER:
            # Mark as conflict and emit signal for UI
            await self._queue.mark_conflict(change.id, str(error))
            if server_entity is None:
                # Can't show comparison dialog without server entity — fall back to server wins
                logger.warning(f"Cannot fetch server entity for conflict {change.entity_id}, discarding local")
                await self._queue.dequeue(change.id)
                await self._refresh_entity(change.entity_type, change.entity_id)
                return
            local_entity = json.loads(change.payload)
            self.conflict_detected.emit(change.id, local_entity, server_entity)

    async def _refresh_entity(self, entity_type: str, entity_id: UUID) -> None:
        """Refresh a single entity from the cloud."""
        if entity_type == "transaction":
            await self._transaction_repo.refresh_from_cloud()
        elif entity_type == "planned_template":
            await self._planned_repo.refresh_from_cloud()
        elif entity_type == "sheet":
            await self._sheet_repo.refresh_from_cloud()

    async def _force_push(self, change: PendingChange) -> None:
        """Force push a change, overwriting server version.

        Also dequeues the change after successful push so callers don't need to.
        """
        # Get current server version, increment, and push
        data = json.loads(change.payload)

        if change.entity_type == "transaction":
            current_version = await self._transaction_repo._cloud.get_version(change.entity_id)
            data["version"] = (current_version or 0) + 1
            transaction = self._deserialize_transaction(data)
            result = await self._transaction_repo.sync_to_cloud(transaction)
            await self._transaction_repo._local.save(result, force=True)

        elif change.entity_type == "planned_template":
            server = await self._planned_repo._cloud.get_by_id(change.entity_id)
            data["version"] = (server.version if server else 0) + 1
            template = self._deserialize_planned(data)
            result = await self._planned_repo.sync_to_cloud(template)
            await self._planned_repo._local.save(result)

        elif change.entity_type == "sheet":
            sheet = self._deserialize_sheet(data)
            result = await self._sheet_repo.sync_to_cloud(sheet)
            await self._sheet_repo._local.save(result)

        # Dequeue after successful push to prevent re-push on crash recovery
        await self._queue.dequeue(change.id)

    async def _resolve_by_timestamp(self, change: PendingChange) -> None:
        """Resolve conflict by comparing timestamps."""
        server_entity = await self._fetch_server_entity(change)
        if not server_entity:
            # Server doesn't have it - push local
            await self._force_push(change)
            return

        local_data = json.loads(change.payload)
        local_modified = local_data.get("modified_at") or local_data.get("created_at")
        server_modified = getattr(server_entity, "modified_at", None) or getattr(
            server_entity, "created_at", None
        )

        if local_modified and server_modified:
            from datetime import timezone
            if isinstance(local_modified, str):
                local_modified = datetime.fromisoformat(local_modified)
            if isinstance(server_modified, str):
                server_modified = datetime.fromisoformat(server_modified)

            # Normalize both timestamps to UTC for correct cross-timezone comparison.
            # Naive datetimes (no tzinfo) are assumed to be UTC already.
            if local_modified.tzinfo is not None:
                local_modified = local_modified.astimezone(timezone.utc).replace(tzinfo=None)
            if server_modified.tzinfo is not None:
                server_modified = server_modified.astimezone(timezone.utc).replace(tzinfo=None)

            if local_modified > server_modified:
                await self._force_push(change)
            else:
                await self._queue.dequeue(change.id)
                await self._refresh_entity(change.entity_type, change.entity_id)
        else:
            # Can't compare timestamps - use server version
            await self._queue.dequeue(change.id)
            await self._refresh_entity(change.entity_type, change.entity_id)

    async def _fetch_server_entity(self, change: PendingChange) -> Optional[Any]:
        """Fetch the server version of an entity."""
        try:
            if change.entity_type == "transaction":
                return await self._transaction_repo._cloud.get_by_id(change.entity_id)
            elif change.entity_type == "planned_template":
                return await self._planned_repo._cloud.get_by_id(change.entity_id)
            elif change.entity_type == "sheet":
                return await self._sheet_repo._cloud.get_by_id(change.entity_id)
        except Exception:
            return None

    def _is_same_content(self, change: PendingChange, server_entity: Any) -> bool:
        """Check if a queued change has the same content as the server entity.

        Compares all fields except version/timestamps to detect phantom conflicts
        (where the content is identical but versions diverged due to a lost response).
        """
        try:
            from decimal import Decimal as _Decimal
            data = json.loads(change.payload)
            if change.entity_type == "transaction":
                # Compare content fields (ignore version, created_at, modified_at, modified_by)
                content_fields = [
                    "description", "amount", "type", "status", "sheet",
                    "category", "party", "notes", "reference", "activity",
                ]
                for field in content_fields:
                    local_val = data.get(field, "") or ""
                    server_val = getattr(server_entity, field, "") or ""
                    # Normalize amounts to avoid "100" != "100.00"
                    if field == "amount":
                        try:
                            if _Decimal(str(local_val)) != _Decimal(str(server_val)):
                                return False
                            continue
                        except Exception:
                            pass
                    if str(local_val) != str(server_val):
                        return False
                # Compare date separately (may be string vs date)
                local_date = data.get("date", "")
                if isinstance(local_date, str) and local_date:
                    local_date = local_date[:10]  # YYYY-MM-DD
                server_date = str(server_entity.date) if server_entity.date else ""
                return local_date == server_date

            elif change.entity_type == "planned_template":
                content_fields = [
                    "description", "amount", "type", "frequency",
                    "target_sheet", "category", "party", "activity",
                ]
                for field in content_fields:
                    local_val = data.get(field, "") or ""
                    server_val = getattr(server_entity, field, "") or ""
                    if field == "amount":
                        try:
                            if _Decimal(str(local_val)) != _Decimal(str(server_val)):
                                return False
                            continue
                        except Exception:
                            pass
                    if str(local_val) != str(server_val):
                        return False
                return True

        except Exception:
            return False
        return False

    async def _update_pending_count(self) -> None:
        """Update and emit pending count if changed."""
        count = await self._queue.get_pending_count()
        if count != self._last_pending_count:
            self._last_pending_count = count
            self.pending_count_changed.emit(count)

    @property
    def is_syncing(self) -> bool:
        """Whether a sync operation is currently in progress."""
        return self._is_syncing

    async def get_pending_count(self) -> int:
        """Get current pending count."""
        return await self._queue.get_pending_count()

    async def resolve_conflict_with_choice(
        self, change_id: UUID, use_local: bool,
        entity_type: str = "", entity_id: UUID | None = None,
    ) -> None:
        """Resolve a conflict with user's choice.

        Args:
            change_id: ID of the conflicting change (queue entry ID)
            use_local: True to use local version, False to use server
            entity_type: Entity type (e.g. "transaction") for refresh on server-wins
            entity_id: Entity ID for refresh on server-wins
        """
        if use_local:
            # Force-push local version with updated version number to
            # avoid hitting the same conflict again on retry.
            # _force_push dequeues the change after successful push.
            change = await self._queue.get_by_id(change_id)
            if change:
                await self._force_push(change)
        else:
            # Discard local change and refresh from cloud
            await self._queue.resolve_conflict(change_id, use_local=False)
            if entity_type:
                await self._refresh_entity(entity_type, entity_id)

    # Deserialization helpers

    def _deserialize_transaction(self, data: dict) -> Transaction:
        """Deserialize transaction from JSON dict."""
        from decimal import Decimal
        from fidra.domain.models import TransactionType, ApprovalStatus

        return Transaction(
            id=UUID(data["id"]),
            date=datetime.fromisoformat(data["date"]).date()
            if isinstance(data["date"], str)
            else data["date"],
            description=data["description"],
            amount=Decimal(data["amount"]),
            type=TransactionType(data["type"]),
            status=ApprovalStatus(data["status"]),
            sheet=data["sheet"],
            category=data.get("category"),
            party=data.get("party"),
            notes=data.get("notes"),
            reference=data.get("reference"),
            activity=data.get("activity"),
            is_one_time_planned=data.get("is_one_time_planned"),
            version=data.get("version", 1),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else datetime.now(),
            modified_at=datetime.fromisoformat(data["modified_at"])
            if data.get("modified_at")
            else None,
            modified_by=data.get("modified_by"),
        )

    def _deserialize_planned(self, data: dict) -> PlannedTemplate:
        """Deserialize planned template from JSON dict."""
        from decimal import Decimal
        from fidra.domain.models import TransactionType, Frequency

        return PlannedTemplate(
            id=UUID(data["id"]),
            start_date=datetime.fromisoformat(data["start_date"]).date()
            if isinstance(data["start_date"], str)
            else data["start_date"],
            description=data["description"],
            amount=Decimal(data["amount"]),
            type=TransactionType(data["type"]),
            frequency=Frequency(data["frequency"]),
            target_sheet=data["target_sheet"],
            category=data.get("category"),
            party=data.get("party"),
            activity=data.get("activity"),
            end_date=datetime.fromisoformat(data["end_date"]).date()
            if data.get("end_date")
            else None,
            occurrence_count=data.get("occurrence_count"),
            skipped_dates=tuple(
                datetime.fromisoformat(d).date() for d in data.get("skipped_dates", [])
            ),
            fulfilled_dates=tuple(
                datetime.fromisoformat(d).date() for d in data.get("fulfilled_dates", [])
            ),
            version=data.get("version", 1),
        )

    def _deserialize_sheet(self, data: dict) -> Sheet:
        """Deserialize sheet from JSON dict."""
        return Sheet(
            id=UUID(data["id"]),
            name=data["name"],
            is_virtual=data.get("is_virtual", False),
            is_planned=data.get("is_planned", False),
        )
