"""Application context and dependency injection.

The ApplicationContext wires together all application components
and provides them to the UI layer.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from fidra.data.factory import create_repositories
from fidra.data.repository import (
    AttachmentRepository,
    AuditRepository,
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
                     Ignored when using Supabase backend.
        """
        self._db_path = db_path or Path("fidra.db")

        # Settings
        self.settings_store = SettingsStore()
        self.settings: AppSettings = self.settings_store.load()

        # State
        self.state = AppState()

        # Supabase connection (initialized in initialize() if using supabase backend)
        self._supabase_connection = None

        # Repositories (initialized in initialize())
        self.transaction_repo: Optional[TransactionRepository] = None
        self.planned_repo: Optional[PlannedRepository] = None
        self.sheet_repo: Optional[SheetRepository] = None
        self.audit_repo: Optional[AuditRepository] = None
        self.attachment_repo: Optional[AttachmentRepository] = None

        # Services
        self.attachment_service: Optional[Union[AttachmentService, "SupabaseAttachmentService"]] = None
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

        if backend == "supabase":
            # Initialize Supabase connection and repositories
            from fidra.data.supabase_connection import SupabaseConnection
            from fidra.services.supabase_attachments import SupabaseAttachmentService

            supabase_config = self.settings.storage.supabase
            self._supabase_connection = SupabaseConnection(supabase_config)
            await self._supabase_connection.connect()

            (
                self.transaction_repo, self.planned_repo, self.sheet_repo,
                self.audit_repo, self.attachment_repo,
            ) = await create_repositories(
                backend, supabase_connection=self._supabase_connection
            )

            # Create Supabase attachment service
            user = self.settings.profile.initials or self.settings.profile.name or "System"
            self.audit_service = AuditService(self.audit_repo, user=user)
            self.attachment_service = SupabaseAttachmentService(
                self.attachment_repo, supabase_config
            )
        else:
            # SQLite backend (default)
            (
                self.transaction_repo, self.planned_repo, self.sheet_repo,
                self.audit_repo, self.attachment_repo,
            ) = await create_repositories(backend, self._db_path)

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
        if backend == "supabase":
            if self._supabase_connection:
                await self._supabase_connection.close()
                self._supabase_connection = None
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
            self.audit_repo, self.attachment_repo,
        ) = await create_repositories("sqlite", self._db_path)

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

    async def switch_to_supabase(self) -> None:
        """Switch to Supabase backend using configured settings.

        Requires Supabase settings to be configured first.
        """
        from fidra.data.supabase_connection import SupabaseConnection
        from fidra.services.supabase_attachments import SupabaseAttachmentService

        supabase_config = self.settings.storage.supabase
        if not supabase_config.db_connection_string:
            raise ValueError("Supabase connection string not configured")

        # Close existing connections
        await self.close()

        # Update backend
        self.settings.storage.backend = "supabase"

        # Initialize Supabase connection
        self._supabase_connection = SupabaseConnection(supabase_config)
        await self._supabase_connection.connect()

        # Create repositories
        (
            self.transaction_repo, self.planned_repo, self.sheet_repo,
            self.audit_repo, self.attachment_repo,
        ) = await create_repositories(
            "supabase", supabase_connection=self._supabase_connection
        )

        # Recreate services
        user = self.settings.profile.initials or self.settings.profile.name or "System"
        self.audit_service = AuditService(self.audit_repo, user=user)
        self.attachment_service = SupabaseAttachmentService(
            self.attachment_repo, supabase_config
        )

        # Reload all data
        await self._load_initial_data()

        # Save settings
        self.save_settings()

    @property
    def is_supabase(self) -> bool:
        """Check if currently using Supabase backend."""
        return self.settings.storage.backend == "supabase"

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
