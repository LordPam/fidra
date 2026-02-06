"""Notification banner widget for app-wide alerts."""

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)


class NotificationBanner(QFrame):
    """A dismissable notification banner for important alerts.

    Displays a warning message with action buttons.
    """

    # Emitted when user clicks the primary action (e.g., "Review")
    action_clicked = Signal()
    # Emitted when user dismisses the banner
    dismissed = Signal()

    def __init__(self, parent=None):
        """Initialize the notification banner.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("notification_banner")
        self._setup_ui()
        self.hide()  # Hidden by default

    def _setup_ui(self) -> None:
        """Set up the banner UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # Warning icon
        self.icon_label = QLabel("\u26a0")  # Warning triangle
        self.icon_label.setObjectName("banner_icon")
        layout.addWidget(self.icon_label)

        # Message
        self.message_label = QLabel()
        self.message_label.setObjectName("banner_message")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label, 1)

        # Action button (e.g., "Review")
        self.action_btn = QPushButton("Review")
        self.action_btn.setObjectName("banner_action_btn")
        self.action_btn.clicked.connect(self._on_action_clicked)
        layout.addWidget(self.action_btn)

        # Dismiss button
        self.dismiss_btn = QPushButton("Dismiss")
        self.dismiss_btn.setObjectName("banner_dismiss_btn")
        self.dismiss_btn.clicked.connect(self._on_dismiss_clicked)
        layout.addWidget(self.dismiss_btn)

    def show_warning(
        self,
        message: str,
        action_text: str = "Review",
        action_callback: Optional[Callable] = None
    ) -> None:
        """Show a warning banner.

        Args:
            message: The warning message to display
            action_text: Text for the action button
            action_callback: Optional callback for action button
        """
        self.message_label.setText(message)
        self.action_btn.setText(action_text)
        self._action_callback = action_callback
        self.show()

    def _on_action_clicked(self) -> None:
        """Handle action button click."""
        if hasattr(self, '_action_callback') and self._action_callback:
            self._action_callback()
        self.action_clicked.emit()
        self.hide()

    def _on_dismiss_clicked(self) -> None:
        """Handle dismiss button click."""
        self.dismissed.emit()
        self.hide()
