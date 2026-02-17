"""About Fidra dialog."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from fidra import __version__


def _get_resource_path(relative: str) -> Path:
    """Get resource path for both dev and bundled runs."""
    try:
        base = Path(sys._MEIPASS)
    except AttributeError:
        base = Path(__file__).resolve().parent.parent.parent
    return base / relative


class AboutDialog(QDialog):
    """Simple About dialog showing app name, version, and log path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Fidra")
        self.setModal(True)
        self.setFixedWidth(380)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 20)

        # Logo
        logo_path = _get_resource_path("fidra/resources/logo.svg")
        if logo_path.exists():
            renderer = QSvgRenderer(str(logo_path))
            pixmap = QPixmap(48, 48)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()

            logo_label = QLabel()
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)

        # App name
        name_label = QLabel("Fidra")
        name_label.setObjectName("section_header")
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)

        # Version
        version_label = QLabel(f"Version {__version__}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(version_label)

        # Description
        desc_label = QLabel("Local-first financial ledger for organisations")
        desc_label.setObjectName("secondary_text")
        desc_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc_label)

        layout.addSpacing(8)

        # Log file path
        log_path = Path.home() / ".fidra" / "logs" / "fidra.log"
        log_label = QLabel(f"Log file: {log_path}")
        log_label.setObjectName("secondary_text")
        log_label.setAlignment(Qt.AlignCenter)
        log_label.setWordWrap(True)
        log_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        log_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(log_label)

        layout.addSpacing(4)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
