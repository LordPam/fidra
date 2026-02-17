"""Connection state management service.

Tracks cloud connection status, performs periodic health checks,
and manages reconnection attempts.
"""

import asyncio
import logging
from enum import Enum
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal
import qasync

if TYPE_CHECKING:
    from fidra.data.cloud_connection import CloudConnection

logger = logging.getLogger(__name__)


class ConnectionStatus(Enum):
    """Connection state values."""

    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    OFFLINE = "offline"


class ConnectionStateService(QObject):
    """Service for tracking and managing cloud connection state.

    Emits Qt signals when connection status changes, enabling UI updates.
    Performs periodic health checks and automatic reconnection attempts.

    Signals:
        status_changed(ConnectionStatus): Emitted when connection status changes
        health_check_completed(bool): Emitted after each health check
        reconnect_attempt(int, int): Emitted before reconnect (attempt, max_attempts)
    """

    status_changed = Signal(object)  # ConnectionStatus
    health_check_completed = Signal(bool)
    reconnect_attempt = Signal(int, int)  # current_attempt, max_attempts
    _trigger_reconnect = Signal()  # Internal signal to trigger async reconnect
    _trigger_health_check = Signal()  # Internal signal to trigger async health check

    def __init__(
        self,
        cloud_connection: "CloudConnection",
        health_check_interval_ms: int = 30000,  # 30 seconds
        max_reconnect_attempts: int = 5,
        parent: Optional[QObject] = None,
    ):
        """Initialize connection state service.

        Args:
            cloud_connection: The cloud connection to monitor
            health_check_interval_ms: Interval between health checks (ms)
            max_reconnect_attempts: Max reconnection attempts before giving up
            parent: Qt parent object
        """
        super().__init__(parent)
        self._connection = cloud_connection
        self._health_check_interval = health_check_interval_ms
        self._max_reconnect_attempts = max_reconnect_attempts

        self._status = ConnectionStatus.CONNECTED
        self._health_check_timer: Optional[QTimer] = None
        self._reconnect_timer: Optional[QTimer] = None
        self._reconnect_attempts = 0
        self._is_monitoring = False
        self._is_reconnecting = False
        self._is_health_checking = False

        # Connect internal signals to async handlers
        self._trigger_reconnect.connect(self._handle_reconnect_trigger)
        self._trigger_health_check.connect(self._handle_health_check_trigger)

        # Wire up connection callbacks
        self._connection.on_connection_lost = self._on_connection_lost
        self._connection.on_connection_restored = self._on_connection_restored

    @property
    def status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self._status

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._status == ConnectionStatus.CONNECTED

    @property
    def is_offline(self) -> bool:
        """Check if currently offline."""
        return self._status == ConnectionStatus.OFFLINE

    def start_monitoring(self) -> None:
        """Start periodic health checks."""
        if self._is_monitoring:
            return

        self._is_monitoring = True
        self._health_check_timer = QTimer(self)
        self._health_check_timer.timeout.connect(self._do_health_check)
        self._health_check_timer.start(self._health_check_interval)
        logger.info(f"Started health monitoring (interval: {self._health_check_interval}ms)")

    def stop_monitoring(self) -> None:
        """Stop periodic health checks."""
        self._is_monitoring = False
        self._is_reconnecting = False
        if self._health_check_timer:
            self._health_check_timer.stop()
            self._health_check_timer = None
        if self._reconnect_timer:
            self._reconnect_timer.stop()
            self._reconnect_timer = None

        logger.info("Stopped health monitoring")

    async def stop_monitoring_async(self) -> None:
        """Stop periodic health checks and wait for cleanup."""
        self._is_monitoring = False
        self._is_reconnecting = False
        self._is_health_checking = False
        if self._health_check_timer:
            self._health_check_timer.stop()
            self._health_check_timer = None
        if self._reconnect_timer:
            self._reconnect_timer.stop()
            self._reconnect_timer = None

        logger.info("Stopped health monitoring")

    def _set_status(self, new_status: ConnectionStatus) -> None:
        """Update status and emit signal if changed."""
        if new_status != self._status:
            old_status = self._status
            self._status = new_status
            logger.info(f"Connection status: {old_status.value} -> {new_status.value}")
            # Speed up health checks when offline for faster recovery,
            # restore normal interval when connected
            if self._health_check_timer and self._is_monitoring:
                if new_status == ConnectionStatus.OFFLINE:
                    self._health_check_timer.setInterval(5000)
                elif new_status == ConnectionStatus.CONNECTED:
                    self._health_check_timer.setInterval(self._health_check_interval)
            self.status_changed.emit(new_status)

    def _on_connection_lost(self) -> None:
        """Handle connection lost callback from CloudConnection."""
        logger.warning("Connection lost detected")
        self._set_status(ConnectionStatus.RECONNECTING)
        self._start_reconnection()

    def _on_connection_restored(self) -> None:
        """Handle connection restored callback from CloudConnection."""
        logger.info("Connection restored")
        self._reconnect_attempts = 0
        self._set_status(ConnectionStatus.CONNECTED)

    def _do_health_check(self) -> None:
        """Perform a health check (called by timer)."""
        # Don't start new health check if one is already running or we're stopping
        if not self._is_monitoring:
            return
        if self._is_health_checking:
            return
        # Emit signal to trigger async health check
        self._trigger_health_check.emit()

    @qasync.asyncSlot()
    async def _handle_health_check_trigger(self) -> None:
        """Handle health check trigger - runs async health check."""
        if not self._is_monitoring or self._is_health_checking:
            return
        self._is_health_checking = True
        try:
            await self._async_health_check()
        except RuntimeError as e:
            if "Cannot enter into task" in str(e):
                logger.debug("Health check: skipping due to qasync re-entrancy")
            else:
                logger.error(f"Error in health check: {e}")
        except Exception as e:
            logger.error(f"Error in health check: {e}")
        finally:
            self._is_health_checking = False

    async def _async_health_check(self) -> None:
        """Async health check implementation."""
        try:
            # When offline, attempt a full reconnect instead of just pinging
            # the (likely dead) pool - this lets us recover automatically
            # when the network comes back
            if self._status == ConnectionStatus.OFFLINE:
                await self._attempt_offline_recovery()
                return

            is_healthy = await self._connection.health_check()
            self.health_check_completed.emit(is_healthy)

            if not is_healthy and self._status == ConnectionStatus.CONNECTED:
                self._set_status(ConnectionStatus.RECONNECTING)
                self._start_reconnection()
            elif is_healthy and self._status != ConnectionStatus.CONNECTED:
                self._reconnect_attempts = 0
                self._set_status(ConnectionStatus.CONNECTED)

        except RuntimeError as e:
            # Ignore qasync re-entrancy errors - will retry next interval
            if "Cannot enter into task" in str(e):
                logger.debug("Health check: skipping due to qasync re-entrancy")
            else:
                logger.error(f"Health check error: {e}")
                self._handle_health_check_failure()
        except Exception as e:
            logger.error(f"Health check error: {e}")
            self._handle_health_check_failure()

    async def _attempt_offline_recovery(self) -> None:
        """Periodically attempt to reconnect while offline.

        Tries a full reconnect every health check interval. If it works,
        transitions back to CONNECTED. If not, stays OFFLINE silently.
        """
        try:
            await self._connection.reconnect()
            # Success - back online
            print("[RECONNECT] Auto-recovery successful")
            logger.info("Auto-recovery from offline: reconnected")
            self._reconnect_attempts = 0
            self._set_status(ConnectionStatus.CONNECTED)
        except Exception:
            # Still offline - stay quiet, will try again next health check
            pass

    def _handle_health_check_failure(self) -> None:
        """Handle a failed health check."""
        self.health_check_completed.emit(False)
        if self._status == ConnectionStatus.CONNECTED:
            self._set_status(ConnectionStatus.RECONNECTING)
            self._start_reconnection()

    def _start_reconnection(self) -> None:
        """Start reconnection attempts using QTimer."""
        if self._is_reconnecting:
            return  # Already reconnecting

        self._is_reconnecting = True
        self._reconnect_attempts = 0
        print("[RECONNECT] Starting reconnection process...")
        # Trigger first attempt immediately
        self._trigger_reconnect.emit()

    @qasync.asyncSlot()
    async def _handle_reconnect_trigger(self) -> None:
        """Handle reconnect trigger - performs one reconnection attempt."""
        if not self._is_reconnecting:
            return

        self._reconnect_attempts += 1
        self.reconnect_attempt.emit(
            self._reconnect_attempts,
            self._max_reconnect_attempts
        )

        print(f"[RECONNECT] Attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}")
        logger.info(
            f"Reconnection attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}"
        )

        try:
            await self._connection.reconnect()
            # Success!
            print("[RECONNECT] Success!")
            logger.info("Reconnection successful")
            self._reconnect_attempts = 0
            self._is_reconnecting = False
            # Note: on_connection_restored callback will update status
            return

        except RuntimeError as e:
            if "Cannot enter into task" in str(e):
                print("[RECONNECT] qasync re-entrancy, scheduling retry...")
                # Retry after short delay
                self._reconnect_attempts -= 1
                QTimer.singleShot(500, lambda: self._trigger_reconnect.emit())
                return
            else:
                print(f"[RECONNECT] Failed (RuntimeError): {e}")
                logger.warning(f"Reconnection attempt failed (RuntimeError): {e}")

        except Exception as e:
            print(f"[RECONNECT] Failed: {e}")
            logger.warning(f"Reconnection attempt failed: {e}")

        # Check if we should retry or give up
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            print("[RECONNECT] Max attempts reached, going offline")
            logger.error("Max reconnection attempts reached, going offline")
            self._is_reconnecting = False
            self._set_status(ConnectionStatus.OFFLINE)
            return

        # Schedule next attempt with exponential backoff: 1s, 2s, 4s, 8s, 16s
        delay_ms = min(1000 * (2 ** (self._reconnect_attempts - 1)), 16000)
        print(f"[RECONNECT] Scheduling retry in {delay_ms}ms")
        logger.info(f"Waiting {delay_ms}ms before next attempt")
        QTimer.singleShot(delay_ms, lambda: self._trigger_reconnect.emit())

    async def reconnect_now(self) -> bool:
        """Manually trigger reconnection attempt.

        Returns:
            True if reconnection succeeded, False otherwise
        """
        print("[RECONNECT] Manual reconnection requested")
        logger.info("Manual reconnection requested")
        self._reconnect_attempts = 0
        self._is_reconnecting = False  # Stop any ongoing reconnection
        self._set_status(ConnectionStatus.RECONNECTING)

        try:
            await self._connection.reconnect()
            print("[RECONNECT] Manual reconnection successful")
            return True
        except Exception as e:
            print(f"[RECONNECT] Manual reconnection failed: {e}")
            logger.error(f"Manual reconnection failed: {e}")
            self._set_status(ConnectionStatus.OFFLINE)
            return False

    def get_status_message(self) -> str:
        """Get human-readable status message."""
        if self._status == ConnectionStatus.CONNECTED:
            return "Connected"
        elif self._status == ConnectionStatus.RECONNECTING:
            if self._reconnect_attempts > 0:
                return f"Reconnecting ({self._reconnect_attempts}/{self._max_reconnect_attempts})..."
            return "Reconnecting..."
        else:
            return "Offline"

    def report_network_error(self) -> None:
        """Report a network error detected by another component.

        Call this when any operation detects a network failure to
        immediately update connection status without waiting for health check.
        """
        if self._status == ConnectionStatus.CONNECTED:
            print("[RECONNECT] Network error reported - starting reconnection")
            logger.info("Network error reported - starting reconnection")
            self._set_status(ConnectionStatus.RECONNECTING)
            self._start_reconnection()
