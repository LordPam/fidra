#!/usr/bin/env python
"""Fidra application entry point.

This module initializes the Qt application with qasync event loop integration
and launches the main window.
"""

import asyncio
import sys
from pathlib import Path

import qasync
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from fidra.app import ApplicationContext
from fidra.state.persistence import SettingsStore
from fidra.ui.main_window import MainWindow
from fidra.ui.dialogs.setup_wizard import SetupWizard


async def async_main(ctx: ApplicationContext) -> None:
    """Initialize async components.

    Args:
        ctx: Application context
    """
    print("Initializing Fidra...")
    await ctx.initialize()
    print(f"Database: {ctx.db_path}")
    print(f"Loaded {len(ctx.state.transactions.value)} transactions")
    print(f"Loaded {len(ctx.state.sheets.value)} sheets")
    print("Fidra is ready!")


async def async_cleanup(ctx: ApplicationContext) -> None:
    """Clean up async components.

    Args:
        ctx: Application context
    """
    print("Closing database connections...")
    await ctx.close()
    print("Goodbye!")


def run() -> None:
    """Run the application with qasync event loop."""
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Fidra")
    app.setOrganizationName("Fidra")

    # Set window icon (only needed for development - bundled app uses .icns from bundle)
    # Check if running from PyInstaller bundle
    is_bundled = getattr(sys, 'frozen', False)
    if not is_bundled:
        # Development mode - load icon from source
        icon_path = Path(__file__).resolve().parent / "fidra" / "ui" / "theme" / "icons" / "icon.svg"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

    # Check for first run (no settings file exists)
    settings_store = SettingsStore()
    is_first_run = not settings_store.exists()

    # Determine database path: command line arg > wizard > last opened > default
    db_path = None
    wizard_name = None
    wizard_initials = None

    if len(sys.argv) > 1:
        # Command line argument takes priority
        db_path = Path(sys.argv[1])
        if not db_path.exists():
            print(f"Warning: Database file not found: {db_path}")
            db_path = None

    # Show setup wizard on first run (if no command line arg)
    if is_first_run and db_path is None:
        wizard = SetupWizard()
        if wizard.exec():
            db_path = wizard.db_path
            wizard_name = wizard.user_name
            wizard_initials = wizard.user_initials
        else:
            # User cancelled setup wizard - exit
            sys.exit(0)

    # Set up qasync event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create application context
    ctx = ApplicationContext(db_path=db_path)

    # Apply wizard profile settings if from first run
    if wizard_name:
        ctx.settings.profile.name = wizard_name
        ctx.settings.profile.initials = wizard_initials or ""
        ctx.settings.profile.first_run_complete = True
        if db_path:
            ctx.settings.storage.last_file = db_path
        ctx.save_settings()

    # If no db_path specified, try to use last opened file from settings
    if db_path is None and ctx.settings.storage.last_file:
        last_file = ctx.settings.storage.last_file
        if last_file.exists():
            print(f"Restoring last database: {last_file}")
            ctx._db_path = last_file

    with loop:
        try:
            # Initialize async components
            loop.run_until_complete(async_main(ctx))

            # Create and show main window
            window = MainWindow(ctx)
            window.show()

            # Check for empty database and prompt opening balance after window is visible
            QTimer.singleShot(0, window.check_opening_balance)

            # Run Qt event loop (blocks until app quits)
            loop.run_forever()

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            # Cleanup async components
            loop.run_until_complete(async_cleanup(ctx))
            loop.close()


if __name__ == "__main__":
    run()
