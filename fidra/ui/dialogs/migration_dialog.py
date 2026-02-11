"""Data migration dialog for transferring data between SQLite and Supabase."""

from typing import TYPE_CHECKING, Optional

import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext

from fidra.services.migration import MigrationProgress, MigrationResult, MigrationService


class MigrationDialog(QDialog):
    """Wizard dialog for migrating data between SQLite and Supabase.

    Steps:
    1. Select migration direction (SQLite→Supabase or Supabase→SQLite)
    2. Configure options (include attachments, audit log)
    3. Execute migration with progress
    4. Show results
    """

    def __init__(self, context: "ApplicationContext", parent=None):
        super().__init__(parent)
        self._context = context
        self._migration_service = MigrationService()
        self._is_migrating = False

        self.setWindowTitle("Migrate Data")
        self.setModal(True)
        self.setMinimumSize(600, 450)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Stacked widget for wizard steps
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        # Step 1: Direction selection
        self._setup_step1()

        # Step 2: Options
        self._setup_step2()

        # Step 3: Progress
        self._setup_step3()

        # Step 4: Results
        self._setup_step4()

        # Navigation buttons
        nav_layout = QHBoxLayout()

        self._back_btn = QPushButton("< Back")
        self._back_btn.clicked.connect(self._on_back)
        self._back_btn.setEnabled(False)
        nav_layout.addWidget(self._back_btn)

        nav_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        nav_layout.addWidget(self._cancel_btn)

        self._next_btn = QPushButton("Next >")
        self._next_btn.clicked.connect(self._on_next)
        nav_layout.addWidget(self._next_btn)

        layout.addLayout(nav_layout)

    def _setup_step1(self) -> None:
        """Set up direction selection step."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        header = QLabel("Select Migration Direction")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Current status
        if self._context.is_supabase:
            status = QLabel("Current backend: Supabase (cloud)")
            status.setStyleSheet("color: #10b981;")
        else:
            status = QLabel(f"Current backend: SQLite ({self._context.db_path.name})")
            status.setStyleSheet("color: #6b7280;")
        layout.addWidget(status)

        # Direction options
        direction_group = QGroupBox("Migration Direction")
        direction_layout = QVBoxLayout(direction_group)

        self._to_supabase_radio = QRadioButton("SQLite → Supabase (Upload to cloud)")
        self._to_supabase_radio.setChecked(True)
        direction_layout.addWidget(self._to_supabase_radio)

        self._to_sqlite_radio = QRadioButton("Supabase → SQLite (Download to local)")
        direction_layout.addWidget(self._to_sqlite_radio)

        # Disable options that don't apply
        supabase_configured = bool(
            self._context.settings.storage.supabase.db_connection_string
        )

        if not supabase_configured:
            self._to_supabase_radio.setEnabled(False)
            self._to_sqlite_radio.setEnabled(False)
            warning = QLabel(
                "Supabase is not configured. Please configure it first in Settings."
            )
            warning.setStyleSheet("color: #ef4444;")
            direction_layout.addWidget(warning)

        layout.addWidget(direction_group)

        # Info text
        info = QLabel(
            "This will copy all data from the source to the destination.\n"
            "Existing data at the destination will be preserved (duplicates skipped)."
        )
        info.setObjectName("secondary_text")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()
        self._stack.addWidget(page)

    def _setup_step2(self) -> None:
        """Set up options step."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        header = QLabel("Migration Options")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Data options
        data_group = QGroupBox("Data to Migrate")
        data_layout = QVBoxLayout(data_group)

        self._include_transactions = QCheckBox("Transactions")
        self._include_transactions.setChecked(True)
        self._include_transactions.setEnabled(False)  # Always include
        data_layout.addWidget(self._include_transactions)

        self._include_planned = QCheckBox("Planned transaction templates")
        self._include_planned.setChecked(True)
        data_layout.addWidget(self._include_planned)

        self._include_sheets = QCheckBox("Sheet records")
        self._include_sheets.setChecked(True)
        data_layout.addWidget(self._include_sheets)

        self._include_attachments = QCheckBox("Attachments (metadata and files)")
        self._include_attachments.setChecked(True)
        data_layout.addWidget(self._include_attachments)

        self._include_audit = QCheckBox("Audit log")
        self._include_audit.setChecked(False)
        data_layout.addWidget(self._include_audit)

        layout.addWidget(data_group)

        # Warning
        warning_group = QGroupBox("Important")
        warning_layout = QVBoxLayout(warning_group)

        warning_text = QLabel(
            "• The migration will NOT delete data at the destination\n"
            "• Duplicate records (same ID) will be skipped\n"
            "• Attachment files will be copied (may take time for large files)\n"
            "• A backup of your current data is recommended before migrating"
        )
        warning_text.setWordWrap(True)
        warning_layout.addWidget(warning_text)

        layout.addWidget(warning_group)

        layout.addStretch()
        self._stack.addWidget(page)

    def _setup_step3(self) -> None:
        """Set up progress step."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        header = QLabel("Migrating Data")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        # Status label
        self._progress_label = QLabel("Preparing...")
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._progress_label)

        # Log area
        self._progress_log = QTextEdit()
        self._progress_log.setReadOnly(True)
        self._progress_log.setMaximumHeight(200)
        layout.addWidget(self._progress_log)

        layout.addStretch()
        self._stack.addWidget(page)

    def _setup_step4(self) -> None:
        """Set up results step."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        header = QLabel("Migration Complete")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Results summary
        self._results_label = QLabel()
        self._results_label.setWordWrap(True)
        layout.addWidget(self._results_label)

        # Errors area (if any)
        self._errors_group = QGroupBox("Errors")
        errors_layout = QVBoxLayout(self._errors_group)
        self._errors_text = QTextEdit()
        self._errors_text.setReadOnly(True)
        self._errors_text.setMaximumHeight(150)
        errors_layout.addWidget(self._errors_text)
        self._errors_group.setVisible(False)
        layout.addWidget(self._errors_group)

        # Switch backend option
        self._switch_backend_check = QCheckBox("Switch to the new backend now")
        self._switch_backend_check.setChecked(True)
        layout.addWidget(self._switch_backend_check)

        layout.addStretch()
        self._stack.addWidget(page)

    def _on_back(self) -> None:
        """Go to previous step."""
        current = self._stack.currentIndex()
        if current > 0:
            self._stack.setCurrentIndex(current - 1)
            self._update_buttons()

    def _on_next(self) -> None:
        """Go to next step or finish."""
        current = self._stack.currentIndex()

        if current == 0:
            # Validate step 1
            if not self._validate_step1():
                return
            self._stack.setCurrentIndex(1)
        elif current == 1:
            # Start migration
            self._stack.setCurrentIndex(2)
            self._start_migration()
        elif current == 3:
            # Finish
            self._finish_migration()
            return

        self._update_buttons()

    def _validate_step1(self) -> bool:
        """Validate direction selection."""
        supabase_configured = bool(
            self._context.settings.storage.supabase.db_connection_string
        )

        if not supabase_configured:
            QMessageBox.warning(
                self,
                "Supabase Not Configured",
                "Please configure Supabase settings first.\n\n"
                "Go to Settings > Configure Supabase..."
            )
            return False

        return True

    def _update_buttons(self) -> None:
        """Update navigation button states."""
        current = self._stack.currentIndex()

        self._back_btn.setEnabled(current > 0 and current < 2)

        if current == 2:
            # Progress step
            self._next_btn.setEnabled(False)
            self._cancel_btn.setEnabled(False)
        elif current == 3:
            # Results step
            self._next_btn.setText("Finish")
            self._next_btn.setEnabled(True)
            self._cancel_btn.setEnabled(False)
            self._back_btn.setEnabled(False)
        else:
            self._next_btn.setText("Next >")
            self._next_btn.setEnabled(True)
            self._cancel_btn.setEnabled(True)

    @qasync.asyncSlot()
    async def _start_migration(self) -> None:
        """Execute the migration."""
        self._is_migrating = True
        self._update_buttons()

        to_supabase = self._to_supabase_radio.isChecked()
        self._progress_log.clear()

        try:
            if to_supabase:
                await self._migrate_to_supabase()
            else:
                await self._migrate_to_sqlite()
        except Exception as e:
            self._log(f"Migration failed: {e}")
            self._show_error_result(str(e))
        finally:
            self._is_migrating = False

    async def _migrate_to_supabase(self) -> None:
        """Migrate data from SQLite to Supabase."""
        self._log("Starting migration to Supabase...")

        # Connect to Supabase
        from fidra.data.supabase_connection import SupabaseConnection
        from fidra.data.factory import create_repositories

        supabase_config = self._context.settings.storage.supabase
        supabase_conn = SupabaseConnection(supabase_config)

        try:
            self._log("Connecting to Supabase...")
            await supabase_conn.connect()

            # Create destination repositories
            dest_repos = await create_repositories(
                "supabase", supabase_connection=supabase_conn
            )
            dest_trans_repo, dest_planned_repo, dest_sheet_repo, dest_audit_repo, dest_attach_repo = dest_repos

            # Export from current (SQLite) repositories
            self._log("Exporting data from SQLite...")
            data = await self._migration_service.export_to_json(
                self._context.transaction_repo,
                self._context.planned_repo,
                self._context.sheet_repo,
                self._context.audit_repo,
                self._context.attachment_repo,
                progress_callback=self._on_progress,
            )

            # Filter data based on options
            if not self._include_planned.isChecked():
                data["planned_templates"] = []
            if not self._include_sheets.isChecked():
                data["sheets"] = []
            if not self._include_attachments.isChecked():
                data["attachments"] = []
            if not self._include_audit.isChecked():
                data["audit_log"] = []

            # Import to Supabase
            self._log("Importing data to Supabase...")
            result = await self._migration_service.import_from_json(
                data,
                dest_trans_repo,
                dest_planned_repo,
                dest_sheet_repo,
                dest_audit_repo,
                dest_attach_repo,
                progress_callback=self._on_progress,
            )

            # Migrate attachment files if included
            if self._include_attachments.isChecked() and data["attachments"]:
                self._log("Uploading attachment files to Supabase Storage...")
                from fidra.domain.models import Attachment

                attachments = [
                    self._migration_service._dict_to_attachment(a)
                    for a in data["attachments"]
                ]

                local_dir = self._context.db_path.parent / f"{self._context.db_path.stem}_attachments"
                uploaded, upload_errors = await self._migration_service.migrate_attachments_to_supabase(
                    local_dir,
                    attachments,
                    supabase_config,
                    progress_callback=self._on_progress,
                )
                result.errors.extend(upload_errors)
                self._log(f"Uploaded {uploaded} attachment files")

            self._show_result(result, to_supabase=True)

        finally:
            await supabase_conn.close()

    async def _migrate_to_sqlite(self) -> None:
        """Migrate data from Supabase to SQLite."""
        self._log("Starting migration to SQLite...")

        # Connect to Supabase to read data
        from fidra.data.supabase_connection import SupabaseConnection
        from fidra.data.factory import create_repositories

        supabase_config = self._context.settings.storage.supabase
        supabase_conn = SupabaseConnection(supabase_config)

        try:
            self._log("Connecting to Supabase...")
            await supabase_conn.connect()

            # Create source repositories (Supabase)
            src_repos = await create_repositories(
                "supabase", supabase_connection=supabase_conn
            )
            src_trans_repo, src_planned_repo, src_sheet_repo, src_audit_repo, src_attach_repo = src_repos

            # Export from Supabase
            self._log("Exporting data from Supabase...")
            data = await self._migration_service.export_to_json(
                src_trans_repo,
                src_planned_repo,
                src_sheet_repo,
                src_audit_repo,
                src_attach_repo,
                progress_callback=self._on_progress,
            )

            # Filter data based on options
            if not self._include_planned.isChecked():
                data["planned_templates"] = []
            if not self._include_sheets.isChecked():
                data["sheets"] = []
            if not self._include_attachments.isChecked():
                data["attachments"] = []
            if not self._include_audit.isChecked():
                data["audit_log"] = []

            # Import to SQLite (current context)
            self._log("Importing data to SQLite...")
            result = await self._migration_service.import_from_json(
                data,
                self._context.transaction_repo,
                self._context.planned_repo,
                self._context.sheet_repo,
                self._context.audit_repo,
                self._context.attachment_repo,
                progress_callback=self._on_progress,
            )

            # Download attachment files if included
            if self._include_attachments.isChecked() and data["attachments"]:
                self._log("Downloading attachment files from Supabase Storage...")
                from fidra.domain.models import Attachment

                attachments = [
                    self._migration_service._dict_to_attachment(a)
                    for a in data["attachments"]
                ]

                local_dir = self._context.db_path.parent / f"{self._context.db_path.stem}_attachments"
                downloaded, download_errors = await self._migration_service.migrate_attachments_to_local(
                    local_dir,
                    attachments,
                    supabase_config,
                    progress_callback=self._on_progress,
                )
                result.errors.extend(download_errors)
                self._log(f"Downloaded {downloaded} attachment files")

            self._show_result(result, to_supabase=False)

        finally:
            await supabase_conn.close()

    def _on_progress(self, progress: MigrationProgress) -> None:
        """Handle progress update."""
        if progress.total > 0:
            pct = int((progress.current / progress.total) * 100)
            self._progress_bar.setValue(pct)

        self._progress_label.setText(progress.message)
        self._log(progress.message)

    def _log(self, message: str) -> None:
        """Add message to progress log."""
        self._progress_log.append(message)

    def _show_result(self, result: MigrationResult, to_supabase: bool) -> None:
        """Show migration result."""
        self._stack.setCurrentIndex(3)
        self._update_buttons()

        direction = "to Supabase" if to_supabase else "to SQLite"

        summary = (
            f"Migration {direction} completed!\n\n"
            f"Transactions: {result.transactions_migrated}\n"
            f"Planned templates: {result.planned_templates_migrated}\n"
            f"Sheets: {result.sheets_migrated}\n"
            f"Attachments: {result.attachments_migrated}\n"
            f"Audit entries: {result.audit_entries_migrated}"
        )
        self._results_label.setText(summary)

        if result.errors:
            self._errors_group.setVisible(True)
            self._errors_text.setPlainText("\n".join(result.errors))
        else:
            self._errors_group.setVisible(False)

        # Store result for finish action
        self._migration_result = result
        self._migrated_to_supabase = to_supabase

    def _show_error_result(self, error: str) -> None:
        """Show error result."""
        self._stack.setCurrentIndex(3)
        self._update_buttons()

        self._results_label.setText(f"Migration failed:\n\n{error}")
        self._errors_group.setVisible(False)
        self._switch_backend_check.setVisible(False)

        self._migration_result = None

    @qasync.asyncSlot()
    async def _finish_migration(self) -> None:
        """Finish migration and optionally switch backend."""
        if self._switch_backend_check.isChecked() and hasattr(self, '_migrated_to_supabase'):
            try:
                if self._migrated_to_supabase:
                    await self._context.switch_to_supabase()
                    QMessageBox.information(
                        self,
                        "Backend Switched",
                        "Now using Supabase backend.\n\n"
                        "Your data is stored in the cloud."
                    )
                else:
                    # Already on SQLite, just reload
                    await self._context._load_initial_data()

            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Switch Failed",
                    f"Could not switch backend: {e}\n\n"
                    "Your data has been migrated but you're still on the current backend."
                )

        self.accept()
