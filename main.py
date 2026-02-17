#!/usr/bin/env python
"""Fidra application entry point.

This module initializes the Qt application with qasync event loop integration
and launches the main window.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import qasync
from PySide6.QtCore import QTimer, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from fidra.app import ApplicationContext
from fidra.state.persistence import SettingsStore
from fidra.ui.main_window import MainWindow
from fidra.ui.window_manager import WindowManager
from fidra.ui.dialogs.setup_wizard import SetupWizard
from fidra.ui.dialogs.file_chooser import FileChooserDialog


def should_restore_last_session(settings_store: SettingsStore) -> tuple[bool, Path | None, str | None]:
    """Check if we should restore the last session (file or cloud server).

    Returns (should_restore, file_path, server_id) where should_restore is True if:
    - Settings file exists
    - For SQLite: last_file exists on disk
    - For Cloud: active_server_id is set
    - last_opened_at is within 24 hours (or missing for backward compatibility)
    """
    if not settings_store.exists():
        return False, None, None

    settings = settings_store.load()
    backend = settings.storage.backend
    last_opened_at = settings.storage.last_opened_at

    # Check if within time window
    is_recent = False
    if not last_opened_at:
        # Backward compatibility: if no timestamp, restore anyway
        is_recent = True
    else:
        try:
            opened_time = datetime.fromisoformat(last_opened_at)
            is_recent = datetime.now() - opened_time < timedelta(hours=24)
        except (ValueError, TypeError):
            # Invalid timestamp format - restore anyway
            is_recent = True

    if backend == "cloud":
        # Cloud backend - check for active server
        server_id = settings.storage.active_server_id
        if server_id and is_recent:
            # Verify server still exists in config
            server = settings.storage.get_active_server()
            if server:
                return True, None, server_id
        return False, None, None
    else:
        # SQLite backend
        last_file = settings.storage.last_file
        if last_file and last_file.exists() and is_recent:
            return True, last_file, None
        return False, None, None


async def async_cleanup(window_manager: WindowManager) -> None:
    """Clean up all windows and resources (safe to call multiple times)."""
    if window_manager.window_count > 0 or window_manager._pending_cleanup:
        print("Closing all windows...")
        await window_manager.close_all_windows()
        print("Goodbye!")


def _get_resource_path(relative_path: str) -> Path:
    """Resolve resource paths for bundled and dev runs."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent / relative_path


