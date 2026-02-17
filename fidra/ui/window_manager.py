"""Window manager for multi-window support."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from fidra.app import ApplicationContext
from fidra.data.validation import DatabaseValidationError
from fidra.ui.dialogs.file_chooser import FileChooserDialog


class WindowManager(QObject):
    """Manages multiple application windows.

    Each window has its own ApplicationContext pointing to a different file.
    The manager tracks all open windows and handles application lifecycle.
    """

    # Emitted when all windows are closed
    all_windows_closed = Signal()

    def __init__(self, settings_store):
        super().__init__()
        self._windows: list = []  # List of (MainWindow, ApplicationContext) tuples
        self._settings_store = settings_store
        self._closing_all = False
        self._pending_cleanup: list = []  # Contexts from closed windows needing cleanup

    @property
    def window_count(self) -> int:
        """Get number of open windows."""
        return len(self._windows)

    def create_window(self, db_path: Optional[Path] = None, server_id: Optional[str] = None, loop=None) -> bool:
        """Create a new window with optional database path or cloud server.

        Args:
            db_path: Path to database file. If None, shows file chooser.
            server_id: Cloud server ID to connect to (takes precedence over db_path).
            loop: The asyncio event loop to use for initialization.

        Returns:
            True if window was created, False if cancelled.
        """
        # Import here to avoid circular imports
        from fidra.ui.main_window import MainWindow

        # If no path and no server, show file chooser
        if db_path is None and server_id is None:
            # Get settings to offer options
            settings = self._settings_store.load()
            last_file = settings.storage.last_file
            cloud_servers = settings.storage.cloud_servers
            active_server_id = settings.storage.active_server_id

            chooser = FileChooserDialog(
                last_file=last_file,
                cloud_servers=cloud_servers,
                active_server_id=active_server_id,
            )
            if chooser.exec():
                if chooser.is_cloud:
                    server_id = chooser.selected_server_id
                else:
                    db_path = chooser.db_path
            else:
                return False

        # Create context
        ctx = ApplicationContext(db_path=db_path or Path("fidra.db"))

        # Initialize based on whether this is cloud or local
        if server_id:
            # Cloud server connection
            ctx.settings.storage.active_server_id = server_id
            ctx.settings.storage.backend = "cloud"

            if loop:
                try:
                    loop.run_until_complete(self._init_cloud_context(ctx, server_id))
                except Exception as e:
                    self._show_cloud_error(server_id, e)
                    return False

            # Save settings with active server
            ctx.save_settings()
        else:
            # Local SQLite file
            if loop:
                try:
                    loop.run_until_complete(self._init_context(ctx))
                except DatabaseValidationError as e:
                    self._show_validation_error(db_path, e)
                    return False

            # Update last opened timestamp (only after successful init)
            ctx.settings.storage.last_file = db_path
            ctx.settings.storage.last_opened_at = datetime.now().isoformat()
            ctx.settings.storage.backend = "sqlite"
            ctx.save_settings()

        # Create and show window
        window = MainWindow(ctx, window_manager=self)
        window.show()

        # Track window
        self._windows.append((window, ctx))

        return True

    async def _init_cloud_context(self, ctx: ApplicationContext, server_id: str) -> None:
        """Initialize application context for cloud backend."""
        await ctx.switch_to_cloud(server_id)
        server = ctx.active_server
        print(f"Connected to: {server.name if server else 'Cloud'}")
        print(f"Loaded {len(ctx.state.transactions.value)} transactions")

    def _show_cloud_error(self, server_id: str, error: Exception) -> None:
        """Show an error dialog for cloud connection failures."""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Connection Failed")
        msg.setText("Unable to connect to cloud server")
        msg.setInformativeText(str(error))
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    async def create_window_async(
        self, db_path: Optional[Path] = None, server_id: Optional[str] = None
    ) -> bool:
        """Create a new window asynchronously (for use when event loop is running).

        Args:
            db_path: Path to database file.
            server_id: Cloud server ID to connect to (takes precedence over db_path).

        Returns:
            True if window was created, False on error.
        """
        from fidra.ui.main_window import MainWindow

        if server_id:
            # Cloud server connection
            ctx = ApplicationContext(db_path=Path("fidra.db"))
            ctx.settings.storage.active_server_id = server_id
            ctx.settings.storage.backend = "cloud"

            try:
                await self._init_cloud_context(ctx, server_id)
            except Exception as e:
                self._show_cloud_error(server_id, e)
                return False

            # Update last opened timestamp and save settings
            ctx.settings.storage.last_opened_at = datetime.now().isoformat()
            ctx.save_settings()
        else:
            # Local SQLite file
            ctx = ApplicationContext(db_path=db_path)

            try:
                await self._init_context(ctx)
            except DatabaseValidationError as e:
                self._show_validation_error(db_path, e)
                return False

            # Update last opened timestamp
            ctx.settings.storage.last_file = db_path
            ctx.settings.storage.last_opened_at = datetime.now().isoformat()
            ctx.settings.storage.backend = "sqlite"
            ctx.save_settings()

        # Create and show window
        window = MainWindow(ctx, window_manager=self)
        window.show()

        # Track window
        self._windows.append((window, ctx))

        return True

    def _show_validation_error(self, db_path: Path, error: DatabaseValidationError) -> None:
        """Show an error dialog for database validation failures."""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Cannot Open File")
        msg.setText(f"Unable to open '{db_path.name}'")

        detail_text = str(error)
        if error.details:
            detail_text += f"\n\n{error.details}"
        msg.setInformativeText(detail_text)

        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    async def _init_context(self, ctx: ApplicationContext) -> None:
        """Initialize application context."""
        await ctx.initialize()
        print(f"Opened: {ctx.db_path}")
        print(f"Loaded {len(ctx.state.transactions.value)} transactions")

    def close_window(self, window) -> None:
        """Close a specific window and clean up its context.

        Args:
            window: The MainWindow to close.
        """
        ctx_to_close = None
        for i, (w, ctx) in enumerate(self._windows):
            if w is window:
                ctx_to_close = ctx
                self._windows.pop(i)
                break

        # Track context for cleanup in close_all_windows
        if ctx_to_close:
            self._pending_cleanup.append(ctx_to_close)

        # If no windows left, emit signal (triggers app quit)
        if not self._windows and not self._closing_all:
            self.all_windows_closed.emit()

    async def close_all_windows(self) -> None:
        """Close all windows and clean up resources."""
        self._closing_all = True

        # Close any remaining windows
        for window, ctx in self._windows:
            await ctx.close()
            window.close()

        # Clean up contexts from windows that were already closed
        for ctx in self._pending_cleanup:
            await ctx.close()

        self._windows.clear()
        self._pending_cleanup.clear()
        self._closing_all = False

    def get_open_files(self) -> list[Path]:
        """Get list of currently open database files."""
        return [ctx.db_path for _, ctx in self._windows]

    def is_file_open(self, path: Path) -> bool:
        """Check if a file is already open in a window."""
        return path in self.get_open_files()

    def focus_window_for_file(self, path: Path) -> bool:
        """Focus the window that has the given file open.

        Returns:
            True if a window was found and focused.
        """
        for window, ctx in self._windows:
            if ctx.db_path == path:
                window.raise_()
                window.activateWindow()
                return True
        return False
