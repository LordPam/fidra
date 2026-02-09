"""File chooser dialog for returning users."""

import sys
from pathlib import Path
from typing import Optional

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

# Theme colors from tokens.py
NAVY = "#23395B"
DEEP_NAVY = "#0D1F2F"
GOLD = "#BFA159"
LIGHT_GRAY = "#D3D3D3"
MID_GRAY = "#A9A9A9"
DARK_GRAY = "#4A5568"


def get_resource_path(relative_path: str) -> Path:
    """Get path to resource, works for dev and PyInstaller bundle."""
    try:
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        base_path = Path(__file__).resolve().parent.parent.parent.parent
    return base_path / relative_path


class FileChooserDialog(QDialog):
    """Simple file chooser for returning users.

    Shows options to:
    - Open the last used file (if provided)
    - Open a different file
    - Create a new database
    """

    def __init__(self, last_file: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fidra")
        self.setModal(True)
        self.setFixedSize(440, 420)

        self._last_file = last_file
        self._db_path: Optional[Path] = None

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

        subtitle = QLabel("Choose a file to continue")
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
                padding: 14px 24px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #CCAF6A;
            }}
            QPushButton:pressed {{
                background: #A89048;
            }}
        """

        # Secondary button style (subtle, no harsh border)
        secondary_style = f"""
            QPushButton {{
                background: rgba(35, 57, 91, 0.6);
                color: {LIGHT_GRAY};
                border: 1px solid rgba(169, 169, 169, 0.3);
                border-radius: 8px;
                padding: 14px 24px;
                font-size: 14px;
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
                padding: 12px 24px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: rgba(35, 57, 91, 0.4);
                color: {LIGHT_GRAY};
            }}
            QPushButton:pressed {{
                background: rgba(35, 57, 91, 0.6);
            }}
        """

        # Open last file button (if available)
        if self._last_file and self._last_file.exists():
            # Truncate long filenames
            filename = self._last_file.name
            if len(filename) > 30:
                filename = filename[:27] + "..."

            last_btn = QPushButton(f"Open {filename}")
            last_btn.setStyleSheet(primary_style)
            last_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            last_btn.clicked.connect(self._open_last_file)
            btn_layout.addWidget(last_btn)

            # Other buttons are secondary when last file exists
            open_style = secondary_style
        else:
            # No last file - open button is primary
            open_style = primary_style

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

    def _open_last_file(self) -> None:
        """Open the last used file."""
        self._db_path = self._last_file
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
            self.accept()

    @property
    def db_path(self) -> Optional[Path]:
        """Get the selected database path."""
        return self._db_path