def run() -> None:
    """Run the application with qasync event loop."""
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Fidra")
    app.setOrganizationName("Fidra")

    # Set window icon (avoid overriding macOS .icns)
    is_bundled = getattr(sys, 'frozen', False)
    if sys.platform == "win32":
        icon_path = _get_resource_path("fidra/resources/icons/fidra.ico")
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
    elif not is_bundled and sys.platform != "darwin":
        icon_path = _get_resource_path("fidra/ui/theme/icons/icon.svg")
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

    # Check settings state
    settings_store = SettingsStore()
    is_first_run = not settings_store.exists()

    # Determine database path or cloud server
    db_path = None
    server_id = None

    # Priority 1: Command line argument (SQLite file only)
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
        if not db_path.exists():
            print(f"Warning: File not found: {db_path}")
            db_path = None

    # Priority 2: Check if we should restore last session (within 24 hours)
    last_file_for_chooser = None
    cloud_servers_for_chooser = None
    active_server_for_chooser = None

    if db_path is None and not is_first_run:
        # Check if user wants to always show file chooser
        settings = settings_store.load()
        always_show_chooser = settings.storage.always_show_file_chooser

        should_restore, last_file, last_server_id = should_restore_last_session(settings_store)
        if should_restore and not always_show_chooser:
            if last_server_id:
                print(f"Restoring recent cloud session")
                server_id = last_server_id
            elif last_file:
                print(f"Restoring recent file: {last_file}")
                db_path = last_file
            # Update last_opened_at so the session stays "recent"
            temp_settings = settings_store.load()
            temp_settings.storage.last_opened_at = datetime.now().isoformat()
            settings_store.save(temp_settings)
        else:
            # Session is stale (>24 hours) or user prefers file chooser - show it
            # Keep track of options to offer
            last_file_for_chooser = settings.storage.last_file
            cloud_servers_for_chooser = settings.storage.cloud_servers
            active_server_for_chooser = settings.storage.active_server_id

    # Priority 3: First run - show setup wizard
    if db_path is None and server_id is None and is_first_run:
        wizard = SetupWizard()
        if wizard.exec():
            # Save wizard settings
            temp_settings = settings_store.load()
            if wizard.user_name:
                temp_settings.profile.name = wizard.user_name
                temp_settings.profile.initials = wizard.user_initials or ""
                temp_settings.profile.first_run_complete = True

            if wizard.is_cloud:
                # Cloud server selected
                server_id = wizard.cloud_server.id
                temp_settings.storage.add_server(wizard.cloud_server)
                temp_settings.storage.active_server_id = server_id
                temp_settings.storage.backend = "cloud"
            else:
                # Local file selected
                db_path = wizard.db_path
                temp_settings.storage.last_file = db_path
                temp_settings.storage.backend = "sqlite"

            temp_settings.storage.last_opened_at = datetime.now().isoformat()
            settings_store.save(temp_settings)
        else:
            # User cancelled - exit
            sys.exit(0)

    # Priority 4: Returning user with stale session - show file chooser
    if db_path is None and server_id is None and not is_first_run:
        chooser = FileChooserDialog(
            last_file=last_file_for_chooser,
            cloud_servers=cloud_servers_for_chooser,
            active_server_id=active_server_for_chooser,
        )
        if chooser.exec():
            if chooser.is_cloud:
                server_id = chooser.selected_server_id
                # Update settings for cloud
                temp_settings = settings_store.load()
                # If a new server was configured, add it to the list
                if chooser.new_server:
                    temp_settings.storage.add_server(chooser.new_server)
                temp_settings.storage.active_server_id = server_id
                temp_settings.storage.last_opened_at = datetime.now().isoformat()
                temp_settings.storage.backend = "cloud"
                settings_store.save(temp_settings)
            else:
                db_path = chooser.db_path
                # Update settings with new file
                temp_settings = settings_store.load()
                temp_settings.storage.last_file = db_path
                temp_settings.storage.last_opened_at = datetime.now().isoformat()
                temp_settings.storage.backend = "sqlite"
                settings_store.save(temp_settings)
        else:
            # User cancelled - exit
            sys.exit(0)

    # Set up qasync event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Suppress qasync re-entrancy errors (harmless - tasks retry on next interval)
    def exception_handler(loop, context):
        exception = context.get("exception")
        if exception and "Cannot enter into task" in str(exception):
            # Silently ignore qasync re-entrancy - background tasks will retry
            return
        # For other exceptions, use default handler
        loop.default_exception_handler(context)

    loop.set_exception_handler(exception_handler)

    # Create window manager
    window_manager = WindowManager(settings_store)

    # Connect window manager signals - do async cleanup before quitting
    async def do_cleanup_and_quit():
        print("Cleaning up...")
        await window_manager.close_all_windows()
        print("Goodbye!")
        app.quit()

    def on_all_windows_closed():
        # Schedule async cleanup
        asyncio.ensure_future(do_cleanup_and_quit())

    window_manager.all_windows_closed.connect(on_all_windows_closed)

    with loop:
        try:
            # Create initial window
            success = window_manager.create_window(db_path=db_path, server_id=server_id, loop=loop)

            # If initial window failed (e.g., invalid database), show file chooser
            if not success:
                settings = settings_store.load()
                chooser = FileChooserDialog(
                    last_file=None,
                    cloud_servers=settings.storage.cloud_servers,
                    active_server_id=settings.storage.active_server_id,
                )
                if chooser.exec():
                    if chooser.is_cloud:
                        server_id = chooser.selected_server_id
                        db_path = None
                        # Update settings for cloud
                        temp_settings = settings_store.load()
                        # If a new server was configured, add it to the list
                        if chooser.new_server:
                            temp_settings.storage.add_server(chooser.new_server)
                        temp_settings.storage.active_server_id = server_id
                        temp_settings.storage.last_opened_at = datetime.now().isoformat()
                        temp_settings.storage.backend = "cloud"
                        settings_store.save(temp_settings)
                    else:
                        db_path = chooser.db_path
                        server_id = None
                        temp_settings = settings_store.load()
                        temp_settings.storage.last_file = db_path
                        temp_settings.storage.last_opened_at = datetime.now().isoformat()
                        temp_settings.storage.backend = "sqlite"
                        settings_store.save(temp_settings)
                    success = window_manager.create_window(db_path=db_path, server_id=server_id, loop=loop)

                if not success:
                    # Still failed or user cancelled - exit
                    sys.exit(0)

            # Check for empty database on first window
            if window_manager.window_count > 0:
                first_window = window_manager._windows[0][0]
                QTimer.singleShot(0, first_window.check_opening_balance)

            # Run Qt event loop (blocks until app quits)
            loop.run_forever()

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            # Cleanup all windows (may already be done if closed via UI)
            try:
                loop.run_until_complete(async_cleanup(window_manager))
            except RuntimeError:
                # Event loop already stopped - cleanup was done before quit
                pass
            loop.close()
            # Force exit - qasync context manager can hang on macOS
            os._exit(0)


if __name__ == "__main__":
    run()
