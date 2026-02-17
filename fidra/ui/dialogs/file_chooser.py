"""File chooser dialog for returning users."""

import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QWidget,
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QColor
from PySide6.QtSvgWidgets import QSvgWidget

if TYPE_CHECKING:
    from fidra.domain.settings import CloudServerConfig

# Theme colors from tokens.py
NAVY = "#23395B"
DEEP_NAVY = "#0D1F2F"
GOLD = "#BFA159"
LIGHT_GRAY = "#D3D3D3"
MID_GRAY = "#A9A9A9"
DARK_GRAY = "#4A5568"
CLOUD_ACCENT = "#60A5FA"  # Blue accent for cloud options


def get_resource_path(relative_path: str) -> Path:
    """Get path to resource, works for dev and PyInstaller bundle."""
    try:
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        base_path = Path(__file__).resolve().parent.parent.parent.parent
    return base_path / relative_path


class ServerSelectionDialog(QDialog):
    """Dialog for selecting a cloud server or adding a new one."""

    def __init__(
        self,
        servers: list["CloudServerConfig"],
        active_server_id: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Select Server")
        self.setModal(True)
        self.setFixedWidth(400)

        self._servers = servers
        self._active_server_id = active_server_id
        self._selected_server: Optional["CloudServerConfig"] = None
        self._new_server: Optional["CloudServerConfig"] = None

        self.setStyleSheet(f"""
            QDialog {{
                background: {DEEP_NAVY};
            }}
            QLabel {{
                color: {LIGHT_GRAY};
                background: transparent;
            }}
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QLabel("Select Server")
        header.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {LIGHT_GRAY};")
        layout.addWidget(header)

        # Server buttons
        btn_style = f"""
            QPushButton {{
                background: rgba(35, 57, 91, 0.6);
                color: {LIGHT_GRAY};
                border: 1px solid rgba(169, 169, 169, 0.3);
                border-radius: 8px;
                padding: 12px 16px;
                font-size: 14px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: rgba(35, 57, 91, 0.9);
                border-color: rgba(169, 169, 169, 0.5);
            }}
        """

        # Show all servers except the active one (which is already shown in main dialog)
        for server in self._servers:
            if server.id == self._active_server_id:
                continue  # Skip active server, already shown in main dialog

            name = server.name
            if len(name) > 35:
                name = name[:32] + "..."

            btn = QPushButton(name)
            btn.setStyleSheet(btn_style)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, s=server: self._select_server(s))
            layout.addWidget(btn)

        # Separator
        layout.addSpacing(8)
        separator = QLabel("or")
        separator.setStyleSheet(f"font-size: 12px; color: {DARK_GRAY};")
        separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(separator)
        layout.addSpacing(8)

        # Add new server button
        add_btn = QPushButton("+ Configure New Server...")
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CLOUD_ACCENT};
                color: {DEEP_NAVY};
                border: none;
                border-radius: 8px;
                padding: 12px 16px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #93C5FD;
            }}
        """)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add_new_server)
        layout.addWidget(add_btn)

        layout.addSpacing(8)

        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {MID_GRAY};
                border: none;
                padding: 8px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                color: {LIGHT_GRAY};
            }}
        """)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _select_server(self, server: "CloudServerConfig") -> None:
        """Select an existing server."""
        self._selected_server = server
        self.accept()

    def _add_new_server(self) -> None:
        """Open dialog to add a new server."""
        from fidra.ui.dialogs.cloud_server_dialog import CloudServerDialog

        dialog = CloudServerDialog(parent=self)
        if dialog.exec():
            self._new_server = dialog.get_server_config()
            self.accept()

    @property
    def selected_server(self) -> Optional["CloudServerConfig"]:
        return self._selected_server

    @property
    def new_server(self) -> Optional["CloudServerConfig"]:
        return self._new_server


class FileChooserDialog(QDialog):
    """File chooser for returning users.

    Shows options to:
    - Connect to a configured cloud server (if any)
    - Open the last used file (if provided)
    - Open a different file
    - Create a new database
    """

    def __init__(
        self,
        last_file: Optional[Path] = None,
        cloud_servers: Optional[list["CloudServerConfig"]] = None,
        active_server_id: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Fidra")
        self.setModal(True)

        self._last_file = last_file
        self._cloud_servers = cloud_servers or []
        self._active_server_id = active_server_id
        self._db_path: Optional[Path] = None
        self._selected_server_id: Optional[str] = None
        self._new_server: Optional["CloudServerConfig"] = None  # Track newly added server

        self.setFixedWidth(440)
        self.setMinimumHeight(420)

        # Apply base styling
        self.setStyleSheet(f"""
            QDialog {{
                background: {DEEP_NAVY};
            }}
            QLabel {{
                color: {LIGHT_GRAY};
                background: transparent;
            }}
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 40, 50, 35)
        layout.setSpacing(0)

        # Top spacing
        layout.addStretch(1)

        # Logo container
        logo_container = QWidget()
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.addStretch()

        logo_path = get_resource_path("fidra/ui/theme/icons/icon.svg")
        if logo_path.exists():
            logo = QSvgWidget(str(logo_path))
            logo.setFixedSize(72, 72)
            logo_layout.addWidget(logo)
        else:
            # Fallback text logo
            logo_label = QLabel("F")
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_label.setFixedSize(72, 72)
            logo_label.setStyleSheet(f"""
                font-size: 40px;
                font-weight: bold;
                color: {GOLD};
                background: {NAVY};
                border-radius: 16px;
            """)
            logo_layout.addWidget(logo_label)

        logo_layout.addStretch()
        layout.addWidget(logo_container)

        layout.addSpacing(20)

        # Welcome message
        welcome = QLabel("Welcome back")
        welcome.setStyleSheet(f"""
            font-size: 22px;
            font-weight: 600;
            color: {LIGHT_GRAY};
        """)
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(welcome)

        layout.addSpacing(6)

        subtitle = QLabel("Choose where to continue")
        subtitle.setStyleSheet(f"font-size: 13px; color: {MID_GRAY};")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(28)

        # Button container for consistent width
        btn_container = QWidget()
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(12)

        # Primary button style (gold)
        primary_style = f"""
            QPushButton {{
                background: {GOLD};
                color: {DEEP_NAVY};
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background: #CCAF6A;
            }}
            QPushButton:pressed {{
                background: #A89048;
            }}
        """

        # Cloud button style (blue accent)
        cloud_style = f"""
            QPushButton {{
                background: {CLOUD_ACCENT};
                color: {DEEP_NAVY};
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background: #93C5FD;
            }}
            QPushButton:pressed {{
                background: #3B82F6;
            }}
        """

        # Secondary button style (subtle, no harsh border)
        secondary_style = f"""
            QPushButton {{
                background: rgba(35, 57, 91, 0.6);
                color: {LIGHT_GRAY};
                border: 1px solid rgba(169, 169, 169, 0.3);
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background: rgba(35, 57, 91, 0.9);
                border-color: rgba(169, 169, 169, 0.5);
            }}
            QPushButton:pressed {{
                background: rgba(26, 45, 69, 0.9);
            }}
        """

        # Tertiary button style (text-like)
        tertiary_style = f"""
            QPushButton {{
                background: transparent;
                color: {MID_GRAY};
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 13px;
                min-height: 18px;
            }}
            QPushButton:hover {{
                background: rgba(35, 57, 91, 0.4);
                color: {LIGHT_GRAY};
            }}
            QPushButton:pressed {{
                background: rgba(35, 57, 91, 0.6);
            }}
        """

        has_primary = False

        # Cloud server button (only show active/last-used server)
        if self._cloud_servers:
            # Find the active server
            active_server = None
            for server in self._cloud_servers:
                if server.id == self._active_server_id:
                    active_server = server
                    break

            # If no active server but we have servers, use the first one
            if not active_server and self._cloud_servers:
                active_server = self._cloud_servers[0]

            # Show active server with cloud style
            if active_server:
                name = active_server.name
                if len(name) > 25:
                    name = name[:22] + "..."

                server_btn = QPushButton(f"Connect to {name}")
                server_btn.setStyleSheet(cloud_style)
                server_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                server_btn.clicked.connect(lambda checked, s=active_server: self._connect_to_server(s))
                btn_layout.addWidget(server_btn)
                has_primary = True

            # "Connect to different server" button (if there are other servers or to add new)
            diff_server_btn = QPushButton("Connect to Different Server...")
            diff_server_btn.setStyleSheet(secondary_style)
            diff_server_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            diff_server_btn.clicked.connect(self._show_server_selection)
            btn_layout.addWidget(diff_server_btn)

            # Add separator label
            separator = QLabel("or open a local file")
            separator.setStyleSheet(f"font-size: 11px; color: {DARK_GRAY}; margin-top: 8px;")
            separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_layout.addWidget(separator)

        # Open last file button (if available)
        if self._last_file and self._last_file.exists():
            # Truncate long filenames
            filename = self._last_file.name
            if len(filename) > 30:
                filename = filename[:27] + "..."

            last_btn = QPushButton(f"Open {filename}")
            # Use primary style if no cloud servers, else secondary
            last_btn.setStyleSheet(primary_style if not has_primary else secondary_style)
            last_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            last_btn.clicked.connect(self._open_last_file)
            btn_layout.addWidget(last_btn)
            has_primary = True

            # Other buttons are secondary when last file exists
            open_style = secondary_style
        else:
            # No last file - open button is primary if no cloud
            open_style = primary_style if not has_primary else secondary_style

        # Open different file button
        open_btn = QPushButton("Open Other File...")
        open_btn.setStyleSheet(open_style)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_file)
        btn_layout.addWidget(open_btn)

        # Create new button
        new_btn = QPushButton("Create New Database...")
        new_btn.setStyleSheet(tertiary_style)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self._create_new)
        btn_layout.addWidget(new_btn)

        layout.addWidget(btn_container)

        layout.addStretch(2)

        # Quit link
        quit_btn = QPushButton("Quit")
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {DARK_GRAY};
                border: none;
                padding: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {MID_GRAY};
            }}
        """)
        quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_btn.clicked.connect(self.reject)
        layout.addWidget(quit_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _connect_to_server(self, server: "CloudServerConfig") -> None:
        """Connect to a cloud server."""
        self._selected_server_id = server.id
        self._db_path = None  # No local path for cloud
        self.accept()

    def _show_server_selection(self) -> None:
        """Show dialog to select a different server or add new."""
        dialog = ServerSelectionDialog(
            servers=self._cloud_servers,
            active_server_id=self._active_server_id,
            parent=self,
        )
        if dialog.exec():
            if dialog.selected_server:
                self._selected_server_id = dialog.selected_server.id
                self._db_path = None
                self.accept()
            elif dialog.new_server:
                # User configured a new server - store it so main.py can save it
                self._new_server = dialog.new_server
                self._selected_server_id = dialog.new_server.id
                self._db_path = None
                self.accept()

    def _open_last_file(self) -> None:
        """Open the last used file."""
        self._db_path = self._last_file
        self._selected_server_id = None
        self.accept()

    def _open_file(self) -> None:
        """Show dialog to open an existing file."""
        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path.home()

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Database",
            str(default_dir),
            "All Databases (*.fdra *.db);;Fidra Files (*.fdra);;Legacy Database (*.db);;All Files (*)"
        )

        if file_path:
            self._db_path = Path(file_path)
            self._selected_server_id = None
            self.accept()

    def _create_new(self) -> None:
        """Show dialog to create a new database."""
        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path.home()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Create New Database",
            str(default_dir / "finances.fdra"),
            "Fidra Files (*.fdra);;All Files (*)"
        )

        if file_path:
            path = Path(file_path)
            # Ensure .fdra extension
            if not path.suffix:
                path = path.with_suffix('.fdra')
            self._db_path = path
            self._selected_server_id = None
            self.accept()

    @property
    def db_path(self) -> Optional[Path]:
        """Get the selected database path (None if cloud server selected)."""
        return self._db_path

    @property
    def selected_server_id(self) -> Optional[str]:
        """Get the selected cloud server ID (None if local file selected)."""
        return self._selected_server_id

    @property
    def is_cloud(self) -> bool:
        """Check if a cloud server was selected."""
        return self._selected_server_id is not None

    @property
    def new_server(self) -> Optional["CloudServerConfig"]:
        """Get newly configured server (if any) - needs to be saved to settings."""
        return self._new_server
