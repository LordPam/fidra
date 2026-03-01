"""Cloud server configuration dialog."""

import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from uuid import uuid4

import qasync
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer
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
    QWidget,
)

from fidra.domain.settings import CloudServerConfig, CloudStorageProvider

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


def _get_icon_path(name: str) -> Path:
    """Get path to an icon file."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "fidra"
    else:
        # Go up from fidra/ui/dialogs to fidra
        base = Path(__file__).resolve().parent.parent.parent
    return base / "ui" / "theme" / "icons" / f"{name}.svg"


def _load_svg_icon(name: str, size: int = 18) -> QIcon:
    """Load an SVG icon and return as QIcon."""
    path = _get_icon_path(name)
    if not path.exists():
        return QIcon()

    renderer = QSvgRenderer(str(path))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    from PySide6.QtGui import QPainter
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class PasswordLineEdit(QLineEdit):
    """QLineEdit with a visibility toggle button (eye icon)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self._visible = False

        # Add toggle action
        self._eye_open = _load_svg_icon("eye-open")
        self._eye_closed = _load_svg_icon("eye-closed")

        self._toggle_action = self.addAction(
            self._eye_closed, QLineEdit.ActionPosition.TrailingPosition
        )
        self._toggle_action.setToolTip("Show/hide")
        self._toggle_action.triggered.connect(self._toggle_visibility)

    def _toggle_visibility(self) -> None:
        """Toggle password visibility."""
        self._visible = not self._visible
        if self._visible:
            self.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_action.setIcon(self._eye_open)
        else:
            self.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_action.setIcon(self._eye_closed)


