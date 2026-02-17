"""First-run setup wizard for new installations."""

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QFrame,
    QStackedWidget,
    QWidget,
    QSizePolicy,
)
from PySide6.QtSvgWidgets import QSvgWidget

# Theme colors from tokens.py
NAVY = "#23395B"
DEEP_NAVY = "#0D1F2F"
GOLD = "#BFA159"
LIGHT_GRAY = "#D3D3D3"
MID_GRAY = "#A9A9A9"
CLOUD_ACCENT = "#60A5FA"


def get_resource_path(relative_path: str) -> Path:
    """Get path to resource, works for dev and PyInstaller bundle."""
    try:
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        base_path = Path(__file__).resolve().parent.parent.parent.parent
    return base_path / relative_path


class SetupWizard(QDialog):
    """First-run setup wizard.

    Guides new users through:
    1. Welcome screen with logo
    2. Database selection (create new or open existing)
    3. Profile setup (name and initials)
    """

    # Emitted when setup is complete with (db_path, name, initials)
    setup_complete = Signal(Path, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Fidra")
        self.setModal(True)
        self.setFixedSize(520, 480)

        # Apply base styling
        self.setStyleSheet(f"""
            QDialog {{
                background: {DEEP_NAVY};
            }}
            QLabel {{
                color: {LIGHT_GRAY};
            }}
        """)

        # Result data
        self._db_path: Optional[Path] = None
        self._cloud_server = None  # CloudServerConfig if user chose cloud
        self._name: str = ""
        self._initials: str = ""

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the wizard UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget for wizard pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # Page 1: Welcome
        self.stack.addWidget(self._create_welcome_page())

        # Page 2: Database selection
        self.stack.addWidget(self._create_database_page())

        # Page 3: Profile setup
        self.stack.addWidget(self._create_profile_page())

    def _create_welcome_page(self) -> QWidget:
        """Create the welcome page with logo."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        layout.addStretch(1)

        # Logo
        logo_container = QWidget()
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.addStretch()

        logo_path = get_resource_path("fidra/ui/theme/icons/icon.svg")
        if logo_path.exists():
            logo = QSvgWidget(str(logo_path))
            logo.setFixedSize(100, 100)
            logo_layout.addWidget(logo)
        else:
            # Fallback text logo
            logo_label = QLabel("F")
            logo_label.setAlignment(Qt.AlignCenter)
            logo_label.setFixedSize(100, 100)
            logo_label.setStyleSheet(f"""
                font-size: 56px;
                font-weight: bold;
                color: {GOLD};
                background: {NAVY};
                border-radius: 20px;
            """)
            logo_layout.addWidget(logo_label)

        logo_layout.addStretch()
        layout.addWidget(logo_container)

        layout.addSpacing(16)

        # Welcome text
        title = QLabel("Welcome to Fidra")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {LIGHT_GRAY};")
        layout.addWidget(title)

        subtitle = QLabel("Simple, powerful financial tracking for organisations")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"font-size: 13px; color: {MID_GRAY};")
        layout.addWidget(subtitle)

        layout.addStretch(1)

        # Get Started button
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()

        get_started_btn = QPushButton("Get Started")
        get_started_btn.setMinimumWidth(180)
        get_started_btn.setMinimumHeight(40)
        get_started_btn.setCursor(Qt.PointingHandCursor)
        get_started_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GOLD};
                color: {DEEP_NAVY};
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                padding: 10px 24px;
            }}
            QPushButton:hover {{
                background: #CDB169;
            }}
            QPushButton:pressed {{
                background: #A89049;
            }}
        """)
        get_started_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        btn_layout.addWidget(get_started_btn)

        btn_layout.addStretch()
        layout.addWidget(btn_container)

        layout.addStretch(1)

        return page

    def _create_database_page(self) -> QWidget:
        """Create the database selection page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(12)

        # Header
        title = QLabel("Choose Your Database")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {LIGHT_GRAY};")
        layout.addWidget(title)

        subtitle = QLabel("Fidra stores your financial data in a database file.\nYou can create a new one or open an existing file.")
        subtitle.setStyleSheet(f"font-size: 12px; color: {MID_GRAY};")
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        # Create New card
        new_card = QFrame()
        new_card.setStyleSheet(f"""
            QFrame {{
                background: {NAVY};
                border: 1px solid {MID_GRAY};
                border-radius: 8px;
            }}
        """)
        new_layout = QVBoxLayout(new_card)
        new_layout.setContentsMargins(16, 14, 16, 14)
        new_layout.setSpacing(6)

        new_title = QLabel("Create New Database")
        new_title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {LIGHT_GRAY}; background: transparent; border: none;")
        new_layout.addWidget(new_title)

        new_desc = QLabel("Start fresh with a new financial ledger")
        new_desc.setStyleSheet(f"font-size: 12px; color: {MID_GRAY}; background: transparent; border: none;")
        new_layout.addWidget(new_desc)

        new_btn = QPushButton("Create New")
        new_btn.setMinimumHeight(32)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GOLD};
                color: {DEEP_NAVY};
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: #CDB169;
            }}
        """)
        new_btn.clicked.connect(self._create_new_database)
        new_layout.addWidget(new_btn, alignment=Qt.AlignLeft)

        layout.addWidget(new_card)

        layout.addSpacing(8)

        # Open Existing card
        open_card = QFrame()
        open_card.setStyleSheet(f"""
            QFrame {{
                background: {NAVY};
                border: 1px solid {MID_GRAY};
                border-radius: 8px;
            }}
        """)
        open_layout = QVBoxLayout(open_card)
        open_layout.setContentsMargins(16, 14, 16, 14)
        open_layout.setSpacing(6)

        open_title = QLabel("Open Existing Database")
        open_title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {LIGHT_GRAY}; background: transparent; border: none;")
        open_layout.addWidget(open_title)

        open_desc = QLabel("Continue with an existing Fidra database file")
        open_desc.setStyleSheet(f"font-size: 12px; color: {MID_GRAY}; background: transparent; border: none;")
        open_layout.addWidget(open_desc)

        open_btn = QPushButton("Browse...")
        open_btn.setMinimumHeight(32)
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {LIGHT_GRAY};
                border: 1px solid {MID_GRAY};
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {DEEP_NAVY};
                border-color: {LIGHT_GRAY};
            }}
        """)
        open_btn.clicked.connect(self._open_existing_database)
        open_layout.addWidget(open_btn, alignment=Qt.AlignLeft)

        layout.addWidget(open_card)

        layout.addSpacing(8)

        # Connect to Cloud card
        cloud_card = QFrame()
        cloud_card.setStyleSheet(f"""
            QFrame {{
                background: {NAVY};
                border: 1px solid {CLOUD_ACCENT};
                border-radius: 8px;
            }}
        """)
        cloud_layout = QVBoxLayout(cloud_card)
        cloud_layout.setContentsMargins(16, 14, 16, 14)
        cloud_layout.setSpacing(6)

        cloud_title = QLabel("Connect to Cloud Server")
        cloud_title.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {LIGHT_GRAY}; background: transparent; border: none;")
        cloud_layout.addWidget(cloud_title)

        cloud_desc = QLabel("Connect to a shared cloud database (Supabase)")
        cloud_desc.setStyleSheet(f"font-size: 12px; color: {MID_GRAY}; background: transparent; border: none;")
        cloud_layout.addWidget(cloud_desc)

        cloud_btn = QPushButton("Configure Server...")
        cloud_btn.setMinimumHeight(32)
        cloud_btn.setCursor(Qt.PointingHandCursor)
        cloud_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CLOUD_ACCENT};
                color: {DEEP_NAVY};
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: #93C5FD;
            }}
        """)
        cloud_btn.clicked.connect(self._configure_cloud_server)
        cloud_layout.addWidget(cloud_btn, alignment=Qt.AlignLeft)

        layout.addWidget(cloud_card)

        layout.addStretch(1)

        # Selected path display
        self.db_path_label = QLabel("")
        self.db_path_label.setStyleSheet(f"font-size: 11px; color: {GOLD};")
        self.db_path_label.setWordWrap(True)
        self.db_path_label.hide()
        layout.addWidget(self.db_path_label)

        layout.addSpacing(8)

        # Navigation
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(12)

        back_btn = QPushButton("Back")
        back_btn.setMinimumHeight(36)
        back_btn.setMinimumWidth(80)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {MID_GRAY};
                border: 1px solid {MID_GRAY};
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {NAVY};
                color: {LIGHT_GRAY};
            }}
        """)
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        nav_layout.addWidget(back_btn)

        nav_layout.addStretch()

        self.db_next_btn = QPushButton("Next")
        self.db_next_btn.setEnabled(False)
        self.db_next_btn.setMinimumHeight(36)
        self.db_next_btn.setMinimumWidth(80)
        self.db_next_btn.setCursor(Qt.PointingHandCursor)
        self.db_next_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GOLD};
                color: {DEEP_NAVY};
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: #CDB169;
            }}
            QPushButton:disabled {{
                background: {NAVY};
                color: {MID_GRAY};
            }}
        """)
        self.db_next_btn.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        nav_layout.addWidget(self.db_next_btn)

        layout.addLayout(nav_layout)

        return page

    def _create_profile_page(self) -> QWidget:
        """Create the profile setup page."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(12)

        # Header
        title = QLabel("Set Up Your Profile")
        title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {LIGHT_GRAY};")
        layout.addWidget(title)

        subtitle = QLabel("Your name and initials are used for audit trails\nwhen you make changes to the ledger.")
        subtitle.setStyleSheet(f"font-size: 12px; color: {MID_GRAY};")
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        # Form
        # Name field
        name_label = QLabel("Your Name")
        name_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {LIGHT_GRAY};")
        layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g., John Smith")
        self.name_input.setMinimumHeight(38)
        self.name_input.setStyleSheet(f"""
            QLineEdit {{
                background: {NAVY};
                border: 1px solid {MID_GRAY};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {LIGHT_GRAY};
            }}
            QLineEdit:focus {{
                border-color: {GOLD};
            }}
            QLineEdit::placeholder {{
                color: {MID_GRAY};
            }}
        """)
        self.name_input.textChanged.connect(self._on_profile_changed)
        layout.addWidget(self.name_input)

        layout.addSpacing(12)

        # Initials field
        initials_label = QLabel("Initials")
        initials_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {LIGHT_GRAY};")
        layout.addWidget(initials_label)

        self.initials_input = QLineEdit()
        self.initials_input.setPlaceholderText("e.g., JS")
        self.initials_input.setMaxLength(4)
        self.initials_input.setMinimumHeight(38)
        self.initials_input.setStyleSheet(f"""
            QLineEdit {{
                background: {NAVY};
                border: 1px solid {MID_GRAY};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {LIGHT_GRAY};
            }}
            QLineEdit:focus {{
                border-color: {GOLD};
            }}
            QLineEdit::placeholder {{
                color: {MID_GRAY};
            }}
        """)
        self.initials_input.textChanged.connect(self._on_profile_changed)
        layout.addWidget(self.initials_input)

        initials_hint = QLabel("These appear in the audit log for each change you make")
        initials_hint.setStyleSheet(f"font-size: 11px; color: {MID_GRAY};")
        layout.addWidget(initials_hint)

        layout.addStretch(1)

        # Navigation
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(12)

        back_btn = QPushButton("Back")
        back_btn.setMinimumHeight(36)
        back_btn.setMinimumWidth(80)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {MID_GRAY};
                border: 1px solid {MID_GRAY};
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {NAVY};
                color: {LIGHT_GRAY};
            }}
        """)
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        nav_layout.addWidget(back_btn)

        nav_layout.addStretch()

        self.finish_btn = QPushButton("Start Using Fidra")
        self.finish_btn.setEnabled(False)
        self.finish_btn.setMinimumHeight(36)
        self.finish_btn.setMinimumWidth(140)
        self.finish_btn.setCursor(Qt.PointingHandCursor)
        self.finish_btn.setStyleSheet(f"""
            QPushButton {{
                background: {GOLD};
                color: {DEEP_NAVY};
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: #CDB169;
            }}
            QPushButton:disabled {{
                background: {NAVY};
                color: {MID_GRAY};
            }}
        """)
        self.finish_btn.clicked.connect(self._finish_setup)
        nav_layout.addWidget(self.finish_btn)

        layout.addLayout(nav_layout)

        return page

    def _create_new_database(self) -> None:
        """Show dialog to create a new database file."""
        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path.home()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Create New Database",
            str(default_dir / "finances.fdra"),
            "Fidra Files (*.fdra);;Legacy Database (*.db);;All Files (*)"
        )

        if file_path:
            self._db_path = Path(file_path)
            self._cloud_server = None  # Clear any cloud config
            self.db_path_label.setText(f"New database: {self._db_path}")
            self.db_path_label.show()
            self.db_next_btn.setEnabled(True)

    def _open_existing_database(self) -> None:
        """Show dialog to open an existing database file."""
        default_dir = Path.home() / "Documents"
        if not default_dir.exists():
            default_dir = Path.home()

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Existing Database",
            str(default_dir),
            "All Databases (*.fdra *.db);;Fidra Files (*.fdra);;Legacy Database (*.db);;All Files (*)"
        )

        if file_path:
            self._db_path = Path(file_path)
            self._cloud_server = None  # Clear any cloud config
            self.db_path_label.setText(f"Selected: {self._db_path}")
            self.db_path_label.show()
            self.db_next_btn.setEnabled(True)

    def _configure_cloud_server(self) -> None:
        """Show dialog to configure a cloud server."""
        from fidra.ui.dialogs.cloud_server_dialog import CloudServerDialog

        dialog = CloudServerDialog(parent=self)
        if dialog.exec():
            self._cloud_server = dialog.get_server_config()
            self._db_path = None  # Clear any local path
            self.db_path_label.setText(f"Cloud: {self._cloud_server.name}")
            self.db_path_label.show()
            self.db_next_btn.setEnabled(True)

    def _on_profile_changed(self) -> None:
        """Handle profile input changes."""
        name = self.name_input.text().strip()
        initials = self.initials_input.text().strip()

        # Auto-generate initials from name if empty
        if name and not initials:
            parts = name.split()
            if len(parts) >= 2:
                suggested = (parts[0][0] + parts[-1][0]).upper()
                self.initials_input.setPlaceholderText(f"e.g., {suggested}")

        # Enable finish button if we have at least a name
        self.finish_btn.setEnabled(bool(name))

    def _finish_setup(self) -> None:
        """Complete the setup wizard."""
        self._name = self.name_input.text().strip()
        self._initials = self.initials_input.text().strip()

        # If no initials provided, generate from name
        if not self._initials and self._name:
            parts = self._name.split()
            if len(parts) >= 2:
                self._initials = (parts[0][0] + parts[-1][0]).upper()
            elif parts:
                self._initials = parts[0][:2].upper()

        self.setup_complete.emit(self._db_path, self._name, self._initials)
        self.accept()

    @property
    def db_path(self) -> Optional[Path]:
        """Get the selected database path (None if cloud server selected)."""
        return self._db_path

    @property
    def cloud_server(self):
        """Get the configured cloud server (None if local file selected)."""
        return self._cloud_server

    @property
    def is_cloud(self) -> bool:
        """Check if user chose cloud server."""
        return self._cloud_server is not None

    @property
    def user_name(self) -> str:
        """Get the user's name."""
        return self._name

    @property
    def user_initials(self) -> str:
        """Get the user's initials."""
        return self._initials
