"""Backup and restore dialog."""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext

from fidra.services.backup import BackupService


class BackupRestoreDialog(QDialog):
    """Dialog for managing database backups.

    Provides:
    - Create backup button
    - Backup history table with restore/delete actions
    - Settings for backup directory, retention, and auto-backup
    """

    def __init__(self, context: "ApplicationContext", parent=None):
        super().__init__(parent)
        self._context = context
        self._backup_service = context.backup_service
        self._selected_backup_path: Optional[Path] = None

        self.setWindowTitle("Backup & Restore")
        self.setModal(True)
        self.setMinimumSize(700, 500)

        self._setup_ui()
        self._load_backups()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Create Backup section
        backup_group = QGroupBox("Create Backup")
        backup_layout = QHBoxLayout(backup_group)

        self.backup_btn = QPushButton("Backup Now")
        self.backup_btn.setMinimumHeight(36)
        self.backup_btn.clicked.connect(self._on_backup_now)
        backup_layout.addWidget(self.backup_btn)

        self.backup_status = QLabel("")
        self.backup_status.setObjectName("secondary_text")
        backup_layout.addWidget(self.backup_status, 1)

        layout.addWidget(backup_group)

        # Backup History section
        history_group = QGroupBox("Backup History")
        history_layout = QVBoxLayout(history_group)

        # Table for backup list
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(5)
        self.backup_table.setHorizontalHeaderLabels([
            "Date", "DB Size", "Attachments", "Total Size", "Trigger"
        ])
        self.backup_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.backup_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.backup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.backup_table.verticalHeader().setVisible(False)
        self.backup_table.horizontalHeader().setStretchLastSection(True)
        self.backup_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.backup_table.setMinimumHeight(150)
        self.backup_table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        history_layout.addWidget(self.backup_table)

        # Restore/Delete buttons
        button_row = QHBoxLayout()
        button_row.addStretch()

        self.restore_btn = QPushButton("Restore Selected")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self._on_restore)
        button_row.addWidget(self.restore_btn)

        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete)
        button_row.addWidget(self.delete_btn)

        history_layout.addLayout(button_row)
        layout.addWidget(history_group)

        # Settings section
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout(settings_group)

        # Backup folder
        folder_row = QHBoxLayout()
        folder_label = QLabel("Backup folder:")
        folder_label.setMinimumWidth(100)
        folder_row.addWidget(folder_label)

        self.folder_path_label = QLabel()
        self.folder_path_label.setObjectName("secondary_text")
        self._update_folder_label()
        folder_row.addWidget(self.folder_path_label, 1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse_folder)
        folder_row.addWidget(self.browse_btn)

        self.reset_folder_btn = QPushButton("Reset")
        self.reset_folder_btn.setToolTip("Use default location (next to database)")
        self.reset_folder_btn.clicked.connect(self._on_reset_folder)
        folder_row.addWidget(self.reset_folder_btn)

        settings_layout.addLayout(folder_row)

        # Retention
        retention_row = QHBoxLayout()
        retention_label = QLabel("Keep last:")
        retention_label.setMinimumWidth(100)
        retention_row.addWidget(retention_label)

        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 100)
        self.retention_spin.setValue(self._context.settings.backup.retention_count)
        self.retention_spin.setSuffix(" backups")
        self.retention_spin.setMinimumWidth(120)
        retention_row.addWidget(self.retention_spin)
        retention_row.addStretch()

        settings_layout.addLayout(retention_row)

        # Auto-backup checkbox
        self.auto_backup_check = QCheckBox("Automatically backup when closing the app")
        self.auto_backup_check.setChecked(self._context.settings.backup.auto_backup_on_close)
        settings_layout.addWidget(self.auto_backup_check)

        layout.addWidget(settings_group)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _update_folder_label(self) -> None:
        """Update the folder path label."""
        backup_dir = self._context.settings.backup.backup_dir
        if backup_dir:
            self.folder_path_label.setText(str(backup_dir))
        else:
            # Show default location
            default_dir = self._backup_service.backup_dir
            self.folder_path_label.setText(f"{default_dir} (default)")

    def _load_backups(self) -> None:
        """Load and display backup history."""
        backups = self._backup_service.list_backups()

        self.backup_table.setRowCount(len(backups))
        self._backup_paths = []

        for row, (backup_path, metadata) in enumerate(backups):
            self._backup_paths.append(backup_path)

            # Date
            date_str = metadata.created_at.strftime("%Y-%m-%d %H:%M:%S")
            self.backup_table.setItem(row, 0, QTableWidgetItem(date_str))

            # DB Size
            db_size = BackupService.format_size(metadata.db_size)
            self.backup_table.setItem(row, 1, QTableWidgetItem(db_size))

            # Attachments
            if metadata.attachments_count > 0:
                att_str = f"{metadata.attachments_count} ({BackupService.format_size(metadata.attachments_size)})"
            else:
                att_str = "None"
            self.backup_table.setItem(row, 2, QTableWidgetItem(att_str))

            # Total Size
            total_size = metadata.db_size + metadata.attachments_size
            self.backup_table.setItem(row, 3, QTableWidgetItem(BackupService.format_size(total_size)))

            # Trigger
            trigger_display = {
                "manual": "Manual",
                "auto_close": "Auto (close)",
                "pre_restore": "Pre-restore",
            }.get(metadata.trigger, metadata.trigger)
            self.backup_table.setItem(row, 4, QTableWidgetItem(trigger_display))

        # Update status
        if backups:
            self.backup_status.setText(f"{len(backups)} backup(s) available")
        else:
            self.backup_status.setText("No backups yet")

    def _on_selection_changed(self) -> None:
        """Handle backup selection change."""
        selected = self.backup_table.selectedItems()
        has_selection = len(selected) > 0

        self.restore_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

        if has_selection:
            row = self.backup_table.currentRow()
            if 0 <= row < len(self._backup_paths):
                self._selected_backup_path = self._backup_paths[row]
            else:
                self._selected_backup_path = None
        else:
            self._selected_backup_path = None

    @qasync.asyncSlot()
    async def _on_backup_now(self) -> None:
        """Create a manual backup."""
        self.backup_btn.setEnabled(False)
        self.backup_status.setText("Creating backup...")

        try:
            backup_path, metadata = self._backup_service.create_backup(trigger="manual")
            self.backup_status.setText(f"Backup created: {backup_path.name}")
            self._load_backups()
        except Exception as e:
            self.backup_status.setText(f"Backup failed: {e}")
        finally:
            self.backup_btn.setEnabled(True)

    @qasync.asyncSlot()
    async def _on_restore(self) -> None:
        """Restore selected backup."""
        if not self._selected_backup_path:
            return

        # Confirmation dialog
        result = QMessageBox.warning(
            self,
            "Confirm Restore",
            "This will replace your current database and attachments with the backup.\n\n"
            "A backup of the current state will be created first.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        self.backup_status.setText("Restoring backup...")

        try:
            # Create pre-restore backup
            self._backup_service.create_backup(trigger="pre_restore")

            # Close database connection
            await self._context.close()

            # Restore the backup
            self._backup_service.restore_backup(self._selected_backup_path)

            # Reinitialize context with restored database
            await self._context.initialize()

            self.backup_status.setText("Restore complete. Reloading...")

            # Reload backups list
            self._load_backups()

            # Notify parent to refresh UI
            QMessageBox.information(
                self,
                "Restore Complete",
                "The backup has been restored successfully.\n\n"
                "The application data has been reloaded."
            )

        except Exception as e:
            self.backup_status.setText(f"Restore failed: {e}")
            QMessageBox.critical(
                self,
                "Restore Failed",
                f"Failed to restore backup: {e}"
            )

    def _on_delete(self) -> None:
        """Delete selected backup."""
        if not self._selected_backup_path:
            return

        # Confirmation dialog
        result = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete backup '{self._selected_backup_path.name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        try:
            self._backup_service.delete_backup(self._selected_backup_path)
            self.backup_status.setText("Backup deleted")
            self._load_backups()
        except Exception as e:
            self.backup_status.setText(f"Delete failed: {e}")

    def _on_browse_folder(self) -> None:
        """Browse for backup folder."""
        current = self._context.settings.backup.backup_dir or self._backup_service.backup_dir
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Backup Folder",
            str(current),
        )

        if folder:
            self._context.settings.backup.backup_dir = Path(folder)
            self._update_folder_label()

    def _on_reset_folder(self) -> None:
        """Reset backup folder to default."""
        self._context.settings.backup.backup_dir = None
        self._update_folder_label()

    def _on_save(self) -> None:
        """Save settings and close dialog."""
        # Update settings
        self._context.settings.backup.retention_count = self.retention_spin.value()
        self._context.settings.backup.auto_backup_on_close = self.auto_backup_check.isChecked()

        # Save to disk
        self._context.save_settings()

        # Update backup service settings
        self._backup_service.settings = self._context.settings.backup

        self.accept()
