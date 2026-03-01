"""Application context and dependency injection.

The ApplicationContext wires together all application components
and provides them to the UI layer.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)

from fidra.data.factory import create_repositories
from fidra.data.repository import (
    ActivityNotesRepository,
    AttachmentRepository,
    AuditRepository,
    CategoryRepository,
    PlannedRepository,
    SheetRepository,
    TransactionRepository,
)
from fidra.domain.settings import AppSettings
from fidra.state.app_state import AppState
from fidra.state.persistence import SettingsStore
from fidra.services.attachments import AttachmentService
from fidra.services.audit import AuditService
from fidra.services.backup import BackupService
from fidra.services.balance import BalanceService
from fidra.services.export import ExportService
from fidra.services.file_watcher import FileWatcherService
from fidra.services.financial_year import FinancialYearService
from fidra.services.forecast import ForecastService
from fidra.services.search import SearchService
from fidra.services.undo import UndoStack

# Conditional import for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fidra.services.connection_state import ConnectionStateService
    from fidra.services.sync_service import SyncService
    from fidra.data.sync_queue import SyncQueue


class ApplicationContext:
    """Application context providing dependency injection.

    The context holds all application services and state,
    making them available throughout the application.

    Example:
        >>> ctx = ApplicationContext()
        >>> await ctx.initialize()
        >>> # Access repositories
        >>> transactions = await ctx.transaction_repo.get_all()
        >>> # Access state
        >>> ctx.state.transactions.set(transactions)
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize application context.

        Args:
            db_path: Optional path to database file.
                     Defaults to "fidra.db" in current directory.
                     Ignored when using cloud backend.
        """
        self._db_path = db_path or Path("fidra.db")

        # Settings
        self.settings_store = SettingsStore()
        self.settings: AppSettings = self.settings_store.load()

        # State
        self.state = AppState()

        # Cloud connection (initialized in initialize() if using cloud backend)
        self._cloud_connection = None
        self.connection_state: Optional["ConnectionStateService"] = None
        self.sync_queue: Optional["SyncQueue"] = None
        self.sync_service: Optional["SyncService"] = None
        self.change_listener = None  # ChangeListener for real-time LISTEN/NOTIFY

        # Buffered remote changes during sync + post-sync cooldown
        self._buffered_remote_changes: set[str] = set()
        self._sync_cooldown_until: float = 0.0

        # Repositories (initialized in initialize())
        self.transaction_repo: Optional[TransactionRepository] = None
        self.planned_repo: Optional[PlannedRepository] = None
        self.sheet_repo: Optional[SheetRepository] = None
        self.audit_repo: Optional[AuditRepository] = None
        self.attachment_repo: Optional[AttachmentRepository] = None
        self.category_repo: Optional[CategoryRepository] = None
        self.activity_notes_repo: Optional[ActivityNotesRepository] = None

        # Services
        self.attachment_service: Optional[Union[AttachmentService, "CloudAttachmentService"]] = None
        self.audit_service: Optional[AuditService] = None
        self.backup_service = BackupService(self._db_path, self.settings.backup)
        self.balance_service = BalanceService()
        self.export_service = ExportService(self.balance_service)
        self.file_watcher = FileWatcherService()
        self.financial_year_service = FinancialYearService(
            start_month=self.settings.financial_year.start_month
        )
        self.forecast_service = ForecastService()
        self.search_service = SearchService()
        self.undo_stack = UndoStack(max_size=50)

    async def initialize(self) -> None:
        """Initialize async components (repositories).

        Must be called before using the context.

        Example:
            >>> ctx = ApplicationContext()
            >>> await ctx.initialize()
        """
        # Create repositories based on settings
        backend = self.settings.storage.backend

        if backend == "cloud":
            # Initialize cloud connection and repositories
            from fidra.data.cloud_connection import CloudConnection
            from fidra.services.cloud_attachments import create_cloud_attachment_service

            server_config = self.settings.storage.get_active_server()
            if not server_config:
                raise ValueError("No cloud server configured")

            self._cloud_connection = CloudConnection(server_config)
            await self._cloud_connection.connect()

            # Create connection state service for monitoring
            from fidra.services.connection_state import ConnectionStateService
            self.connection_state = ConnectionStateService(self._cloud_connection)
            self.connection_state.start_monitoring()

            # Wire up connection state to app state
            self.connection_state.status_changed.connect(
                lambda status: self.state.connection_status.set(status.value)
            )

            (
                self.transaction_repo, self.planned_repo, self.sheet_repo,
                self.audit_repo, self.attachment_repo, self.category_repo,
                self.activity_notes_repo, self.sync_queue,
            ) = await create_repositories(
                backend,
                cloud_connection=self._cloud_connection,
                connection_state=self.connection_state,
            )

            # Initialize sync service if we have a sync queue
            if self.sync_queue:
                await self._init_sync_service()

            # Start real-time change listener for updates from other devices
            await self._init_change_listener()

            # Migrate categories from settings to database if empty
            await self._migrate_categories_to_db()

            # Migrate activity notes from settings to database if empty
            await self._migrate_activity_notes_to_db()

            # Create cloud attachment service
            user = self.settings.profile.initials or self.settings.profile.name or "System"
            self.audit_service = AuditService(
                self.audit_repo, user=user, connection_state=self.connection_state
            )
            self.attachment_service = create_cloud_attachment_service(
                self.attachment_repo, server_config.storage
            )
        else:
            # SQLite backend (default)
            (
                self.transaction_repo, self.planned_repo, self.sheet_repo,
                self.audit_repo, self.attachment_repo, self.category_repo,
                self.activity_notes_repo, _,  # No sync queue for SQLite
            ) = await create_repositories(backend, self._db_path)

            # Migrate categories from settings to database if empty
            await self._migrate_categories_to_db()

            # Migrate activity notes from settings to database if empty
            await self._migrate_activity_notes_to_db()

            # Create local attachment service
            user = self.settings.profile.initials or self.settings.profile.name or "System"
            self.audit_service = AuditService(self.audit_repo, user=user)
            self.attachment_service = AttachmentService(self.attachment_repo, self._db_path)

            # Start watching the database file for external changes (SQLite only)
            self.file_watcher.start_watching(self._db_path)

        # Load initial data
        await self._load_initial_data()

        # Restore UI state from settings
        self._restore_ui_state()

    async def _init_sync_service(self) -> None:
        """Initialize the background sync service for cloud mode."""
        from fidra.services.sync_service import SyncService, ConflictStrategy
        from fidra.services.connection_state import ConnectionStatus

        # Get sync settings
        sync_settings = self.settings.sync
        strategy = ConflictStrategy(sync_settings.conflict_strategy)

        self.sync_service = SyncService(
            sync_queue=self.sync_queue,
            transaction_repo=self.transaction_repo,
            planned_repo=self.planned_repo,
            sheet_repo=self.sheet_repo,
            category_repo=self.category_repo,
            connection_state=self.connection_state,
            activity_notes_repo=self.activity_notes_repo,
            conflict_strategy=strategy,
            sync_interval_ms=sync_settings.sync_interval_seconds * 1000,
        )

        # Wire up signals to app state
        self.sync_service.pending_count_changed.connect(
            lambda count: self.state.pending_sync_count.set(count)
        )
        self.sync_service.sync_completed.connect(self._on_sync_completed)

        # Trigger immediate sync and restart listener when connection is restored
        def on_status_changed(status: ConnectionStatus):
            if status == ConnectionStatus.CONNECTED:
                # Use QTimer to defer to avoid re-entrancy issues
                from PySide6.QtCore import QTimer
                QTimer.singleShot(100, lambda: asyncio.ensure_future(self.sync_service.sync_now()))
                if self.change_listener:
                    QTimer.singleShot(500, lambda: asyncio.ensure_future(self.change_listener.restart()))

        self.connection_state.status_changed.connect(on_status_changed)

        # Start the sync service
        self.sync_service.start()

        # If there are pending changes from a previous session, sync immediately
        pending_count = await self.sync_queue.get_pending_count()
        if pending_count > 0:
            print(f"[SYNC] Found {pending_count} pending changes from previous session")
            try:
                await self.sync_service.sync_now()
                # After syncing, refresh caches from cloud to get any other updates
                await self._refresh_caches_from_cloud()
            except Exception as e:
                print(f"[SYNC] Initial sync failed: {e} - will retry in background")

    async def _init_change_listener(self) -> None:
        """Initialize the real-time change listener for cloud mode."""
        from fidra.services.change_listener import ChangeListener

        self.change_listener = ChangeListener(
            cloud_connection=self._cloud_connection,
            debounce_ms=1000,
        )
        # Use ensure_future since ApplicationContext is not a QObject
        self.change_listener.tables_changed.connect(
            lambda tables: asyncio.ensure_future(self._on_remote_tables_changed(tables))
        )
        await self.change_listener.start()

    def _on_sync_completed(self, count: int) -> None:
        """Handle sync completion: set cooldown and replay buffered changes."""
        import time

        self.state.last_sync_time.set(datetime.now())

        if count > 0:
            # Set a 2-second cooldown to ignore self-triggered NOTIFY events
            self._sync_cooldown_until = time.monotonic() + 2.0

        # Replay any changes that were buffered during sync
        if self._buffered_remote_changes:
            buffered = self._buffered_remote_changes.copy()
            self._buffered_remote_changes.clear()
            logger.debug(f"Replaying buffered remote changes: {buffered}")
            # Delay replay past the cooldown window so genuine remote changes
            # (vs self-triggered ones) get processed. If they were self-triggered,
            # the cooldown will filter them. If they were genuine, we want them.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(
                2500,
                lambda: asyncio.ensure_future(self._on_remote_tables_changed(buffered)),
            )

    async def _on_remote_tables_changed(self, changed_tables: set) -> None:
        """Handle remote data changes detected via LISTEN/NOTIFY."""
        # Buffer changes while sync is in progress — they'll be replayed when sync completes
        if self.sync_service and self.sync_service.is_syncing:
            logger.debug(f"Buffering remote changes during sync: {changed_tables}")
            self._buffered_remote_changes.update(changed_tables)
            return

        # Skip notifications that arrive within the post-sync cooldown window
        # (these are almost certainly self-triggered by our own push)
        import time
        if time.monotonic() < self._sync_cooldown_until:
            logger.debug(f"Ignoring self-triggered notification: {changed_tables}")
            return

        for attempt in range(2):
            try:
                if "transactions" in changed_tables and hasattr(self.transaction_repo, 'refresh_from_cloud'):
                    await self.transaction_repo.refresh_from_cloud()
                if "planned_templates" in changed_tables and hasattr(self.planned_repo, 'refresh_from_cloud'):
                    await self.planned_repo.refresh_from_cloud()
                if "sheets" in changed_tables and hasattr(self.sheet_repo, 'refresh_from_cloud'):
                    await self.sheet_repo.refresh_from_cloud()
                if "categories" in changed_tables and hasattr(self.category_repo, 'refresh_from_cloud'):
                    await self.category_repo.refresh_from_cloud()
                if "activity_notes" in changed_tables and hasattr(self.activity_notes_repo, 'refresh_from_cloud'):
                    await self.activity_notes_repo.refresh_from_cloud()

                # Reload state from refreshed caches
                await self._load_initial_data()
                print(f"[LISTEN] Refreshed state for: {changed_tables}")
                return
            except Exception as e:
                print(f"[LISTEN] Refresh attempt {attempt + 1} failed: {e}")
                if "readonly" in str(e).lower() and attempt == 0:
                    await self._reconnect_local_cache()
                elif attempt == 0:
                    await asyncio.sleep(1)

    async def _reconnect_local_cache(self) -> None:
        """Reconnect the local SQLite cache after a readonly error.

        SQLite can mark a connection as readonly if the underlying file
        was replaced (SQLITE_READONLY_DBMOVED). Reopening the connection
        fixes this.
        """
        if not hasattr(self.transaction_repo, '_local'):
            return

        local_trans = self.transaction_repo._local
        old_conn = local_trans._conn

        # Close the stale connection
        if old_conn:
            try:
                await old_conn.close()
            except Exception:
                pass

        # Reopen
        await local_trans.connect()
        new_conn = local_trans._conn

        # Update all repos that share this connection
        if hasattr(self.planned_repo, '_local'):
            self.planned_repo._local._conn = new_conn
        if hasattr(self.sheet_repo, '_local'):
            self.sheet_repo._local._conn = new_conn
        if hasattr(self.category_repo, '_local'):
            self.category_repo._local._conn = new_conn
        if hasattr(self.activity_notes_repo, '_local'):
            self.activity_notes_repo._local._conn = new_conn

        print("[CACHE] Local cache connection reconnected")

    async def _refresh_caches_from_cloud(self) -> None:
        """Refresh all caches from cloud data.

        Called after syncing pending changes to get latest server state.
        """
        if hasattr(self.transaction_repo, 'refresh_from_cloud'):
            print("[CACHE] Refreshing caches from cloud...")
            try:
                await self.transaction_repo.refresh_from_cloud()
                await self.planned_repo.refresh_from_cloud()
                await self.sheet_repo.refresh_from_cloud()
                await self.category_repo.refresh_from_cloud()
                if hasattr(self.activity_notes_repo, 'refresh_from_cloud'):
                    await self.activity_notes_repo.refresh_from_cloud()
                print("[CACHE] Cache refresh complete")
            except Exception as e:
                print(f"[CACHE] Cache refresh failed: {e}")

    async def _load_initial_data(self) -> None:
        """Load initial data into state."""
        # Load transactions
        transactions = await self.transaction_repo.get_all()
        self.state.transactions.set(transactions)

        # Load planned templates
        templates = await self.planned_repo.get_all()
        self.state.planned_templates.set(templates)

        # Load sheets and sync with transaction sheet names
        sheets = await self.sheet_repo.get_all()
        sheets = await self._sync_sheets_from_transactions(sheets, transactions)
        self.state.sheets.set(sheets)

    async def _sync_sheets_from_transactions(
        self, sheets: list, transactions: list
    ) -> list:
        """Ensure all sheet names used by transactions have Sheet records.

        Args:
            sheets: Existing sheets from database
            transactions: All transactions

        Returns:
            Updated list of sheets
        """
        from fidra.domain.models import Sheet

        # Get existing sheet names
        existing_names = {s.name for s in sheets}

        # Get unique sheet names from transactions
        transaction_sheets = {t.sheet for t in transactions if t.sheet}

        # Create Sheet records for any missing sheet names
        for sheet_name in transaction_sheets:
            if sheet_name not in existing_names:
                new_sheet = Sheet.create(name=sheet_name)
                await self.sheet_repo.save(new_sheet)
                sheets.append(new_sheet)
                existing_names.add(sheet_name)

        return sheets

    async def close(self) -> None:
        """Close resources (database connections)."""
        backend = self.settings.storage.backend

        # Auto-backup on close if enabled (SQLite only)
        if backend == "sqlite" and self.settings.backup.auto_backup_on_close:
            try:
                self.backup_service.create_backup(trigger="auto_close")
            except Exception:
                # Don't block closing on backup failure
                pass

        # Stop file watcher (SQLite only)
        self.file_watcher.stop_watching()

        # Close connections based on backend
        if backend == "cloud":
            # Stop change listener
            if self.change_listener:
                try:
                    await asyncio.wait_for(self.change_listener.stop(), timeout=2.0)
                except asyncio.TimeoutError:
                    print("Warning: Change listener stop timed out")
                self.change_listener = None

            # Stop sync service (with timeout to prevent hanging)
            if self.sync_service:
                try:
                    await asyncio.wait_for(self.sync_service.stop_async(), timeout=2.0)
                except asyncio.TimeoutError:
                    print("Warning: Sync service stop timed out")
                self.sync_service = None

            # Close sync queue
            if self.sync_queue:
                try:
                    await asyncio.wait_for(self.sync_queue.close(), timeout=2.0)
                except asyncio.TimeoutError:
                    print("Warning: Sync queue close timed out")
                self.sync_queue = None

            # Stop connection monitoring
            if self.connection_state:
                try:
                    await asyncio.wait_for(self.connection_state.stop_monitoring_async(), timeout=2.0)
                except asyncio.TimeoutError:
                    print("Warning: Connection state stop timed out")
                self.connection_state = None

            # Close local cache connections (SQLite cache used by caching repos)
            if self.transaction_repo and hasattr(self.transaction_repo, 'close'):
                try:
                    await asyncio.wait_for(self.transaction_repo.close(), timeout=2.0)
                except (asyncio.TimeoutError, Exception):
                    pass

            # Close cloud connection (uses timeout with terminate() fallback)
            if self._cloud_connection:
                await self._cloud_connection.close(timeout=2.0)
                self._cloud_connection = None
        else:
            if self.transaction_repo:
                await self.transaction_repo.close()

    async def switch_database(self, new_path: Path) -> None:
        """Switch to a different SQLite database file.

        Args:
            new_path: Path to the new database file
        """
        # Close existing connections
        await self.close()

        # Update path and ensure SQLite backend
        self._db_path = new_path
        self.settings.storage.backend = "sqlite"

        # Reinitialize repositories
        (
            self.transaction_repo, self.planned_repo, self.sheet_repo,
            self.audit_repo, self.attachment_repo, self.category_repo,
            self.activity_notes_repo, _,  # No sync queue for SQLite
        ) = await create_repositories("sqlite", self._db_path)

        # Migrate categories from settings to database if empty
        await self._migrate_categories_to_db()
        await self._migrate_activity_notes_to_db()

        # Recreate services with new repos
        user = self.settings.profile.initials or self.settings.profile.name or "System"
        self.audit_service = AuditService(self.audit_repo, user=user)
        self.attachment_service = AttachmentService(self.attachment_repo, self._db_path)

        # Update backup service with new database path
        self.backup_service.db_path = self._db_path

        # Reload all data
        await self._load_initial_data()

        # Restart file watcher for new database
        self.file_watcher.start_watching(self._db_path)

        # Save last opened file path and timestamp to settings
        self.settings.storage.last_file = new_path
        self.settings.storage.last_opened_at = datetime.now().isoformat()
        self.save_settings()

    async def switch_to_cloud(self, server_id: str | None = None) -> None:
        """Switch to cloud backend using configured settings.

        Args:
            server_id: ID of the server to connect to. If None, uses active_server_id.

        Requires cloud server settings to be configured first.
        """
        from fidra.data.cloud_connection import CloudConnection
        from fidra.services.cloud_attachments import create_cloud_attachment_service

        # Get the server config
        if server_id:
            self.settings.storage.active_server_id = server_id

        server_config = self.settings.storage.get_active_server()
        if not server_config:
            raise ValueError("No cloud server configured")

        if not server_config.db_connection_string:
            raise ValueError("Database connection string not configured")

        # Close existing connections
        await self.close()

        # Update backend
        self.settings.storage.backend = "cloud"

        # Initialize cloud connection
        self._cloud_connection = CloudConnection(server_config)
        await self._cloud_connection.connect()

        # Create connection state service for monitoring
        from fidra.services.connection_state import ConnectionStateService
        self.connection_state = ConnectionStateService(self._cloud_connection)
        self.connection_state.start_monitoring()

        # Wire up connection state to app state
        self.connection_state.status_changed.connect(
            lambda status: self.state.connection_status.set(status.value)
        )

        # Create repositories with caching
        (
            self.transaction_repo, self.planned_repo, self.sheet_repo,
            self.audit_repo, self.attachment_repo, self.category_repo,
            self.activity_notes_repo, self.sync_queue,
        ) = await create_repositories(
            "cloud",
            cloud_connection=self._cloud_connection,
            connection_state=self.connection_state,
        )

        # Initialize sync service if we have a sync queue
        if self.sync_queue:
            await self._init_sync_service()

        # Start real-time change listener for updates from other devices
        await self._init_change_listener()

        # Migrate categories from settings to database if empty
        await self._migrate_categories_to_db()
        await self._migrate_activity_notes_to_db()

        # Recreate services
        user = self.settings.profile.initials or self.settings.profile.name or "System"
        self.audit_service = AuditService(
            self.audit_repo, user=user, connection_state=self.connection_state
        )
        self.attachment_service = create_cloud_attachment_service(
            self.attachment_repo, server_config.storage
        )

        # Reload all data
        await self._load_initial_data()

        # Restore UI state from settings
        self._restore_ui_state()

        # Save settings
        self.save_settings()

    @property
    def is_cloud(self) -> bool:
        """Check if currently using cloud backend."""
        return self.settings.storage.backend == "cloud"

    @property
    def active_server(self):
        """Get the active cloud server configuration."""
        return self.settings.storage.get_active_server()

    @property
    def db_path(self) -> Path:
        """Get current database path."""
        return self._db_path

    def save_settings(self) -> None:
        """Save current settings to disk."""
        self.settings_store.save(self.settings)

    def _restore_ui_state(self) -> None:
        """Restore UI state from persisted settings."""
        ui_state = self.settings.ui_state
        self.state.include_planned.set(ui_state.show_planned)
        self.state.filtered_balance_mode.set(ui_state.filtered_balance_mode)
        self.state.current_sheet.set(ui_state.current_sheet)

    def save_ui_state(self) -> None:
        """Save current UI state to settings."""
        self.settings.ui_state.show_planned = self.state.include_planned.value
        self.settings.ui_state.filtered_balance_mode = self.state.filtered_balance_mode.value
        self.settings.ui_state.current_sheet = self.state.current_sheet.value
        self.save_settings()

    async def _migrate_categories_to_db(self) -> None:
        """Migrate categories from settings to database if database is empty.

        This handles the one-time migration when upgrading from settings-based
        categories to database-stored categories.
        """
        if not self.category_repo:
            return

        # Check if database already has categories
        income_cats = await self.category_repo.get_all("income")
        expense_cats = await self.category_repo.get_all("expense")

        if income_cats or expense_cats:
            # Database already has categories, don't overwrite
            return

        # Migrate from settings
        settings_income = self.settings.income_categories
        settings_expense = self.settings.expense_categories

        if settings_income:
            await self.category_repo.set_all("income", settings_income)

        if settings_expense:
            await self.category_repo.set_all("expense", settings_expense)

    async def _migrate_activity_notes_to_db(self) -> None:
        """Migrate activity notes from settings JSON to database if database is empty.

        Reads the raw JSON file to find activity_notes that were stripped
        during settings migration (the field no longer exists on AppSettings).
        """
        if not self.activity_notes_repo:
            return

        # Check if database already has notes
        existing_notes = await self.activity_notes_repo.get_all()
        if existing_notes:
            return

        # Read raw JSON to find old activity_notes before they were stripped
        import json
        settings_path = self.settings_store.path
        if not settings_path.exists():
            return

        try:
            raw = json.loads(settings_path.read_text())
            notes = raw.get("activity_notes")
            if notes and isinstance(notes, dict):
                for activity, text in notes.items():
                    if text and text.strip():
                        await self.activity_notes_repo.save(activity, text.strip())
        except Exception:
            pass

    async def get_categories(self, type: str) -> list[str]:
        """Get categories for a transaction type.

        Args:
            type: 'income' or 'expense'

        Returns:
            List of category names
        """
        if self.category_repo:
            return await self.category_repo.get_all(type)
        # Fallback to settings (shouldn't happen after migration)
        if type == "income":
            return self.settings.income_categories
        return self.settings.expense_categories

    async def set_categories(self, type: str, categories: list[str]) -> None:
        """Set categories for a transaction type.

        Args:
            type: 'income' or 'expense'
            categories: List of category names
        """
        if self.category_repo:
            await self.category_repo.set_all(type, categories)
