"""Main application window with tab-based navigation."""

import asyncio
from datetime import date
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

import qasync
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext

from fidra.domain.models import PlannedTemplate
from fidra.ui.theme.engine import get_theme_engine, Theme
from fidra.ui.views.dashboard_view import DashboardView
from fidra.ui.views.transactions_view import TransactionsView
from fidra.ui.views.planned_view import PlannedView
from fidra.ui.views.reports_view import ReportsView
from fidra.ui.dialogs.manage_sheets_dialog import ManageSheetsDialog
from fidra.ui.dialogs.audit_log_dialog import AuditLogDialog
from fidra.ui.dialogs.backup_restore_dialog import BackupRestoreDialog
from fidra.ui.dialogs.financial_year_dialog import FinancialYearDialog
from fidra.ui.dialogs.manage_categories_dialog import ManageCategoriesDialog
from fidra.ui.dialogs.migration_dialog import MigrationDialog
from fidra.ui.dialogs.opening_balance_dialog import OpeningBalanceDialog
from fidra.ui.dialogs.profile_dialog import ProfileDialog
from fidra.ui.dialogs.supabase_config_dialog import SupabaseConfigDialog
from fidra.ui.dialogs.transaction_settings_dialog import TransactionSettingsDialog
from fidra.ui.components.notification_banner import NotificationBanner


class ViewIndex(IntEnum):
    """Indices for the stacked widget views."""

    DASHBOARD = 0
    TRANSACTIONS = 1
    PLANNED = 2
    REPORTS = 3


