"""Conflict resolution dialog for handling version conflicts."""

from enum import Enum
from typing import Optional, Union

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGridLayout,
)

from fidra.domain.models import PlannedTemplate, Transaction


class ConflictResolution(Enum):
    """Resolution choice for version conflicts."""
    KEEP_MINE = "keep_mine"
    USE_THEIRS = "use_theirs"


def _build_fields(
    local: Union[Transaction, PlannedTemplate],
    db: Union[Transaction, PlannedTemplate],
) -> list[tuple[str, str, str]]:
    """Build comparison fields based on entity type."""
    if isinstance(local, Transaction):
        return [
            ("Description", local.description, db.description),
            ("Amount", f"£{local.amount:,.2f}", f"£{db.amount:,.2f}"),
            ("Date", local.date.strftime("%d %b %Y"), db.date.strftime("%d %b %Y")),
            ("Type", local.type.value.title(), db.type.value.title()),
            ("Status", local.status.value.title(), db.status.value.title()),
            ("Category", local.category or "-", db.category or "-"),
            ("Party", local.party or "-", db.party or "-"),
            ("Reference", local.reference or "-", db.reference or "-"),
            ("Activity", local.activity or "-", db.activity or "-"),
            ("Notes", local.notes or "-", db.notes or "-"),
        ]
    elif isinstance(local, PlannedTemplate):
        return [
            ("Description", local.description, db.description),
            ("Amount", f"£{local.amount:,.2f}", f"£{db.amount:,.2f}"),
            ("Start Date", local.start_date.strftime("%d %b %Y"), db.start_date.strftime("%d %b %Y")),
            ("Frequency", local.frequency.value.title(), db.frequency.value.title()),
            ("Target Sheet", local.target_sheet or "-", db.target_sheet or "-"),
            ("Category", local.category or "-", db.category or "-"),
            ("Party", local.party or "-", db.party or "-"),
            ("Activity", local.activity or "-", db.activity or "-"),
        ]
    return []


class ConflictResolutionDialog(QDialog):
    """Dialog for resolving version conflicts between local and database versions.

    Shows both versions side by side and lets the user choose how to proceed.
    Supports Transaction and PlannedTemplate entities.
    """

    def __init__(
        self,
        local_entity: Union[Transaction, PlannedTemplate],
        db_entity: Union[Transaction, PlannedTemplate],
        parent=None
    ):
        """Initialize the conflict resolution dialog.

        Args:
            local_entity: The user's local version (their edits)
            db_entity: The current database version (someone else's changes)
            parent: Parent widget
        """
        super().__init__(parent)
        self._local = local_entity
        self._db = db_entity
        self._resolution = ConflictResolution.USE_THEIRS  # Safe default

        entity_label = "planned template" if isinstance(local_entity, PlannedTemplate) else "transaction"
        self.setWindowTitle("Conflict Detected")
        self.setModal(True)
        self.setMinimumWidth(600)
        # Disable close button — user must choose a resolution
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowCloseButtonHint
        )

        self._entity_label = entity_label
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Warning header
        header = QLabel(
            f"This {self._entity_label} was modified by someone else while you were editing it."
        )
        header.setObjectName("conflict_header")
        header.setWordWrap(True)
        header.setStyleSheet("font-size: 14px; font-weight: bold; color: #ef4444;")
        layout.addWidget(header)

        subheader = QLabel(
            "Please choose which version to keep. Differences are highlighted."
        )
        subheader.setWordWrap(True)
        subheader.setStyleSheet("color: #6b7280;")
        layout.addWidget(subheader)

        # Comparison frame
        comparison = QFrame()
        comparison.setObjectName("conflict_comparison")
        comparison.setStyleSheet("""
            QFrame#conflict_comparison {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 6px;
            }
        """)
        comp_layout = QGridLayout(comparison)
        comp_layout.setContentsMargins(16, 16, 16, 16)
        comp_layout.setSpacing(12)

        # Column headers
        yours_header = QLabel("Your Changes")
        yours_header.setStyleSheet("font-weight: bold; color: #3b82f6;")
        theirs_header = QLabel("Database Version")
        theirs_header.setStyleSheet("font-weight: bold; color: #10b981;")

        comp_layout.addWidget(yours_header, 0, 1)
        comp_layout.addWidget(theirs_header, 0, 2)

        # Compare fields — built dynamically based on entity type
        row = 1
        fields = _build_fields(self._local, self._db)

        for field_name, local_val, db_val in fields:
            is_different = local_val != db_val

            # Field label
            label = QLabel(field_name + ":")
            label.setStyleSheet("font-weight: 500;")
            comp_layout.addWidget(label, row, 0)

            # Your value
            yours = QLabel(str(local_val))
            if is_different:
                yours.setStyleSheet(
                    "background-color: #dbeafe; color: #1e40af; "
                    "padding: 4px 8px; border-radius: 3px; font-weight: 500;"
                )
            comp_layout.addWidget(yours, row, 1)

            # Their value
            theirs = QLabel(str(db_val))
            if is_different:
                theirs.setStyleSheet(
                    "background-color: #d1fae5; color: #065f46; "
                    "padding: 4px 8px; border-radius: 3px; font-weight: 500;"
                )
            comp_layout.addWidget(theirs, row, 2)

            row += 1

        layout.addWidget(comparison)

        # Version info
        version_info = QLabel(
            f"Your version: {self._local.version - 1} → {self._local.version}  |  "
            f"Database version: {self._db.version}"
        )
        version_info.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(version_info)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        button_layout.addStretch()

        use_theirs_btn = QPushButton("Use Database Version")
        use_theirs_btn.setToolTip("Discard your changes and use the database version")
        use_theirs_btn.clicked.connect(self._on_use_theirs)
        button_layout.addWidget(use_theirs_btn)

        keep_mine_btn = QPushButton("Keep My Changes")
        keep_mine_btn.setObjectName("primary_button")
        keep_mine_btn.setToolTip("Overwrite the database with your changes")
        keep_mine_btn.clicked.connect(self._on_keep_mine)
        button_layout.addWidget(keep_mine_btn)

        layout.addLayout(button_layout)

    def _on_keep_mine(self) -> None:
        """User chose to keep their changes."""
        self._resolution = ConflictResolution.KEEP_MINE
        self.accept()

    def _on_use_theirs(self) -> None:
        """User chose to use the database version."""
        self._resolution = ConflictResolution.USE_THEIRS
        self.accept()

    def get_resolution(self) -> ConflictResolution:
        """Get the user's resolution choice.

        Returns:
            The chosen resolution
        """
        return self._resolution
