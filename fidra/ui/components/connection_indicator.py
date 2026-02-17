"""Connection status indicator widget for status bar."""

from typing import Optional, TYPE_CHECKING

import qasync
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)

if TYPE_CHECKING:
    from fidra.services.connection_state import ConnectionStateService, ConnectionStatus


class ConnectionIndicator(QFrame):
    """Status bar widget showing cloud connection state.

    Displays connection status with a colored indicator and optional
    pending sync count. Provides manual reconnect button when offline.

    Signals:
        reconnect_requested: Emitted when user clicks reconnect
    """

    reconnect_requested = Signal()

    def __init__(
        self,
        connection_state: "ConnectionStateService",
        parent: Optional[QWidget] = None,
    ):
        """Initialize the connection indicator.

        Args:
            connection_state: Connection state service to monitor
            parent: Parent widget
        """
        super().__init__(parent)
        self._connection_state = connection_state
        self._pending_count = 0

        self.setObjectName("connection_indicator")
        self._setup_ui()
        self._connect_signals()
        self._update_display(connection_state.status)

    def _setup_ui(self) -> None:
        """Set up the indicator UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Status dot
        self.status_dot = QLabel()
        self.status_dot.setObjectName("status_dot")
        self.status_dot.setFixedSize(8, 8)
        layout.addWidget(self.status_dot)

        # Status text
        self.status_label = QLabel("Connected")
        self.status_label.setObjectName("status_label")
        layout.addWidget(self.status_label)

        # Pending count (hidden when 0)
        self.pending_label = QLabel()
        self.pending_label.setObjectName("pending_label")
        self.pending_label.hide()
        layout.addWidget(self.pending_label)

        # Reconnect button (hidden when connected)
        self.reconnect_btn = QPushButton("Reconnect")
        self.reconnect_btn.setObjectName("reconnect_btn")
        self.reconnect_btn.setFixedHeight(22)
        self.reconnect_btn.clicked.connect(self._on_reconnect_clicked)
        self.reconnect_btn.hide()
        layout.addWidget(self.reconnect_btn)

        # Apply base styling
        self.setStyleSheet("""
            #connection_indicator {
                background: transparent;
                border: none;
            }
            #status_dot {
                border-radius: 4px;
            }
            #status_label {
                font-size: 12px;
            }
            #pending_label {
                font-size: 11px;
                color: #888;
            }
            #reconnect_btn {
                font-size: 11px;
                padding: 2px 8px;
            }
        """)

    def _connect_signals(self) -> None:
        """Connect to connection state service signals."""
        self._connection_state.status_changed.connect(self._on_status_changed)
        self._connection_state.reconnect_attempt.connect(self._on_reconnect_attempt)

    def _on_status_changed(self, status: "ConnectionStatus") -> None:
        """Handle connection status changes."""
        self._update_display(status)

    def _on_reconnect_attempt(self, attempt: int, max_attempts: int) -> None:
        """Handle reconnection attempt updates."""
        self.status_label.setText(f"Reconnecting ({attempt}/{max_attempts})...")

    def _update_display(self, status: "ConnectionStatus") -> None:
        """Update the display based on connection status."""
        from fidra.services.connection_state import ConnectionStatus

        if status == ConnectionStatus.CONNECTED:
            self.status_dot.setStyleSheet(
                "#status_dot { background-color: #4CAF50; border-radius: 4px; }"
            )
            self.status_label.setText("Connected")
            self.reconnect_btn.hide()
            self._update_pending_display()

        elif status == ConnectionStatus.RECONNECTING:
            self.status_dot.setStyleSheet(
                "#status_dot { background-color: #FFC107; border-radius: 4px; }"
            )
            self.status_label.setText("Reconnecting...")
            self.reconnect_btn.hide()
            self.pending_label.hide()

        elif status == ConnectionStatus.OFFLINE:
            self.status_dot.setStyleSheet(
                "#status_dot { background-color: #F44336; border-radius: 4px; }"
            )
            self.status_label.setText("Offline")
            self.reconnect_btn.show()
            self._update_pending_display()

    def set_pending_count(self, count: int) -> None:
        """Set the number of pending sync operations.

        Args:
            count: Number of pending changes
        """
        self._pending_count = count
        self._update_pending_display()

    def _update_pending_display(self) -> None:
        """Update the pending changes display."""
        if self._pending_count > 0:
            self.pending_label.setText(f"({self._pending_count} pending)")
            self.pending_label.show()
        else:
            self.pending_label.hide()

    @qasync.asyncSlot()
    async def _on_reconnect_clicked(self) -> None:
        """Handle reconnect button click."""
        self.reconnect_btn.setEnabled(False)
        self.reconnect_btn.setText("Connecting...")

        try:
            success = await self._connection_state.reconnect_now()
            if not success:
                self.reconnect_btn.setText("Reconnect")
                self.reconnect_btn.setEnabled(True)
        except Exception:
            self.reconnect_btn.setText("Reconnect")
            self.reconnect_btn.setEnabled(True)

        self.reconnect_requested.emit()
