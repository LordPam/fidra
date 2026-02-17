"""Cloud servers list and management dialog."""

from typing import TYPE_CHECKING, Optional

import qasync
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext
    from fidra.domain.settings import CloudServerConfig


class CloudServersListDialog(QDialog):
    """Dialog for viewing and managing cloud server configurations.

    Shows a list of configured servers with options to:
    - Connect to a server
    - Add a new server
    - Edit an existing server
    - Delete a server
    """

    # Emitted when user wants to connect to a server
    connect_requested = Signal(str)  # server_id

    def __init__(self, context: "ApplicationContext", parent=None):
        super().__init__(parent)
        self._context = context
        self._selected_server_id: Optional[str] = None

        self.setWindowTitle("Cloud Servers")
        self.setModal(True)
        self.setMinimumSize(520, 400)

        self._setup_ui()
        self._load_servers()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QLabel("Configured Cloud Servers")
        header.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(header)

        # Main content area
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # Server list
        self._server_list = QListWidget()
        self._server_list.setMinimumWidth(280)
        self._server_list.itemSelectionChanged.connect(self._on_selection_changed)
        self._server_list.itemDoubleClicked.connect(self._on_connect)
        content_layout.addWidget(self._server_list, 1)

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(0)  # We'll add explicit spacing
        btn_layout.setContentsMargins(0, 0, 0, 0)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedSize(100, 34)
        self._connect_btn.setEnabled(False)
        self._connect_btn.clicked.connect(self._on_connect)
        btn_layout.addWidget(self._connect_btn)

        btn_layout.addSpacing(24)  # Larger gap before management buttons

        self._add_btn = QPushButton("Add...")
        self._add_btn.setFixedSize(100, 34)
        self._add_btn.clicked.connect(self._on_add)
        btn_layout.addWidget(self._add_btn)

        btn_layout.addSpacing(12)

        self._edit_btn = QPushButton("Edit...")
        self._edit_btn.setFixedSize(100, 34)
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(self._edit_btn)

        btn_layout.addSpacing(12)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setFixedSize(100, 34)
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._delete_btn)

        btn_layout.addStretch()

        content_layout.addLayout(btn_layout)
        layout.addLayout(content_layout, 1)

        # Current status
        if self._context.is_cloud:
            server = self._context.active_server
            status_text = f"Currently connected to: {server.name}" if server else "Connected to cloud"
            self._status_label = QLabel(status_text)
            self._status_label.setStyleSheet("color: #10b981; font-size: 12px;")
        else:
            self._status_label = QLabel("Currently using local SQLite database")
            self._status_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self._status_label)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _load_servers(self) -> None:
        """Load servers into the list."""
        self._server_list.clear()
        servers = self._context.settings.storage.cloud_servers
        active_id = self._context.settings.storage.active_server_id

        for server in servers:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, server.id)

            # Show server name with indicator if it's the active one
            display_text = server.name
            if server.id == active_id and self._context.is_cloud:
                display_text += " (connected)"

            item.setText(display_text)
            self._server_list.addItem(item)

        if not servers:
            # Show placeholder
            item = QListWidgetItem("No servers configured")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setForeground(Qt.GlobalColor.gray)
            self._server_list.addItem(item)

    def _on_selection_changed(self) -> None:
        """Handle selection change in the list."""
        selected = self._server_list.selectedItems()
        has_selection = bool(selected) and selected[0].data(Qt.ItemDataRole.UserRole) is not None

        self._connect_btn.setEnabled(has_selection)
        self._edit_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)

        if has_selection:
            self._selected_server_id = selected[0].data(Qt.ItemDataRole.UserRole)
        else:
            self._selected_server_id = None

    def _on_connect(self) -> None:
        """Connect to the selected server."""
        if self._selected_server_id:
            self.connect_requested.emit(self._selected_server_id)
            self.accept()

    def _on_add(self) -> None:
        """Add a new server."""
        from fidra.ui.dialogs.cloud_server_dialog import CloudServerDialog

        dialog = CloudServerDialog(self._context, parent=self)
        if dialog.exec():
            self._load_servers()

    def _on_edit(self) -> None:
        """Edit the selected server."""
        if not self._selected_server_id:
            return

        # Find the server config
        server = None
        for s in self._context.settings.storage.cloud_servers:
            if s.id == self._selected_server_id:
                server = s
                break

        if server:
            from fidra.ui.dialogs.cloud_server_dialog import CloudServerDialog

            dialog = CloudServerDialog(self._context, server_config=server, parent=self)
            if dialog.exec():
                self._load_servers()

    def _on_delete(self) -> None:
        """Delete the selected server."""
        if not self._selected_server_id:
            return

        # Find server name for confirmation
        server_name = "this server"
        for s in self._context.settings.storage.cloud_servers:
            if s.id == self._selected_server_id:
                server_name = s.name
                break

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete Server",
            f"Are you sure you want to delete '{server_name}'?\n\n"
            "This will only remove the configuration, not the data on the server.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._context.settings.storage.remove_server(self._selected_server_id)
            self._context.save_settings()
            self._load_servers()
            self._selected_server_id = None

    @property
    def selected_server_id(self) -> Optional[str]:
        """Get the ID of the server user wants to connect to."""
        return self._selected_server_id
