#!/usr/bin/env python
"""Fidra application entry point.

This module initializes the Qt application with qasync event loop integration
and launches the main window.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

import qasync
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from fidra.app import ApplicationContext
from fidra.state.persistence import SettingsStore
from fidra.ui.main_window import MainWindow
from fidra.ui.window_manager import WindowManager
from fidra.ui.dialogs.setup_wizard import SetupWizard
from fidra.ui.dialogs.file_chooser import FileChooserDialog


def should_restore_last_file(settings_store: SettingsStore) -> tuple[bool, Path | None]:
    """Check if we should restore the last opened file.

    Returns (should_restore, file_path) where should_restore is True if:
    - Settings file exists
    - last_file exists on disk
    - last_opened_at is within 24 hours (or missing for backward compatibility)
    """
    if not settings_store.exists():
        return False, None

    settings = settings_store.load()
    last_file = settings.storage.last_file
    last_opened_at = settings.storage.last_opened_at

    if not last_file or not last_file.exists():
        return False, None

    # Backward compatibility: if no timestamp, restore anyway (first time with new field)
    if not last_opened_at:
        return True, last_file

    try:
        opened_time = datetime.fromisoformat(last_opened_at)
        if datetime.now() - opened_time < timedelta(hours=24):
            return True, last_file
    except (ValueError, TypeError):
        # Invalid timestamp format - restore anyway
        return True, last_file

    return False, None


async def async_cleanup(window_manager: WindowManager) -> None:
    """Clean up all windows and resources."""
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

    # Determine database path
    db_path = None
    show_wizard = False

    # Priority 1: Command line argument
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
        if not db_path.exists():
            print(f"Warning: File not found: {db_path}")
            db_path = None

    # Priority 2: Check if we should restore last file (within 24 hours)
    last_file_for_chooser = None
    if db_path is None and not is_first_run:
        should_restore, last_file = should_restore_last_file(settings_store)
        if should_restore:
            print(f"Restoring recent file: {last_file}")
            db_path = last_file
        else:
            # Last file is stale (>24 hours) - show file chooser (not wizard)
            # Keep track of last file to offer as option
            settings = settings_store.load()
            last_file_for_chooser = settings.storage.last_file

    # Priority 3: First run - show setup wizard
    if db_path is None and is_first_run:
        wizard = SetupWizard()
        if wizard.exec():
            db_path = wizard.db_path

            # Save wizard settings
            temp_settings = settings_store.load()
            if wizard.user_name:
                temp_settings.profile.name = wizard.user_name
                temp_settings.profile.initials = wizard.user_initials or ""
                temp_settings.profile.first_run_complete = True
            temp_settings.storage.last_file = db_path
            temp_settings.storage.last_opened_at = datetime.now().isoformat()
            settings_store.save(temp_settings)
        else:
            # User cancelled - exit
            sys.exit(0)

    # Priority 4: Returning user with stale file - show file chooser
    if db_path is None and not is_first_run:
        chooser = FileChooserDialog(last_file=last_file_for_chooser)
        if chooser.exec():
            db_path = chooser.db_path
            # Update settings with new file
            temp_settings = settings_store.load()
            temp_settings.storage.last_file = db_path
            temp_settings.storage.last_opened_at = datetime.now().isoformat()
            settings_store.save(temp_settings)
        else:
            # User cancelled - exit
            sys.exit(0)

    # Set up qasync event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create window manager
    window_manager = WindowManager(settings_store)

    # Connect window manager signals
    def on_all_windows_closed():
        # On macOS, app typically stays open. On other platforms, quit.
        if sys.platform != 'darwin':
            app.quit()

    window_manager.all_windows_closed.connect(on_all_windows_closed)

    with loop:
        try:
            # Create initial window
            success = window_manager.create_window(db_path=db_path, loop=loop)

            # If initial window failed (e.g., invalid database), show file chooser
            if not success:
                chooser = FileChooserDialog(last_file=None)
                if chooser.exec():
                    db_path = chooser.db_path
                    temp_settings = settings_store.load()
                    temp_settings.storage.last_file = db_path
                    temp_settings.storage.last_opened_at = datetime.now().isoformat()
                    settings_store.save(temp_settings)
                    success = window_manager.create_window(db_path=db_path, loop=loop)

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
            # Cleanup all windows
            loop.run_until_complete(async_cleanup(window_manager))
            loop.close()


if __name__ == "__main__":
    run()
