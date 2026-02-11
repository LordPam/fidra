"""Supabase configuration dialog."""

from typing import TYPE_CHECKING

import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class SupabaseConfigDialog(QDialog):
    """Dialog for configuring Supabase connection settings.

    Provides:
    - Project URL, Anon Key, and Database connection string inputs
    - Test connection button
    - Connection pool settings
    """

    def __init__(self, context: "ApplicationContext", parent=None):
        super().__init__(parent)
        self._context = context
        self._supabase_settings = context.settings.storage.supabase

        self.setWindowTitle("Configure Supabase")
        self.setModal(True)
        self.setMinimumWidth(550)

        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Connection settings
        conn_group = QGroupBox("Connection Settings")
        conn_layout = QFormLayout(conn_group)
        conn_layout.setSpacing(12)

        # Project URL
        self.project_url_input = QLineEdit()
        self.project_url_input.setPlaceholderText("https://your-project.supabase.co")
        conn_layout.addRow("Project URL:", self.project_url_input)

        # Anon Key
        self.anon_key_input = QLineEdit()
        self.anon_key_input.setPlaceholderText("eyJhbGciOiJIUzI1NiIsInR5cCI6...")
        self.anon_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        conn_layout.addRow("Anon Key:", self.anon_key_input)

        # Toggle visibility for anon key
        show_key_btn = QPushButton("Show")
        show_key_btn.setCheckable(True)
        show_key_btn.toggled.connect(
            lambda checked: self.anon_key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        show_key_btn.toggled.connect(
            lambda checked: show_key_btn.setText("Hide" if checked else "Show")
        )

        key_row = QHBoxLayout()
        key_row.addWidget(self.anon_key_input)
        key_row.addWidget(show_key_btn)
        conn_layout.addRow("Anon Key:", key_row)

        # Remove duplicate anon key row
        conn_layout.removeRow(1)

        # Database connection string
        self.db_conn_input = QLineEdit()
        self.db_conn_input.setPlaceholderText("postgresql://postgres:password@db.xxx.supabase.co:5432/postgres")
        self.db_conn_input.setEchoMode(QLineEdit.EchoMode.Password)

        show_conn_btn = QPushButton("Show")
        show_conn_btn.setCheckable(True)
        show_conn_btn.toggled.connect(
            lambda checked: self.db_conn_input.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        show_conn_btn.toggled.connect(
            lambda checked: show_conn_btn.setText("Hide" if checked else "Show")
        )

        conn_row = QHBoxLayout()
        conn_row.addWidget(self.db_conn_input)
        conn_row.addWidget(show_conn_btn)
        conn_layout.addRow("DB Connection:", conn_row)

        # Storage bucket
        self.bucket_input = QLineEdit()
        self.bucket_input.setPlaceholderText("attachments")
        conn_layout.addRow("Storage Bucket:", self.bucket_input)

        layout.addWidget(conn_group)

        # Test connection section
        test_group = QGroupBox("Test Connection")
        test_layout = QHBoxLayout(test_group)

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        test_layout.addWidget(self.test_btn)

        self.test_status = QLabel("")
        self.test_status.setObjectName("secondary_text")
        test_layout.addWidget(self.test_status, 1)

        layout.addWidget(test_group)

        # Pool settings
        pool_group = QGroupBox("Connection Pool")
        pool_layout = QFormLayout(pool_group)

        self.pool_min_spin = QSpinBox()
        self.pool_min_spin.setRange(1, 10)
        self.pool_min_spin.setValue(2)
        pool_layout.addRow("Min connections:", self.pool_min_spin)

        self.pool_max_spin = QSpinBox()
        self.pool_max_spin.setRange(2, 50)
        self.pool_max_spin.setValue(10)
        pool_layout.addRow("Max connections:", self.pool_max_spin)

        layout.addWidget(pool_group)

        # Help text
        help_label = QLabel(
            "Find these values in your Supabase project settings:\n"
            "Settings > API > Project URL and Project API keys (anon, public)\n"
            "Settings > Database > Connection string"
        )
        help_label.setObjectName("secondary_text")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # Current status
        if self._context.is_supabase:
            status_label = QLabel("Currently connected to Supabase")
            status_label.setStyleSheet("color: #10b981; font-weight: 600;")
        else:
            status_label = QLabel("Currently using local SQLite database")
            status_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(status_label)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_current_settings(self) -> None:
        """Load current Supabase settings into form."""
        self.project_url_input.setText(self._supabase_settings.project_url or "")
        self.anon_key_input.setText(self._supabase_settings.anon_key or "")
        self.db_conn_input.setText(self._supabase_settings.db_connection_string or "")
        self.bucket_input.setText(self._supabase_settings.storage_bucket or "attachments")
        self.pool_min_spin.setValue(self._supabase_settings.pool_min_size)
        self.pool_max_spin.setValue(self._supabase_settings.pool_max_size)

    @qasync.asyncSlot()
    async def _on_test_connection(self) -> None:
        """Test the Supabase connection."""
        self.test_btn.setEnabled(False)
        self.test_status.setText("Testing connection...")
        self.test_status.setStyleSheet("")

        db_conn_string = self.db_conn_input.text().strip()
        if not db_conn_string:
            self.test_status.setText("Please enter a database connection string")
            self.test_status.setStyleSheet("color: #ef4444;")
            self.test_btn.setEnabled(True)
            return

        try:
            from fidra.data.supabase_connection import SupabaseConnection
            from fidra.domain.settings import SupabaseSettings

            # Create temporary config for testing
            test_config = SupabaseSettings(
                db_connection_string=db_conn_string,
                pool_min_size=1,
                pool_max_size=2,
            )

            conn = SupabaseConnection(test_config)
            await conn.connect()

            # Test with a simple query
            healthy = await conn.health_check()

            await conn.close()

            if healthy:
                self.test_status.setText("Connection successful!")
                self.test_status.setStyleSheet("color: #10b981;")
            else:
                self.test_status.setText("Connection established but health check failed")
                self.test_status.setStyleSheet("color: #f59e0b;")

        except Exception as e:
            self.test_status.setText(f"Connection failed: {e}")
            self.test_status.setStyleSheet("color: #ef4444;")
        finally:
            self.test_btn.setEnabled(True)

    def _on_save(self) -> None:
        """Save settings and close dialog."""
        # Update settings
        self._supabase_settings.project_url = self.project_url_input.text().strip() or None
        self._supabase_settings.anon_key = self.anon_key_input.text().strip() or None
        self._supabase_settings.db_connection_string = self.db_conn_input.text().strip() or None
        self._supabase_settings.storage_bucket = self.bucket_input.text().strip() or "attachments"
        self._supabase_settings.pool_min_size = self.pool_min_spin.value()
        self._supabase_settings.pool_max_size = self.pool_max_spin.value()

        # Save to disk
        self._context.save_settings()

        QMessageBox.information(
            self,
            "Settings Saved",
            "Supabase settings have been saved.\n\n"
            "Use 'Migrate Data...' to transfer your data to Supabase,\n"
            "or the app will use Supabase on next launch if configured."
        )

        self.accept()
