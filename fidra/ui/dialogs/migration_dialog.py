"""Data migration dialog for transferring data between SQLite and cloud backends."""

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
    """Wizard dialog for migrating data between SQLite and cloud backends.

    Steps:
    1. Select migration direction (SQLite -> Cloud or Cloud -> SQLite)
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
        if self._context.is_cloud:
            server = self._context.active_server
            server_name = server.name if server else "Cloud"
            status = QLabel(f"Current backend: {server_name} (cloud)")
            status.setStyleSheet("color: #10b981;")
        else:
            status = QLabel(f"Current backend: SQLite ({self._context.db_path.name})")
            status.setStyleSheet("color: #6b7280;")
        layout.addWidget(status)

        # Direction options
        direction_group = QGroupBox("Migration Direction")
        direction_layout = QVBoxLayout(direction_group)

        self._to_cloud_radio = QRadioButton("SQLite -> Cloud (Upload to cloud)")
        direction_layout.addWidget(self._to_cloud_radio)

        self._to_sqlite_radio = QRadioButton("Cloud -> SQLite (Download to local)")
        direction_layout.addWidget(self._to_sqlite_radio)

        # Disable options that don't apply
        active_server = self._context.settings.storage.get_active_server()
        cloud_configured = active_server is not None and active_server.db_connection_string

        if not cloud_configured:
            self._to_cloud_radio.setEnabled(False)
            self._to_sqlite_radio.setEnabled(False)
            warning = QLabel(
                "No cloud server configured. Please add a server first in Settings > Cloud Servers."
            )
            warning.setStyleSheet("color: #ef4444;")
            direction_layout.addWidget(warning)
        elif self._context.is_cloud:
            # Currently on cloud - SQLite->Cloud doesn't make sense
            self._to_cloud_radio.setEnabled(False)
            self._to_sqlite_radio.setChecked(True)
            warning = QLabel(
                "You're currently connected to cloud. SQLite -> Cloud is only available\n"
                "when connected to a local SQLite file."
            )
            warning.setStyleSheet("color: #f59e0b;")
            warning.setWordWrap(True)
            direction_layout.addWidget(warning)
        else:
            # Currently on SQLite - this is the normal case for SQLite->Cloud
            self._to_cloud_radio.setChecked(True)

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
            "- The migration will NOT delete data at the destination\n"
            "- Duplicate records (same ID) will be skipped\n"
            "- Attachment files will be copied (may take time for large files)\n"
            "- A backup of your current data is recommended before migrating"
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
        active_server = self._context.settings.storage.get_active_server()
        cloud_configured = active_server is not None and active_server.db_connection_string

        if not cloud_configured:
            QMessageBox.warning(
                self,
                "Cloud Server Not Configured",
                "Please configure a cloud server first.\n\n"
                "Go to Settings > Cloud Servers..."
            )
            return False

        # Safety check: can't migrate SQLite->Cloud when already on cloud
        if self._to_cloud_radio.isChecked() and self._context.is_cloud:
            QMessageBox.warning(
                self,
                "Invalid Migration Direction",
                "You are currently connected to a cloud server.\n\n"
                "To upload data from SQLite to cloud, first connect to a local SQLite file,\n"
                "then migrate to cloud."
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

        to_cloud = self._to_cloud_radio.isChecked()
        self._progress_log.clear()

        try:
            if to_cloud:
                await self._migrate_to_cloud()
            else:
                await self._migrate_to_sqlite()
        except Exception as e:
            self._log(f"Migration failed: {e}")
            self._show_error_result(str(e))
        finally:
            self._is_migrating = False

    async def _migrate_to_cloud(self) -> None:
        """Migrate data from SQLite to cloud server."""
        self._log("Starting migration to cloud...")

        # Connect to cloud server
        from fidra.data.cloud_connection import CloudConnection
        from fidra.data.factory import create_repositories

        server_config = self._context.settings.storage.get_active_server()
        cloud_conn = CloudConnection(server_config)

        try:
            self._log(f"Connecting to {server_config.name}...")
            await cloud_conn.connect()

            # Create destination repositories
            dest_repos = await create_repositories(
                "cloud", cloud_connection=cloud_conn
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

            # Import to cloud
            self._log("Importing data to cloud...")
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
                self._log("Uploading attachment files to cloud storage...")
                from fidra.domain.models import Attachment

                attachments = [
                    self._migration_service._dict_to_attachment(a)
                    for a in data["attachments"]
                ]

                local_dir = self._context.db_path.parent / f"{self._context.db_path.stem}_attachments"
                uploaded, upload_errors = await self._migration_service.migrate_attachments_to_cloud(
                    local_dir,
                    attachments,
                    server_config.storage,
                    progress_callback=self._on_progress,
                )
                result.errors.extend(upload_errors)
                self._log(f"Uploaded {uploaded} attachment files")

            self._show_result(result, to_cloud=True)

        finally:
            await cloud_conn.close()

    async def _migrate_to_sqlite(self) -> None:
        """Migrate data from cloud to SQLite."""
        self._log("Starting migration to SQLite...")

        # Connect to cloud to read data
        from fidra.data.cloud_connection import CloudConnection
        from fidra.data.factory import create_repositories

        server_config = self._context.settings.storage.get_active_server()
        cloud_conn = CloudConnection(server_config)

        try:
            self._log(f"Connecting to {server_config.name}...")
            await cloud_conn.connect()

            # Create source repositories (cloud)
            src_repos = await create_repositories(
                "cloud", cloud_connection=cloud_conn
            )
            src_trans_repo, src_planned_repo, src_sheet_repo, src_audit_repo, src_attach_repo = src_repos

            # Export from cloud
            self._log("Exporting data from cloud...")
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
                self._log("Downloading attachment files from cloud storage...")
                from fidra.domain.models import Attachment

                attachments = [
                    self._migration_service._dict_to_attachment(a)
                    for a in data["attachments"]
                ]

                local_dir = self._context.db_path.parent / f"{self._context.db_path.stem}_attachments"
                downloaded, download_errors = await self._migration_service.migrate_attachments_to_local(
                    local_dir,
                    attachments,
                    server_config.storage,
                    progress_callback=self._on_progress,
                )
                result.errors.extend(download_errors)
                self._log(f"Downloaded {downloaded} attachment files")

            self._show_result(result, to_cloud=False)

        finally:
            await cloud_conn.close()

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

    def _show_result(self, result: MigrationResult, to_cloud: bool) -> None:
        """Show migration result."""
        self._stack.setCurrentIndex(3)
        self._update_buttons()

        direction = "to cloud" if to_cloud else "to SQLite"

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
        self._migrated_to_cloud = to_cloud

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
        if self._switch_backend_check.isChecked() and hasattr(self, '_migrated_to_cloud'):
            try:
                if self._migrated_to_cloud:
                    await self._context.switch_to_cloud()
                    server = self._context.active_server
                    server_name = server.name if server else "Cloud"
                    QMessageBox.information(
                        self,
                        "Backend Switched",
                        f"Now using {server_name} backend.\n\n"
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