class MainWindow(QMainWindow):
    """Main application window with tab-based navigation.

    The main window provides a top bar with navigation tabs, a stacked
    widget for switching views, and a status bar for messages.
    """

    view_changed = Signal(int)  # Emitted when navigation changes

    def __init__(self, context: "ApplicationContext", window_manager=None):
        """Initialize main window.

        Args:
            context: Application context providing dependencies
            window_manager: Optional WindowManager for multi-window support
        """
        super().__init__()
        self._ctx = context
        self._state = context.state
        self._window_manager = window_manager

        # Apply theme before setting up UI - restore from settings
        self._theme_engine = get_theme_engine()
        saved_theme = context.settings.ui_state.theme
        initial_theme = Theme.DARK if saved_theme == "dark" else Theme.LIGHT
        self._theme_engine.apply_theme(initial_theme)

        self.setWindowTitle("Fidra")
        self.setMinimumSize(1000, 700)
        self.resize(1280, 800)

        self._setup_ui()
        self._connect_signals()

        # Start on Dashboard
        self.navigate_to(ViewIndex.DASHBOARD)

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar with navigation
        self.top_bar = self._create_top_bar()
        layout.addWidget(self.top_bar)

        # Notification banner (hidden by default)
        self.notification_banner = NotificationBanner()
        layout.addWidget(self.notification_banner)

        # Stacked widget for views
        self.stack = QStackedWidget()
        self.stack.setObjectName("mainStack")

        # Create views
        self.dashboard_view = DashboardView(self._ctx)
        self.transactions_view = TransactionsView(self._ctx)
        self.planned_view = PlannedView(self._ctx)
        self.reports_view = ReportsView(self._ctx)

        # Add views to stack
        self.stack.addWidget(self.dashboard_view)  # Index 0
        self.stack.addWidget(self.transactions_view)  # Index 1
        self.stack.addWidget(self.planned_view)  # Index 2
        self.stack.addWidget(self.reports_view)  # Index 3

        layout.addWidget(self.stack, 1)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("status_bar")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _create_top_bar(self) -> QWidget:
        """Create top bar with logo and navigation tabs.

        Returns:
            Top bar widget
        """
        bar = QWidget()
        bar.setObjectName("top_bar")
        bar.setFixedHeight(56)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(2)

        # Logo/Title
        logo_icon = QLabel()
        logo_icon.setObjectName("app_logo_icon")
        icon_height = 24
        try:
            svg_path = Path(__file__).parent.parent / "resources" / "logo.svg"
            if svg_path.exists():
                renderer = QSvgRenderer(str(svg_path))
                default_size = renderer.defaultSize()
                if default_size.isValid() and default_size.height() > 0:
                    aspect = default_size.width() / default_size.height()
                else:
                    aspect = 1.0
                icon_width = max(1, int(round(icon_height * aspect)))
                logo_icon.setFixedSize(icon_width, icon_height)

                dpr = self.devicePixelRatioF()
                pixmap = QPixmap(int(icon_width * dpr), int(icon_height * dpr))
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                renderer.render(painter, pixmap.rect())
                painter.end()
                pixmap.setDevicePixelRatio(dpr)
                logo_icon.setPixmap(pixmap)
        except Exception:
            pass
        layout.addWidget(logo_icon)

        logo = QLabel("Fidra")
        logo.setObjectName("app_logo")
        layout.addWidget(logo)

        layout.addSpacing(24)

        # Navigation buttons
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        nav_items = [
            ("Dashboard", ViewIndex.DASHBOARD),
            ("Transactions", ViewIndex.TRANSACTIONS),
            ("Planned", ViewIndex.PLANNED),
            ("Reports", ViewIndex.REPORTS),
        ]

        for label, index in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("nav_button")
            btn.setCheckable(True)
            btn.setProperty("viewIndex", index)
            self.nav_group.addButton(btn, index)
            layout.addWidget(btn)

        layout.addStretch()

        # Sheet selector
        sheet_label = QLabel("Sheet:")
        sheet_label.setObjectName("sheet_label")
        layout.addWidget(sheet_label)

        self.sheet_selector = QComboBox()
        self.sheet_selector.setObjectName("sheet_selector")
        self.sheet_selector.setMinimumWidth(160)
        self.sheet_selector.setMaxVisibleItems(10)
        self.sheet_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._updating_sheet_selector = False  # Flag to track programmatic changes
        self.sheet_selector.currentIndexChanged.connect(self._on_sheet_index_changed)
        layout.addWidget(self.sheet_selector)

        # Manage sheets button
        manage_sheets_btn = QPushButton("Manage")
        manage_sheets_btn.setObjectName("toolbar_button")
        manage_sheets_btn.clicked.connect(self._show_manage_sheets)
        layout.addWidget(manage_sheets_btn)

        layout.addSpacing(16)

        # Theme toggle button - set icon based on current theme
        current_theme = self._theme_engine.current_theme
        self.theme_btn = QPushButton("☀" if current_theme == Theme.DARK else "🌙")
        self.theme_btn.setObjectName("theme_button")
        self.theme_btn.setToolTip("Switch to light mode" if current_theme == Theme.DARK else "Switch to dark mode")
        self.theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_btn)

        # Settings button with menu
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("settings_button")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.clicked.connect(self._show_settings_menu)
        layout.addWidget(self.settings_btn)

        return bar

    def _create_placeholder_view(self, name: str) -> QWidget:
        """Create a placeholder view for Phase 1.

        Args:
            name: View name

        Returns:
            Placeholder widget
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel(f"{name} View")
        label.setObjectName("placeholder_title")
        layout.addWidget(label)

        desc = QLabel("(To be implemented in Phase 2+)")
        desc.setObjectName("placeholder_desc")
        layout.addWidget(desc)

        return widget

    def _connect_signals(self) -> None:
        """Connect Qt signals."""
        # Navigation
        self.nav_group.idClicked.connect(self.navigate_to)

        # State changes
        self._state.transactions.changed.connect(self._on_transactions_changed)
        self._state.current_sheet.changed.connect(self._on_sheet_changed)
        self._state.sheets.changed.connect(self._on_sheets_list_changed)
        self._state.error_message.changed.connect(self._show_error)
        self._state.planned_templates.changed.connect(self._check_past_planned_transactions)

        # UI state persistence - save when these change
        self._state.include_planned.changed.connect(self._on_ui_state_changed)
        self._state.filtered_balance_mode.changed.connect(self._on_ui_state_changed)
        self._state.current_sheet.changed.connect(self._on_ui_state_changed)

        # File watcher - reload data when database changes externally
        self._ctx.file_watcher.file_changed.connect(self._on_database_file_changed)

        # Initialize sheet selector with current state
        # (sheets may already be loaded by ApplicationContext before MainWindow was created)
        current_sheets = self._state.sheets.value
        if current_sheets:
            self._on_sheets_list_changed(current_sheets)
        else:
            # Load sheets if not already loaded
            self._load_sheets()

        # Check for past planned transactions on startup
        self._check_past_planned_transactions(self._state.planned_templates.value)

    def navigate_to(self, view_index: int) -> None:
        """Switch to a specific view.

        Args:
            view_index: ViewIndex enum value
        """
        self.stack.setCurrentIndex(view_index)

        # Update nav button state
        btn = self.nav_group.button(view_index)
        if btn:
            btn.setChecked(True)

        self.view_changed.emit(view_index)

    def _on_transactions_changed(self, transactions: list) -> None:
        """Handle transaction list changes.

        Args:
            transactions: Updated transaction list
        """
        count = len(transactions)
        self.status_bar.showMessage(f"{count} transaction{'s' if count != 1 else ''}")

    def _on_sheet_changed(self, sheet: str) -> None:
        """Handle sheet selection change.

        Args:
            sheet: Selected sheet name
        """
        if sheet == "All Sheets":
            self.setWindowTitle("Fidra - All Sheets")
        else:
            self.setWindowTitle(f"Fidra - {sheet}")

        # Reload transactions for the new sheet
        self._reload_transactions()

    def _show_error(self, message: str | None) -> None:
        """Show error message in status bar.

        Args:
            message: Error message, or None to clear
        """
        if message:
            self.status_bar.showMessage(f"Error: {message}", 5000)

    def _toggle_theme(self) -> None:
        """Toggle between light and dark themes."""
        current = self._theme_engine.current_theme
        if current == Theme.LIGHT:
            self._theme_engine.apply_theme(Theme.DARK)
            self.theme_btn.setText("☀")
            self.theme_btn.setToolTip("Switch to light mode")
            self._ctx.settings.ui_state.theme = "dark"
        else:
            self._theme_engine.apply_theme(Theme.LIGHT)
            self.theme_btn.setText("🌙")
            self.theme_btn.setToolTip("Switch to dark mode")
            self._ctx.settings.ui_state.theme = "light"

        # Save theme preference
        self._ctx.save_settings()

        # Refresh chart colors and table after theme change
        self.dashboard_view.refresh_theme()
        self.transactions_view.refresh_theme()
        self.reports_view.refresh_theme()

    def _show_settings_menu(self) -> None:
        """Show settings menu with database options."""
        menu = QMenu(self)

        # Current database info
        current_db = self._ctx.db_path
        db_info = menu.addAction(f"Current: {current_db.name}")
        db_info.setEnabled(False)

        menu.addSeparator()

        # Window actions (only if window manager is available)
        if self._window_manager:
            new_window_action = menu.addAction("New Window...")
            new_window_action.triggered.connect(self._new_window)
            menu.addSeparator()

        # Database actions
        open_action = menu.addAction("Open Database...")
        open_action.triggered.connect(self._open_database)

        new_action = menu.addAction("New Database...")
        new_action.triggered.connect(self._new_database)

        menu.addSeparator()

        # Backup & Restore
        backup_action = menu.addAction("Backup && Restore...")
        backup_action.triggered.connect(self._show_backup_restore)

        menu.addSeparator()

        # Supabase options
        supabase_action = menu.addAction("Configure Supabase...")
        supabase_action.triggered.connect(self._show_supabase_config)

        migrate_action = menu.addAction("Migrate Data...")
        migrate_action.triggered.connect(self._show_migration)

        # Show current backend status
        if self._ctx.is_supabase:
            backend_info = menu.addAction("Backend: Supabase (cloud)")
        else:
            backend_info = menu.addAction("Backend: SQLite (local)")
        backend_info.setEnabled(False)

        menu.addSeparator()

        # Profile settings
        profile_action = menu.addAction("Profile...")
        profile_action.triggered.connect(self._show_profile)

        # Category management
        categories_action = menu.addAction("Manage Categories...")
        categories_action.triggered.connect(self._show_manage_categories)

        # Transaction behavior settings
        transaction_settings_action = menu.addAction("Transaction Behavior...")
        transaction_settings_action.triggered.connect(self._show_transaction_settings)

        menu.addSeparator()

        # Financial year settings
        fy_action = menu.addAction("Financial Year...")
        fy_action.triggered.connect(self._show_financial_year_settings)

        # Audit log
        audit_action = menu.addAction("Audit Log...")
        audit_action.triggered.connect(self._show_audit_log)

        # Show menu below the settings button
        menu.exec(self.settings_btn.mapToGlobal(self.settings_btn.rect().bottomLeft()))

    def _show_manage_categories(self) -> None:
        """Show the manage categories dialog."""
        dialog = ManageCategoriesDialog(self._ctx, self)
        dialog.exec()

    def _show_profile(self) -> None:
        """Show the profile settings dialog."""
        dialog = ProfileDialog(self._ctx, self)
        dialog.exec()

    def _show_backup_restore(self) -> None:
        """Show the backup and restore dialog."""
        dialog = BackupRestoreDialog(self._ctx, self)
        if dialog.exec():
            # Reload data after potential restore
            self._reload_transactions()

    def _show_supabase_config(self) -> None:
        """Show the Supabase configuration dialog."""
        dialog = SupabaseConfigDialog(self._ctx, self)
        dialog.exec()

    def _show_migration(self) -> None:
        """Show the data migration dialog."""
        dialog = MigrationDialog(self._ctx, self)
        if dialog.exec():
            # Reload data after migration
            self._reload_transactions()

    def _show_financial_year_settings(self) -> None:
        """Show the financial year settings dialog."""
        dialog = FinancialYearDialog(self._ctx, self)
        dialog.exec()

    def _show_transaction_settings(self) -> None:
        """Show the transaction behavior settings dialog."""
        dialog = TransactionSettingsDialog(self._ctx, self)
        dialog.exec()

    def _show_audit_log(self) -> None:
        """Show the audit log viewer dialog."""
        dialog = AuditLogDialog(self._ctx, self)
        dialog.exec()

    @qasync.asyncSlot()
    async def _open_database(self) -> None:
        """Open an existing database file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Database",
            str(Path.home()),
            "All Databases (*.fdra *.db);;Fidra Files (*.fdra);;Legacy Database (*.db);;All Files (*)"
        )

        if file_path:
            path = Path(file_path)
            if path.exists():
                self.status_bar.showMessage(f"Opening {path.name}...")
                try:
                    await self._ctx.switch_database(path)
                    self.status_bar.showMessage(f"Opened {path.name}", 3000)
                    self.setWindowTitle(f"Fidra - {path.name}")
                except Exception as e:
                    self.status_bar.showMessage(f"Error opening database: {e}", 5000)

    @qasync.asyncSlot()
    async def _new_database(self) -> None:
        """Create a new database file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "New Database",
            str(Path.home() / "finances.fdra"),
            "Fidra Files (*.fdra);;All Files (*)"
        )

        if file_path:
            path = Path(file_path)
            # Ensure .fdra extension
            if not path.suffix:
                path = path.with_suffix('.fdra')

            self.status_bar.showMessage(f"Creating {path.name}...")
            try:
                await self._ctx.switch_database(path)
                self.status_bar.showMessage(f"Created {path.name}", 3000)
                self.setWindowTitle(f"Fidra - {path.name}")

                # Prompt for opening balance on new database
                await self._prompt_opening_balance()
            except Exception as e:
                self.status_bar.showMessage(f"Error creating database: {e}", 5000)

    @qasync.asyncSlot()
    async def _load_sheets(self) -> None:
        """Load sheets from repository and populate selector."""
        try:
            sheets = await self._ctx.sheet_repo.get_all()
            self._state.sheets.set(sheets)
        except Exception as e:
            self.status_bar.showMessage(f"Error loading sheets: {e}", 5000)

    def _on_sheets_list_changed(self, sheets: list) -> None:
        """Handle sheets list change.

        Args:
            sheets: Updated sheets list
        """
        # Filter out virtual and planned sheets - only real sheets in dropdown
        real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]

        # Sort by saved order (sheets not in order list go to end)
        saved_order = self._ctx.settings.sheet_order
        def sort_key(sheet):
            try:
                return saved_order.index(sheet.name)
            except ValueError:
                return len(saved_order) + 1  # Put unlisted sheets at end

        real_sheets = sorted(real_sheets, key=sort_key)

        # Set flag to ignore programmatic changes
        self._updating_sheet_selector = True

        # Remember current selection
        current = self._state.current_sheet.value

        # Update combo box based on number of real sheets
        self.sheet_selector.clear()

        # Get the manage button - always visible so users can add sheets
        manage_btn = self.findChild(QPushButton, "toolbar_button")

        if len(real_sheets) <= 1:
            # Single sheet or no sheets - hide selector, but keep Manage button
            # When there's only 1 sheet, "All Sheets" view IS that sheet's view (synonymous)
            self.sheet_selector.setVisible(False)
            self.findChild(QLabel, "sheet_label").setVisible(False)
            if manage_btn:
                manage_btn.setVisible(True)  # Always show Manage button

            # Use "All Sheets" which loads all transactions (no filtering)
            # With 0-1 sheets, this is equivalent to viewing that single sheet
            self._updating_sheet_selector = False
            if current != "All Sheets":
                self._state.current_sheet.set("All Sheets")
        else:
            # Multiple sheets - show selector with "All Sheets" option
            self.sheet_selector.setVisible(True)
            self.findChild(QLabel, "sheet_label").setVisible(True)
            if manage_btn:
                manage_btn.setVisible(True)

            # Add "All Sheets" as first option
            self.sheet_selector.addItem("All Sheets")

            # Add individual sheets (only real ones)
            for sheet in real_sheets:
                self.sheet_selector.addItem(sheet.name)

            # Restore selection
            if current == "All Sheets":
                self.sheet_selector.setCurrentIndex(0)
            else:
                index = self.sheet_selector.findText(current)
                if index >= 0:
                    self.sheet_selector.setCurrentIndex(index)
                else:
                    # Default to All Sheets view
                    self.sheet_selector.setCurrentIndex(0)
                    self._state.current_sheet.set("All Sheets")

            self._updating_sheet_selector = False

    def _on_sheet_index_changed(self, index: int) -> None:
        """Handle sheet selection from dropdown.

        Args:
            index: Selected index in combo box
        """
        # Ignore programmatic changes
        if self._updating_sheet_selector:
            return

        if index < 0:
            return

        sheet_name = self.sheet_selector.itemText(index)
        if not sheet_name:
            return

        if sheet_name != self._state.current_sheet.value:
            self._state.current_sheet.set(sheet_name)
            # Note: _on_sheet_changed will handle transaction reload

    @qasync.asyncSlot()
    async def _reload_transactions(self) -> None:
        """Reload transactions for current sheet."""
        try:
            sheet = self._state.current_sheet.value

            # "All Sheets" means load all transactions (sheet=None)
            if sheet == "All Sheets":
                transactions = await self._ctx.transaction_repo.get_all(sheet=None)
            else:
                transactions = await self._ctx.transaction_repo.get_all(sheet=sheet)

            self._state.transactions.set(transactions)
        except Exception as e:
            self.status_bar.showMessage(f"Error loading transactions: {e}", 5000)

    def _show_manage_sheets(self) -> None:
        """Show manage sheets dialog."""
        dialog = ManageSheetsDialog(self._ctx, self)
        dialog.exec()
        # Refresh sheets list after dialog closes
        self._load_sheets()

    def _check_past_planned_transactions(self, templates: list[PlannedTemplate]) -> None:
        """Check for planned templates with dates in the past.

        Args:
            templates: List of planned templates
        """
        if not templates:
            self.notification_banner.hide()
            return

        today = date.today()
        past_templates = []

        for template in templates:
            # Check if the start date is in the past
            if template.start_date < today:
                past_templates.append(template)

        if past_templates:
            count = len(past_templates)
            if count == 1:
                message = (
                    f"1 planned transaction has a date in the past. "
                    f"Past planned transactions are not included in the transactions table."
                )
            else:
                message = (
                    f"{count} planned transactions have dates in the past. "
                    f"Past planned transactions are not included in the transactions table."
                )

            self.notification_banner.show_warning(
                message,
                action_text="Review",
                action_callback=self._on_review_past_planned
            )
        else:
            self.notification_banner.hide()

    def _on_review_past_planned(self) -> None:
        """Navigate to planned view when user clicks Review."""
        self.navigate_to(ViewIndex.PLANNED)

    def _on_ui_state_changed(self, _: object) -> None:
        """Handle UI state change - save to settings."""
        self._ctx.save_ui_state()

    @qasync.asyncSlot()
    async def _on_database_file_changed(self) -> None:
        """Handle external database file changes - reload data."""
        self.status_bar.showMessage("Database changed externally, reloading...")
        try:
            await self._ctx._load_initial_data()
            self.status_bar.showMessage("Database reloaded", 3000)
        except Exception as e:
            self.status_bar.showMessage(f"Error reloading database: {e}", 5000)

    @qasync.asyncSlot()
    async def check_opening_balance(self) -> None:
        """Check first-run conditions and prompt user as needed.

        Called after the main window is shown on startup.
        Checks in order:
        1. Profile setup (if name is empty)
        2. Opening balance (if database is empty)
        """
        # First, check if profile needs to be set up
        # Skip if setup wizard was completed (first_run_complete=True) or if name exists
        if not self._ctx.settings.profile.first_run_complete and not self._ctx.settings.profile.name:
            self._prompt_profile_setup()

        # Then, check if opening balance is needed
        transactions = self._state.transactions.value
        if not transactions:
            await self._prompt_opening_balance()

    def _prompt_profile_setup(self) -> None:
        """Show the profile setup dialog for first-run."""
        dialog = ProfileDialog(self._ctx, self, first_run=True)
        dialog.exec()

    async def _prompt_opening_balance(self) -> None:
        """Show the opening balance dialog and save the result."""
        # Determine the default sheet name
        sheets = self._state.sheets.value
        real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]
        sheet_name = real_sheets[0].name if real_sheets else "Main"

        dialog = OpeningBalanceDialog(self, sheet_name=sheet_name)
        result = dialog.exec()

        if result == OpeningBalanceDialog.DialogCode.Accepted:
            transaction = dialog.get_transaction()
            if transaction:
                try:
                    # Ensure the sheet exists
                    if not real_sheets:
                        from fidra.domain.models import Sheet
                        new_sheet = Sheet.create(name="Main")
                        await self._ctx.sheet_repo.save(new_sheet)
                        sheets = await self._ctx.sheet_repo.get_all()
                        self._state.sheets.set(sheets)

                    await self._ctx.transaction_repo.save(transaction)

                    # Reload transactions
                    all_transactions = await self._ctx.transaction_repo.get_all()
                    self._state.transactions.set(all_transactions)

                    self.status_bar.showMessage("Opening balance set", 3000)
                except Exception as e:
                    self.status_bar.showMessage(f"Error saving opening balance: {e}", 5000)

    def _new_window(self) -> None:
        """Open a new window by selecting a file."""
        if not self._window_manager:
            return

        # Show file dialog directly
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Database in New Window",
            str(Path.home()),
            "All Databases (*.fdra *.db);;Fidra Files (*.fdra);;Legacy Database (*.db);;All Files (*)"
        )

        if file_path:
            path = Path(file_path)
            if path.exists():
                # Check if already open
                if self._window_manager.is_file_open(path):
                    self._window_manager.focus_window_for_file(path)
                else:
                    # Create window asynchronously
                    asyncio.create_task(self._window_manager.create_window_async(path))

    def closeEvent(self, event) -> None:
        """Handle window close event.

        If using window manager, notify it and let it handle cleanup.
        Otherwise, accept the close and let the app quit.
        """
        if self._window_manager:
            # Save UI state before closing
            self._ctx.save_ui_state()

            # Notify window manager
            self._window_manager.close_window(self)

        event.accept()