class CloudServerDialog(QDialog):
    """Dialog for configuring a cloud server connection.

    Can be used to add a new server or edit an existing one.
    """

    def __init__(
        self,
        context: "ApplicationContext" = None,
        server_config: Optional[CloudServerConfig] = None,
        parent=None,
        wizard_theme: bool = False,
    ):
        super().__init__(parent)
        self._context = context
        self._server_config = server_config
        self._is_new = server_config is None

        title = "Add Cloud Server" if self._is_new else "Edit Cloud Server"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)

        # Apply dark theme only when explicitly requested (setup wizard)
        if wizard_theme:
            self._apply_wizard_theme()

        self._setup_ui()
        self._load_current_settings()

    def _apply_wizard_theme(self) -> None:
        """Apply dark styling to match the setup wizard theme."""
        self.setStyleSheet("""
            QDialog {
                background: #0D1F2F;
            }
            QGroupBox {
                background: #23395B;
                border: 1px solid #A9A9A9;
                border-radius: 8px;
                margin-top: 14px;
                padding: 16px 14px 14px;
                font-size: 13px;
                font-weight: 600;
                color: #D3D3D3;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 10px;
                color: #BFA159;
            }
            QLabel {
                color: #D3D3D3;
                font-size: 12px;
                background: transparent;
            }
            QLineEdit {
                background: #0D1F2F;
                border: 1px solid #A9A9A9;
                border-radius: 6px;
                padding: 8px 10px;
                font-size: 12px;
                color: #D3D3D3;
            }
            QLineEdit:focus {
                border-color: #BFA159;
            }
            QLineEdit::placeholder {
                color: #A9A9A9;
            }
            QSpinBox {
                background: #0D1F2F;
                border: 1px solid #A9A9A9;
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 12px;
                color: #D3D3D3;
            }
            QSpinBox:focus {
                border-color: #BFA159;
            }
            QPushButton {
                background: #BFA159;
                color: #0D1F2F;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #CDB169;
            }
            QPushButton:disabled {
                background: #23395B;
                color: #A9A9A9;
            }
            QDialogButtonBox QPushButton {
                min-width: 80px;
            }
        """)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Server settings
        server_group = QGroupBox("Database Connection")
        server_layout = QFormLayout(server_group)
        server_layout.setSpacing(8)
        server_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Server Name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., Sub Aqua Club")
        server_layout.addRow("Name:", self.name_input)

        # Database connection string with eye toggle
        self.db_conn_input = PasswordLineEdit()
        self.db_conn_input.setPlaceholderText("postgresql://user:password@host:5432/database")
        server_layout.addRow("Connection:", self.db_conn_input)

        # Pool settings - aligned with other fields
        pool_widget = QWidget()
        pool_layout = QHBoxLayout(pool_widget)
        pool_layout.setContentsMargins(0, 0, 0, 0)
        pool_layout.setSpacing(8)

        self.pool_min_spin = QSpinBox()
        self.pool_min_spin.setRange(1, 10)
        self.pool_min_spin.setValue(2)
        self.pool_min_spin.setFixedWidth(60)
        pool_layout.addWidget(self.pool_min_spin)

        pool_layout.addWidget(QLabel("-"))

        self.pool_max_spin = QSpinBox()
        self.pool_max_spin.setRange(2, 50)
        self.pool_max_spin.setValue(10)
        self.pool_max_spin.setFixedWidth(60)
        pool_layout.addWidget(self.pool_max_spin)

        pool_layout.addWidget(QLabel("connections"))
        pool_layout.addStretch()

        server_layout.addRow("Pool:", pool_widget)

        layout.addWidget(server_group)

        # File storage settings (Supabase Storage)
        storage_group = QGroupBox("File Storage (Supabase)")
        storage_layout = QFormLayout(storage_group)
        storage_layout.setSpacing(8)
        storage_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # URL
        self.project_url_input = QLineEdit()
        self.project_url_input.setPlaceholderText("https://xxx.supabase.co")
        storage_layout.addRow("URL:", self.project_url_input)

        # Anon Key with eye toggle
        self.anon_key_input = PasswordLineEdit()
        self.anon_key_input.setPlaceholderText("eyJhbGciOiJIUzI1NiIs...")
        storage_layout.addRow("Anon Key:", self.anon_key_input)

        # Bucket - full width like others
        self.bucket_input = QLineEdit()
        self.bucket_input.setPlaceholderText("attachments")
        storage_layout.addRow("Bucket:", self.bucket_input)

        layout.addWidget(storage_group)

        # Test connection - compact inline
        test_row = QHBoxLayout()
        test_row.setSpacing(8)

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._on_test_connection)
        test_row.addWidget(self.test_btn)

        self.test_status = QLabel("")
        self.test_status.setObjectName("secondary_text")
        test_row.addWidget(self.test_status, 1)

        layout.addLayout(test_row)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_current_settings(self) -> None:
        """Load existing server config into form."""
        if self._server_config:
            self.name_input.setText(self._server_config.name or "")
            self.db_conn_input.setText(self._server_config.db_connection_string or "")
            self.pool_min_spin.setValue(self._server_config.pool_min_size)
            self.pool_max_spin.setValue(self._server_config.pool_max_size)

            # Storage settings
            storage = self._server_config.storage
            self.project_url_input.setText(storage.project_url or "")
            self.anon_key_input.setText(storage.anon_key or "")
            self.bucket_input.setText(storage.bucket or "attachments")

    @qasync.asyncSlot()
    async def _on_test_connection(self) -> None:
        """Test the database connection."""
        self.test_btn.setEnabled(False)
        self.test_status.setText("Testing...")
        self.test_status.setStyleSheet("")

        db_conn_string = self.db_conn_input.text().strip()
        if not db_conn_string:
            self.test_status.setText("Enter connection string first")
            self.test_status.setStyleSheet("color: #ef4444;")
            self.test_btn.setEnabled(True)
            return

        try:
            from fidra.data.cloud_connection import CloudConnection

            test_config = CloudServerConfig(
                id="test",
                name="Test",
                db_connection_string=db_conn_string,
                pool_min_size=1,
                pool_max_size=2,
            )

            conn = CloudConnection(test_config)
            await conn.connect()
            healthy = await conn.health_check()
            await conn.close()

            if healthy:
                self.test_status.setText("Success!")
                self.test_status.setStyleSheet("color: #10b981;")
            else:
                self.test_status.setText("Connected but health check failed")
                self.test_status.setStyleSheet("color: #f59e0b;")

        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            self.test_status.setText(f"Failed: {error_msg}")
            self.test_status.setStyleSheet("color: #ef4444;")
        finally:
            self.test_btn.setEnabled(True)

    def _on_save(self) -> None:
        """Save settings and close dialog."""
        name = self.name_input.text().strip()
        db_conn = self.db_conn_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Validation Error", "Please enter a server name.")
            return

        if not db_conn:
            QMessageBox.warning(self, "Validation Error", "Please enter a database connection string.")
            return

        # Create storage config
        storage = CloudStorageProvider(
            provider="supabase",
            project_url=self.project_url_input.text().strip() or None,
            anon_key=self.anon_key_input.text().strip() or None,
            bucket=self.bucket_input.text().strip() or "attachments",
        )

        if self._is_new:
            from datetime import datetime
            server = CloudServerConfig(
                id=uuid4().hex,
                name=name,
                db_connection_string=db_conn,
                storage=storage,
                pool_min_size=self.pool_min_spin.value(),
                pool_max_size=self.pool_max_spin.value(),
                created_at=datetime.now().isoformat(),
            )
            if self._context:
                self._context.settings.storage.add_server(server)
            self._server_config = server
        else:
            self._server_config.name = name
            self._server_config.db_connection_string = db_conn
            self._server_config.storage = storage
            self._server_config.pool_min_size = self.pool_min_spin.value()
            self._server_config.pool_max_size = self.pool_max_spin.value()

        if self._context:
            self._context.save_settings()
        self.accept()

    @property
    def server_config(self) -> Optional[CloudServerConfig]:
        """Get the created/updated server config."""
        return self._server_config
