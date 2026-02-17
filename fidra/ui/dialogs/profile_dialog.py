"""Profile settings dialog."""

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class ProfileDialog(QDialog):
    """Dialog for editing user profile settings.

    Allows the user to set their name and initials, which are used
    in audit logs to track who made changes.
    """

    def __init__(self, context: "ApplicationContext", parent=None, first_run: bool = False):
        """Initialize profile dialog.

        Args:
            context: Application context
            parent: Parent widget
            first_run: If True, shows welcome message and disables cancel
        """
        super().__init__(parent)
        self._context = context
        self._first_run = first_run

        self.setWindowTitle("Welcome to Fidra" if first_run else "Profile Settings")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        if self._first_run:
            # Welcome message for first run
            welcome = QLabel("Welcome to Fidra!")
            welcome.setObjectName("section_header")
            layout.addWidget(welcome)

            intro = QLabel(
                "Please enter your name and initials. This helps identify "
                "who made changes in the audit log, which is useful when "
                "multiple people manage the accounts."
            )
            intro.setWordWrap(True)
            intro.setObjectName("secondary_text")
            layout.addWidget(intro)

            layout.addSpacing(8)
        else:
            # Header for settings mode
            header = QLabel("Profile")
            header.setObjectName("section_header")
            layout.addWidget(header)

            info = QLabel(
                "Your name and initials are used in the audit log to track "
                "who made changes to transactions."
            )
            info.setWordWrap(True)
            info.setObjectName("secondary_text")
            layout.addWidget(info)

            layout.addSpacing(8)

        # Name field
        name_layout = QHBoxLayout()
        name_label = QLabel("Name:")
        name_label.setMinimumWidth(80)
        name_layout.addWidget(name_label)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Jane Smith")
        self.name_edit.setText(self._context.settings.profile.name)
        self.name_edit.setMinimumHeight(32)
        name_layout.addWidget(self.name_edit, 1)
        layout.addLayout(name_layout)

        # Initials field
        initials_layout = QHBoxLayout()
        initials_label = QLabel("Initials:")
        initials_label.setMinimumWidth(80)
        initials_layout.addWidget(initials_label)

        self.initials_edit = QLineEdit()
        self.initials_edit.setPlaceholderText("e.g., JS")
        self.initials_edit.setMaxLength(3)
        self.initials_edit.setText(self._context.settings.profile.initials)
        self.initials_edit.setMinimumHeight(32)
        self.initials_edit.setMaximumWidth(80)
        initials_layout.addWidget(self.initials_edit)
        initials_layout.addStretch()
        layout.addLayout(initials_layout)

        # Hint about initials
        initials_hint = QLabel("Initials appear in audit log entries (max 3 characters).")
        initials_hint.setObjectName("secondary_text")
        layout.addWidget(initials_hint)

        layout.addSpacing(16)

        # Startup section (not shown on first run)
        if not self._first_run:
            startup_header = QLabel("Startup")
            startup_header.setObjectName("section_header")
            layout.addWidget(startup_header)

            self.always_show_chooser = QCheckBox("Always show file chooser on startup")
            self.always_show_chooser.setChecked(
                self._context.settings.storage.always_show_file_chooser
            )
            layout.addWidget(self.always_show_chooser)

            startup_hint = QLabel(
                "When enabled, you'll choose which database to open each time. "
                "Otherwise, the last used database opens automatically."
            )
            startup_hint.setWordWrap(True)
            startup_hint.setObjectName("secondary_text")
            layout.addWidget(startup_hint)

            layout.addSpacing(8)

        # Buttons
        if self._first_run:
            # Only OK button for first run (can't skip profile setup)
            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
            button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Get Started")
        else:
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )

        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Focus on name field
        self.name_edit.setFocus()

    def _on_accept(self) -> None:
        """Save profile settings."""
        name = self.name_edit.text().strip()
        initials = self.initials_edit.text().strip().upper()

        # For first run, require at least a name
        if self._first_run and not name:
            self.name_edit.setFocus()
            return

        # Update settings
        self._context.settings.profile.name = name
        self._context.settings.profile.initials = initials
        self._context.settings.profile.first_run_complete = True

        # Update startup setting (not on first run)
        if not self._first_run:
            self._context.settings.storage.always_show_file_chooser = (
                self.always_show_chooser.isChecked()
            )

        self._context.save_settings()

        # Update audit service user
        if self._context.audit_service:
            self._context.audit_service.user = initials or name or "System"

        self.accept()

    def keyPressEvent(self, event) -> None:
        """Handle key press - prevent Escape from closing on first run."""
        if self._first_run and event.key() == Qt.Key.Key_Escape:
            return  # Ignore Escape on first run
        super().keyPressEvent(event)
