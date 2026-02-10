"""Transactions view - main transaction management interface."""

from typing import TYPE_CHECKING, Optional

from datetime import date, timedelta
import asyncio

import qasync
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QMessageBox,
    QLabel,
    QApplication,
    QFrame,
    QPushButton,
    QSizePolicy,
    QSlider,
)
from PySide6.QtGui import QShortcut, QKeySequence

from fidra.ui.components.add_form import AddTransactionForm
from fidra.ui.components.transaction_table import TransactionTable
from fidra.ui.components.balance_display import BalanceDisplayWidget
from fidra.ui.components.search_bar import SearchBar
from fidra.ui.dialogs.edit_dialog import EditTransactionDialog
from fidra.ui.dialogs.view_transaction_dialog import ViewTransactionDialog
from fidra.ui.dialogs.bulk_edit_dialog import BulkEditTransactionDialog
from fidra.ui.dialogs.export_dialog import ExportDialog
from fidra.ui.dialogs.edit_planned_dialog import EditPlannedDialog
from fidra.ui.dialogs.conflict_resolution_dialog import (
    ConflictResolutionDialog,
    ConflictResolution,
)
from fidra.data.repository import ConcurrencyError
from fidra.services.undo import (
    AddTransactionCommand,
    EditTransactionCommand,
    DeleteTransactionCommand,
    BulkEditCommand,
    DeletePlannedCommand,
    EditPlannedCommand,
    CompositeCommand,
)
from fidra.domain.models import Transaction, TransactionType, ApprovalStatus

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class TransactionsView(QWidget):
    """Main transactions view.

    Layout:
    - Top: Page header with title and summary stats
    - Toolbar: Search bar, filters, and action buttons
    - Main: Three-panel layout (Add form | Table | Balance)
    """

    def __init__(self, context: "ApplicationContext", parent=None):
        """Initialize the transactions view.

        Args:
            context: Application context
            parent: Parent widget
        """
        super().__init__(parent)
        self._context = context
        self._current_search_query = ""  # Current search query
        self._filtered_transactions = []  # Transactions after search filter
        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()

        # Initialize add form with current sheets
        self._init_add_form()

        # Restore filter mode from state
        self.search_bar.set_filter_mode(self._context.state.filtered_balance_mode.value)

        # Display transactions already loaded in state
        # (loaded during app initialization)
        transactions = self._context.state.transactions.value
        if transactions:
            self._on_transactions_changed(transactions)

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ===== PAGE HEADER =====
        header_frame = QFrame()
        header_frame.setObjectName("transactions_header")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(24, 20, 24, 16)
        header_layout.setSpacing(4)

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(16)

        page_title = QLabel("Transactions")
        page_title.setObjectName("page_header")
        title_row.addWidget(page_title)

        title_row.addStretch()

        # Quick stats in header
        self.header_stats = QLabel("")
        self.header_stats.setObjectName("header_stats")
        title_row.addWidget(self.header_stats)

        header_layout.addLayout(title_row)

        layout.addWidget(header_frame)

        # ===== TOOLBAR =====
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("transactions_toolbar")
        toolbar_layout = QHBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(24, 12, 24, 12)
        toolbar_layout.setSpacing(12)

        # Search bar (takes most space)
        self.search_bar = SearchBar()
        toolbar_layout.addWidget(self.search_bar, 1)

        # Separator
        sep1 = QFrame()
        sep1.setObjectName("toolbar_separator")
        sep1.setFixedWidth(1)
        sep1.setFixedHeight(24)
        toolbar_layout.addWidget(sep1)

        # Toggle form panel button
        self.toggle_form_btn = QPushButton("◀")
        self.toggle_form_btn.setObjectName("toolbar_icon_button")
        self.toggle_form_btn.setToolTip("Hide add transaction form")
        self.toggle_form_btn.setFixedWidth(32)
        self.toggle_form_btn.clicked.connect(self._toggle_form_panel)
        toolbar_layout.addWidget(self.toggle_form_btn)

        # Separator
        sep0 = QFrame()
        sep0.setObjectName("toolbar_separator")
        sep0.setFixedWidth(1)
        sep0.setFixedHeight(24)
        toolbar_layout.addWidget(sep0)

        # Show Planned toggle button - restore from state
        self.show_planned_btn = QPushButton("Show Planned")
        self.show_planned_btn.setObjectName("filter_toggle")
        self.show_planned_btn.setCheckable(True)
        self.show_planned_btn.setChecked(self._context.state.include_planned.value)
        self.show_planned_btn.clicked.connect(self._on_show_planned_changed)
        toolbar_layout.addWidget(self.show_planned_btn)

        # Horizon controls (collapsible with animation when Show Planned toggles)
        self._horizon_controls_width = 150
        self.horizon_controls = QWidget()
        horizon_layout = QHBoxLayout(self.horizon_controls)
        horizon_layout.setContentsMargins(0, 0, 0, 0)
        horizon_layout.setSpacing(8)

        self.horizon_label = QLabel()
        self.horizon_label.setObjectName("toolbar_label")
        self._update_horizon_label()
        horizon_layout.addWidget(self.horizon_label)

        self.horizon_slider = QSlider(Qt.Horizontal)
        self.horizon_slider.setObjectName("horizon_slider")
        self.horizon_slider.setMinimum(7)
        self.horizon_slider.setMaximum(730)
        self.horizon_slider.setValue(self._context.settings.forecast.horizon_days)
        self.horizon_slider.setFixedWidth(100)
        self.horizon_slider.setToolTip("Adjust how far into the future to show planned transactions")
        self.horizon_slider.valueChanged.connect(self._on_horizon_changed)
        horizon_layout.addWidget(self.horizon_slider)

        toolbar_layout.addWidget(self.horizon_controls)

        # Animations for horizon controls (animate both min/max width like form panel)
        self._horizon_anim_max = QPropertyAnimation(self.horizon_controls, b"maximumWidth")
        self._horizon_anim_max.setDuration(200)
        self._horizon_anim_max.setEasingCurve(QEasingCurve.InOutQuad)

        self._horizon_anim_min = QPropertyAnimation(self.horizon_controls, b"minimumWidth")
        self._horizon_anim_min.setDuration(200)
        self._horizon_anim_min.setEasingCurve(QEasingCurve.InOutQuad)

        # Initial expanded/collapsed state from Show Planned.
        show_planned = self.show_planned_btn.isChecked()
        initial_width = self._horizon_controls_width if show_planned else 0
        self.horizon_controls.setMaximumWidth(initial_width)
        self.horizon_controls.setMinimumWidth(initial_width)

        # Export button
        export_btn = QPushButton("Export")
        export_btn.setObjectName("toolbar_button")
        export_btn.clicked.connect(self._on_export_dialog)
        toolbar_layout.addWidget(export_btn)

        layout.addWidget(toolbar_frame)

        # ===== MAIN CONTENT =====
        content_frame = QWidget()
        content_frame.setObjectName("transactions_content")
        content_layout = QHBoxLayout(content_frame)
        content_layout.setContentsMargins(24, 16, 24, 24)
        content_layout.setSpacing(16)

        # Left panel: Add form in a card (collapsible)
        self._form_panel_width = 280
        self._form_panel_visible = True

        self.form_card = QFrame()
        self.form_card.setObjectName("form_card")
        self.form_card.setFixedWidth(self._form_panel_width)
        form_layout = QVBoxLayout(self.form_card)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(0)

        self.add_form = AddTransactionForm(
            sheet=self._context.state.current_sheet.value,
            context=self._context
        )
        form_layout.addWidget(self.add_form)

        content_layout.addWidget(self.form_card)

        # Animation for form panel (animate both min and max width for smooth collapse)
        self._form_anim_max = QPropertyAnimation(self.form_card, b"maximumWidth")
        self._form_anim_max.setDuration(200)
        self._form_anim_max.setEasingCurve(QEasingCurve.InOutQuad)

        self._form_anim_min = QPropertyAnimation(self.form_card, b"minimumWidth")
        self._form_anim_min.setDuration(200)
        self._form_anim_min.setEasingCurve(QEasingCurve.InOutQuad)

        # Center: Transaction table
        table_container = QFrame()
        table_container.setObjectName("table_container")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)

        self.transaction_table = TransactionTable()
        table_layout.addWidget(self.transaction_table)

        content_layout.addWidget(table_container, 1)

        # Right panel: Balance card
        balance_card = QFrame()
        balance_card.setObjectName("balance_card")
        balance_card.setFixedWidth(260)
        balance_layout = QVBoxLayout(balance_card)
        balance_layout.setContentsMargins(0, 0, 0, 0)
        balance_layout.setSpacing(0)

        self.balance_display = BalanceDisplayWidget()
        balance_layout.addWidget(self.balance_display)

        content_layout.addWidget(balance_card)

        layout.addWidget(content_frame, 1)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        # Add form
        self.add_form.transaction_added.connect(self._on_transaction_added)

        # Search bar
        self.search_bar.search_changed.connect(self._on_search_changed)
        self.search_bar.filter_mode_changed.connect(self._on_filter_mode_changed)

        # Table actions
        self.transaction_table.edit_requested.connect(self._on_edit_requested)
        self.transaction_table.bulk_edit_requested.connect(self._on_bulk_edit_requested)
        self.transaction_table.delete_requested.connect(self._on_delete_requested)
        self.transaction_table.duplicate_requested.connect(self._on_duplicate_requested)
        self.transaction_table.approve_requested.connect(self._on_approve_requested)
        self.transaction_table.reject_requested.connect(self._on_reject_requested)
        self.transaction_table.convert_to_actual_requested.connect(self._on_convert_to_actual_requested)
        self.transaction_table.skip_instance_requested.connect(self._on_skip_instance_requested)
        self.transaction_table.delete_template_requested.connect(self._on_delete_template_requested)

        # Table selection changes
        self.transaction_table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # State changes
        self._context.state.transactions.changed.connect(self._on_transactions_changed)
        self._context.state.planned_templates.changed.connect(self._on_planned_templates_changed)
        self._context.state.current_sheet.changed.connect(self._on_sheet_changed)
        self._context.state.sheets.changed.connect(self._on_sheets_list_changed)

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts."""
        # Undo/Redo
        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_shortcut.activated.connect(self._on_undo)

        redo_shortcut = QShortcut(QKeySequence.StandardKey.Redo, self)
        redo_shortcut.activated.connect(self._on_redo)

        # New transaction (focus add form)
        new_shortcut = QShortcut(QKeySequence.StandardKey.New, self)
        new_shortcut.activated.connect(self._on_new_transaction)

        # Submit add form
        submit_shortcut = QShortcut(QKeySequence("Shift+Return"), self)
        submit_shortcut.activated.connect(self._on_submit_shortcut)

        # Delete selected transactions
        delete_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self)
        delete_shortcut.activated.connect(self._on_delete_shortcut)

        # Edit selected transaction (E key)
        edit_shortcut = QShortcut(QKeySequence("E"), self)
        edit_shortcut.activated.connect(self._on_edit_shortcut)

        # Approve selected
        approve_shortcut = QShortcut(QKeySequence("A"), self)
        approve_shortcut.activated.connect(self._on_approve_shortcut)

        # Reject selected
        reject_shortcut = QShortcut(QKeySequence("R"), self)
        reject_shortcut.activated.connect(self._on_reject_shortcut)

        # View selected transaction (I key)
        view_shortcut = QShortcut(QKeySequence("I"), self)
        view_shortcut.activated.connect(self._on_view_shortcut)

        # Export dialog (Cmd/Ctrl+E doesn't work well, use Cmd/Ctrl+Shift+E)
        export_shortcut = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        export_shortcut.activated.connect(self._on_export_dialog)

        # Duplicate selected transaction (Cmd/Ctrl+D)
        duplicate_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        duplicate_shortcut.activated.connect(self._on_duplicate_shortcut)

        # Copy to clipboard (C key)
        copy_shortcut = QShortcut(QKeySequence("C"), self)
        copy_shortcut.activated.connect(self._on_copy_to_clipboard)

    def _init_add_form(self) -> None:
        """Initialize add form with current sheets and sheet mode."""
        sheets = self._context.state.sheets.value
        current_sheet = self._context.state.current_sheet.value

        # Set available sheets first (before setting sheet mode)
        if sheets:
            sheet_names = self._get_ordered_sheet_names(sheets)
            self.add_form.set_available_sheets(sheet_names)

        # Then set the current sheet mode
        self.add_form.set_sheet(current_sheet)

        # Update table sheet column visibility
        if current_sheet == "All Sheets" and sheets:
            real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]
            self.transaction_table.set_show_sheet_column(len(real_sheets) >= 2)
        else:
            self.transaction_table.set_show_sheet_column(False)

    @qasync.asyncSlot()
    async def _load_transactions(self) -> None:
        """Load transactions from repository."""
        try:
            sheet = self._context.state.current_sheet.value
            transactions = await self._context.transaction_repo.get_all(sheet=sheet)
            self._context.state.transactions.set(transactions)
        except Exception as e:
            print(f"Error loading transactions: {e}")

    def _on_transactions_changed(self, transactions: list[Transaction]) -> None:
        """Handle transactions list change.

        Args:
            transactions: Updated transaction list
        """
        # Update header stats
        actuals = self._get_actuals_for_current_sheet(transactions)
        total_count = len(actuals)
        pending_count = sum(1 for t in actuals if t.status == ApprovalStatus.PENDING)
        if pending_count > 0:
            self.header_stats.setText(f"{total_count} transactions · {pending_count} pending approval")
        else:
            self.header_stats.setText(f"{total_count} transactions")

        # Get base transactions (with Show Planned, but before search filter)
        if self.show_planned_btn.isChecked():
            planned_instances = self._get_planned_instances_for_current_sheet()

            base_transactions = actuals + planned_instances
            base_transactions.sort(key=lambda t: (t.date, t.created_at))
        else:
            base_transactions = actuals

        # Get display list (after search filter)
        display_transactions = self._get_display_transactions()
        self._filtered_transactions = display_transactions

        # Update table
        self.transaction_table.set_transactions(display_transactions)

        # Update search result count
        self.search_bar.set_result_count(len(display_transactions), len(base_transactions))

        # Update balance
        # Decide whether to use all transactions or filtered ones
        if self.search_bar.is_filter_mode():
            # Filtered balance mode: only count visible (filtered) transactions
            balance_transactions = [t for t in display_transactions if t.status != ApprovalStatus.PLANNED]
        else:
            # Normal mode: count all actual transactions regardless of filter
            balance_transactions = actuals

        current_total = self._context.balance_service.compute_total(balance_transactions)

        filtered_active = (
            self.search_bar.is_filter_mode()
            and bool(self._current_search_query.strip())
        )

        # Projected balance: if Show Planned is ON, calculate from mixed list
        projected_total = None
        if self.show_planned_btn.isChecked():
            # Project balance from current balance + planned instances
            # Include pending expenses in the forecast (current_total excludes them)
            horizon = date.today() + timedelta(days=self._context.settings.forecast.horizon_days)
            pending_total = self._context.balance_service.compute_pending_total(balance_transactions)
            starting_balance = current_total - pending_total  # Include pending expenses
            planned_source = display_transactions if filtered_active else base_transactions
            planned_instances_for_balance = [
                t for t in planned_source if t.status == ApprovalStatus.PLANNED
            ]
            projected_total = self._context.forecast_service.project_balance(
                starting_balance,  # Start from balance including pending
                planned_instances_for_balance,  # Add planned instances
                horizon
            )

        self.balance_display.set_balance(
            current_total,
            projected=projected_total,
            filtered=filtered_active,
        )

    def _get_display_transactions(self) -> list[Transaction]:
        """Get transactions to display based on Show Planned toggle and search filter.

        Returns:
            List of transactions (actual only, or actual + planned), with search applied
        """
        actuals = self._get_actuals_for_current_sheet(self._context.state.transactions.value)

        # If Show Planned is OFF, just return actuals
        if not self.show_planned_btn.isChecked():
            base_transactions = actuals
        else:
            # Get planned instances relevant to the current sheet/view.
            planned_instances = self._get_planned_instances_for_current_sheet()

            # Mix actuals and planned, sort chronologically
            base_transactions = actuals + planned_instances
            base_transactions.sort(key=lambda t: (t.date, t.created_at))

        # Apply search filter if query is present
        if self._current_search_query and self._current_search_query.strip():
            filtered = self._context.search_service.search(
                base_transactions,
                self._current_search_query
            )
            return filtered
        else:
            return base_transactions

    def _get_planned_instances_for_current_sheet(self) -> list[Transaction]:
        """Expand planned templates, scoped to current sheet unless in All Sheets."""
        templates = self._context.state.planned_templates.value
        current_sheet = self._context.state.current_sheet.value
        horizon = date.today() + timedelta(days=self._context.settings.forecast.horizon_days)

        # In specific-sheet mode, only include planned templates targeting that sheet.
        if current_sheet != "All Sheets":
            templates = [t for t in templates if t.target_sheet == current_sheet]

        planned_instances: list[Transaction] = []
        for template in templates:
            instances = self._context.forecast_service.expand_template(
                template,
                horizon,
                include_past=False
            )
            planned_instances.extend(instances)

        return planned_instances

    def _get_actuals_for_current_sheet(self, transactions: list[Transaction]) -> list[Transaction]:
        """Filter actual transactions to current sheet unless in All Sheets."""
        current_sheet = self._context.state.current_sheet.value
        if current_sheet == "All Sheets":
            return transactions
        return [t for t in transactions if t.sheet == current_sheet]

    def _toggle_form_panel(self) -> None:
        """Toggle the add transaction form panel visibility with animation."""
        self._form_panel_visible = not self._form_panel_visible

        if self._form_panel_visible:
            # Show panel - animate from 0 to full width
            self._form_anim_max.setStartValue(0)
            self._form_anim_max.setEndValue(self._form_panel_width)
            self._form_anim_min.setStartValue(0)
            self._form_anim_min.setEndValue(self._form_panel_width)
            self.toggle_form_btn.setText("◀")
            self.toggle_form_btn.setToolTip("Hide add transaction form")
        else:
            # Hide panel - animate from full width to 0
            self._form_anim_max.setStartValue(self._form_panel_width)
            self._form_anim_max.setEndValue(0)
            self._form_anim_min.setStartValue(self._form_panel_width)
            self._form_anim_min.setEndValue(0)
            self.toggle_form_btn.setText("▶")
            self.toggle_form_btn.setToolTip("Show add transaction form")

        self._form_anim_max.start()
        self._form_anim_min.start()

    def _on_show_planned_changed(self) -> None:
        """Handle Show Planned toggle state change."""
        # Update app state (triggers persistence)
        is_checked = self.show_planned_btn.isChecked()
        self._context.state.include_planned.set(is_checked)

        # Animate horizon controls collapse/expand
        if is_checked:
            self._horizon_anim_max.setStartValue(self.horizon_controls.maximumWidth())
            self._horizon_anim_max.setEndValue(self._horizon_controls_width)
            self._horizon_anim_min.setStartValue(self.horizon_controls.minimumWidth())
            self._horizon_anim_min.setEndValue(self._horizon_controls_width)
        else:
            self._horizon_anim_max.setStartValue(self.horizon_controls.maximumWidth())
            self._horizon_anim_max.setEndValue(0)
            self._horizon_anim_min.setStartValue(self.horizon_controls.minimumWidth())
            self._horizon_anim_min.setEndValue(0)
        self._horizon_anim_max.start()
        self._horizon_anim_min.start()

        # Refresh the display
        self._on_transactions_changed(self._context.state.transactions.value)

    def _update_horizon_label(self) -> None:
        """Update the horizon label text."""
        days = self._context.settings.forecast.horizon_days
        if days < 30:
            self.horizon_label.setText(f"{days}d")
        elif days < 365:
            months = days // 30
            self.horizon_label.setText(f"~{months}mo")
        else:
            years = days / 365
            self.horizon_label.setText(f"~{years:.1f}yr")

    def _on_horizon_changed(self, value: int) -> None:
        """Handle horizon slider change."""
        self._context.settings.forecast.horizon_days = value
        self._context.save_settings()
        self._update_horizon_label()
        # Refresh display if show planned is on
        if self.show_planned_btn.isChecked():
            self._on_transactions_changed(self._context.state.transactions.value)

    def _on_search_changed(self, query: str) -> None:
        """Handle search query change.

        Args:
            query: New search query
        """
        self._current_search_query = query
        # Refresh the display with new filter
        self._on_transactions_changed(self._context.state.transactions.value)

    def _on_filter_mode_changed(self, enabled: bool) -> None:
        """Handle filtered balance mode change.

        Args:
            enabled: Whether filtered balance mode is enabled
        """
        # Update app state (triggers persistence)
        self._context.state.filtered_balance_mode.set(enabled)
        # Refresh balance display
        self._on_transactions_changed(self._context.state.transactions.value)

    @qasync.asyncSlot(object)
    async def _on_transaction_added(self, transaction: Transaction) -> None:
        """Handle new transaction from add form.

        Args:
            transaction: New transaction to add
        """
        try:
            # Create command
            command = AddTransactionCommand(
                self._context.transaction_repo, transaction,
                audit_service=self._context.audit_service,
            )

            # Execute through undo stack
            await self._context.undo_stack.execute(command)

            # Reload transactions
            await self._load_transactions()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add transaction: {e}")

    def _on_edit_requested(self, transaction: Transaction) -> None:
        """Handle edit request from table.

        Args:
            transaction: Transaction to edit
        """
        # Get available sheets for the dialog
        sheets = self._context.state.sheets.value
        available_sheets = self._get_ordered_sheet_names(sheets)

        # Show edit dialog with available sheets and context for autocomplete
        dialog = EditTransactionDialog(
            transaction, self,
            available_sheets=available_sheets,
            context=self._context
        )
        if dialog.exec() == QMessageBox.Accepted:
            edited = dialog.get_edited_transaction()
            asyncio.create_task(self._finalize_edit(transaction, edited, dialog))

    async def _finalize_edit(
        self,
        transaction: Transaction,
        edited: Transaction | None,
        dialog: EditTransactionDialog,
    ) -> None:
        """Finalize edit: save transaction and process attachments."""
        if edited:
            await self._save_edited_transaction(transaction, edited)

        # Use edited transaction for attachment naming, fall back to original
        trans_for_naming = edited if edited else transaction
        await self._process_attachment_changes(
            transaction.id,
            dialog.get_pending_attachments(),
            dialog.get_pending_removals(),
            trans_for_naming,
        )

    async def _save_edited_transaction(
        self, original: Transaction, edited: Transaction
    ) -> None:
        """Save an edited transaction, handling conflicts.

        Args:
            original: Original transaction
            edited: Edited transaction
        """
        try:
            # Create command
            command = EditTransactionCommand(
                self._context.transaction_repo,
                original,
                edited,
                audit_service=self._context.audit_service,
            )

            # Execute through undo stack
            await self._context.undo_stack.execute(command)

            # Reload transactions
            await self._load_transactions()

        except ConcurrencyError:
            # Version conflict - fetch current DB version and show resolution dialog
            await self._handle_edit_conflict(edited)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to edit transaction: {e}")

    async def _handle_edit_conflict(self, local_transaction: Transaction) -> None:
        """Handle a version conflict during edit.

        Args:
            local_transaction: The user's edited version
        """
        # Fetch current database version
        db_transaction = await self._context.transaction_repo.get_by_id(
            local_transaction.id
        )

        if db_transaction is None:
            QMessageBox.warning(
                self,
                "Transaction Deleted",
                "This transaction was deleted by another user."
            )
            await self._load_transactions()
            return

        # Show conflict resolution dialog
        dialog = ConflictResolutionDialog(local_transaction, db_transaction, self)
        if dialog.exec() == QMessageBox.Accepted:
            resolution = dialog.get_resolution()
            resolved = dialog.get_resolved_transaction()

            if resolution == ConflictResolution.KEEP_MINE and resolved:
                # Force save with updated version
                try:
                    await self._context.transaction_repo.save(resolved)
                    await self._load_transactions()
                except Exception as e:
                    QMessageBox.critical(
                        self, "Error", f"Failed to save resolved transaction: {e}"
                    )

            elif resolution == ConflictResolution.USE_THEIRS:
                # Just reload - the DB version is already there
                await self._load_transactions()
        else:
            # User cancelled - just reload to show current state
            await self._load_transactions()

    @qasync.asyncSlot(list)
    async def _on_bulk_edit_requested(self, transactions: list[Transaction]) -> None:
        """Handle bulk edit request from table.

        Args:
            transactions: Transactions to bulk edit
        """
        # Get available sheets for the dialog
        sheets = self._context.state.sheets.value
        available_sheets = self._get_ordered_sheet_names(sheets)

        # Show bulk edit dialog
        dialog = BulkEditTransactionDialog(
            transactions,
            self,
            available_sheets=available_sheets,
            context=self._context,
        )
        if dialog.exec() == QMessageBox.Accepted:
            if not dialog.has_changes():
                return  # No changes selected

            edited_list = dialog.get_edited_transactions()
            if edited_list:
                try:
                    # Create bulk edit command
                    command = BulkEditCommand(
                        self._context.transaction_repo,
                        transactions,  # originals
                        edited_list,   # edited versions
                        audit_service=self._context.audit_service,
                    )

                    # Execute through undo stack
                    await self._context.undo_stack.execute(command)

                    # Reload transactions
                    await self._load_transactions()

                except ConcurrencyError:
                    QMessageBox.warning(
                        self,
                        "Conflict Detected",
                        "One or more transactions were modified by another user.\n\n"
                        "The data has been refreshed. Please review and try again."
                    )
                    await self._load_transactions()

                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to bulk edit transactions: {e}")

    @qasync.asyncSlot(list)
    async def _on_delete_requested(self, transactions: list[Transaction]) -> None:
        """Handle delete request from table.

        Args:
            transactions: Transactions to delete
        """
        # Confirm deletion
        count = len(transactions)
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete {count} transaction{'s' if count != 1 else ''}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                # Create delete commands for each transaction
                for trans in transactions:
                    command = DeleteTransactionCommand(
                        self._context.transaction_repo,
                        trans,
                        audit_service=self._context.audit_service,
                    )
                    await self._context.undo_stack.execute(command)

                # Reload transactions
                await self._load_transactions()

            except ConcurrencyError:
                QMessageBox.warning(
                    self,
                    "Conflict Detected",
                    "One or more transactions were modified by another user.\n\n"
                    "The data has been refreshed. Please review and try again."
                )
                await self._load_transactions()

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")

    def _on_duplicate_shortcut(self) -> None:
        """Handle Cmd/Ctrl+D shortcut for duplicating."""
        selected = self.transaction_table.get_selected_transactions()
        # Filter out planned transactions
        actual_only = [t for t in selected if t.status != ApprovalStatus.PLANNED]
        if actual_only:
            self._on_duplicate_requested(actual_only)

    @qasync.asyncSlot(list)
    async def _on_duplicate_requested(self, transactions: list[Transaction]) -> None:
        """Handle duplicate request from table or shortcut.

        Creates copies of the selected transactions with new IDs and today's date.

        Args:
            transactions: Transactions to duplicate
        """
        try:
            from datetime import date as date_cls

            for trans in transactions:
                # Create a new transaction based on the original
                new_trans = Transaction.create(
                    date=date_cls.today(),
                    description=trans.description,
                    amount=trans.amount,
                    type=trans.type,
                    status=ApprovalStatus.PENDING if trans.type == TransactionType.EXPENSE else ApprovalStatus.AUTO,
                    sheet=trans.sheet,
                    category=trans.category,
                    party=trans.party,
                    notes=trans.notes,
                )

                # Save through undo stack
                command = AddTransactionCommand(
                    self._context.transaction_repo, new_trans,
                    audit_service=self._context.audit_service,
                )
                await self._context.undo_stack.execute(command)

            # Reload transactions
            await self._load_transactions()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to duplicate: {e}")

    @qasync.asyncSlot(list)
    async def _on_approve_requested(self, transactions: list[Transaction]) -> None:
        """Handle approve request from table.

        Args:
            transactions: Transactions to approve
        """
        try:
            # Create updated versions with APPROVED status
            old_states = transactions

            # Check if we should also set date to today
            updates = {"status": ApprovalStatus.APPROVED}
            if self._context.settings.transactions.date_on_approve:
                updates["date"] = date.today()

            new_states = [t.with_updates(**updates) for t in transactions]

            # Create bulk edit command
            command = BulkEditCommand(
                self._context.transaction_repo,
                old_states,
                new_states,
                audit_service=self._context.audit_service,
            )

            # Execute through undo stack
            await self._context.undo_stack.execute(command)

            # Reload transactions
            await self._load_transactions()

        except ConcurrencyError:
            QMessageBox.warning(
                self,
                "Conflict Detected",
                "One or more transactions were modified by another user.\n\n"
                "The data has been refreshed. Please review and try again."
            )
            await self._load_transactions()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to approve: {e}")

    @qasync.asyncSlot(list)
    async def _on_reject_requested(self, transactions: list[Transaction]) -> None:
        """Handle reject request from table.

        Args:
            transactions: Transactions to reject
        """
        try:
            # Create updated versions with REJECTED status
            old_states = transactions
            new_states = [t.with_updates(status=ApprovalStatus.REJECTED) for t in transactions]

            # Create bulk edit command
            command = BulkEditCommand(
                self._context.transaction_repo,
                old_states,
                new_states,
                audit_service=self._context.audit_service,
            )

            # Execute through undo stack
            await self._context.undo_stack.execute(command)

            # Reload transactions
            await self._load_transactions()

        except ConcurrencyError:
            QMessageBox.warning(
                self,
                "Conflict Detected",
                "One or more transactions were modified by another user.\n\n"
                "The data has been refreshed. Please review and try again."
            )
            await self._load_transactions()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reject: {e}")

    @qasync.asyncSlot(list)
    async def _on_convert_to_actual_requested(self, planned_transactions: list[Transaction]) -> None:
        """Handle convert to actual request from table.

        Args:
            planned_transactions: Planned transactions to convert to actual
        """
        try:
            from fidra.domain.models import Frequency

            for planned_trans in planned_transactions:
                # Create actual transaction with appropriate status
                if planned_trans.type == TransactionType.INCOME:
                    status = ApprovalStatus.AUTO
                else:
                    status = ApprovalStatus.PENDING

                # Build updates - optionally set date to today on conversion
                updates = {"status": status}
                if self._context.settings.transactions.date_on_planned_conversion:
                    updates["date"] = date.today()

                actual_transaction = planned_trans.with_updates(**updates)

                # Build commands for composite undo
                commands = []

                # Command to add actual transaction
                add_cmd = AddTransactionCommand(
                    self._context.transaction_repo, actual_transaction,
                    audit_service=self._context.audit_service,
                )
                commands.append(add_cmd)

                # Find the template that generated this instance
                templates = self._context.state.planned_templates.value
                for template in templates:
                    # Check if this transaction matches the template
                    if (template.description == planned_trans.description and
                        template.amount == planned_trans.amount and
                        template.type == planned_trans.type):
                        # Check if this is a one-time template
                        if template.frequency == Frequency.ONCE:
                            # Delete the template entirely
                            delete_cmd = DeletePlannedCommand(
                                self._context.planned_repo,
                                template,
                            )
                            commands.append(delete_cmd)
                        else:
                            # Mark as fulfilled for this date (recurring template)
                            updated_template = template.mark_fulfilled(planned_trans.date)
                            edit_cmd = EditPlannedCommand(
                                self._context.planned_repo,
                                template,
                                updated_template,
                            )
                            commands.append(edit_cmd)
                        break

                # Execute as composite command (single undo step)
                composite = CompositeCommand(
                    commands,
                    f"Convert planned: {planned_trans.description}"
                )
                await self._context.undo_stack.execute(composite)

            # Reload transactions and templates
            await self._load_transactions()
            templates = await self._context.planned_repo.get_all()
            self._context.state.planned_templates.set(templates)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to convert to actual: {e}")

    @qasync.asyncSlot(list)
    async def _on_skip_instance_requested(self, planned_transactions: list[Transaction]) -> None:
        """Handle delete instance request from table.

        Args:
            planned_transactions: Planned transaction instances to delete
        """
        # Confirm deletion
        count = len(planned_transactions)
        reply = QMessageBox.question(
            self,
            "Delete This Instance",
            f"Permanently delete {count} occurrence{'s' if count != 1 else ''}?\n\n"
            f"This will remove only the selected occurrence{'s' if count != 1 else ''}. "
            f"Other future instances will remain.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            for planned_trans in planned_transactions:
                # Find the template that generated this instance
                templates = self._context.state.planned_templates.value
                for template in templates:
                    # Check if this transaction matches the template
                    if (template.description == planned_trans.description and
                        template.amount == planned_trans.amount and
                        template.type == planned_trans.type):
                        # Skip this instance (adds to skipped_dates permanently)
                        updated_template = template.skip_instance(planned_trans.date)
                        command = EditPlannedCommand(
                            self._context.planned_repo,
                            template,
                            updated_template,
                        )
                        await self._context.undo_stack.execute(command)
                        break

            # Reload templates
            templates = await self._context.planned_repo.get_all()
            self._context.state.planned_templates.set(templates)

            # Note: Display will auto-refresh via planned_templates.changed signal

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete instance: {e}")

    @qasync.asyncSlot(list)
    async def _on_delete_template_requested(self, planned_transactions: list[Transaction]) -> None:
        """Handle delete template request from table.

        Args:
            planned_transactions: Planned transactions whose templates should be deleted
        """
        # Confirm deletion
        count = len(planned_transactions)
        reply = QMessageBox.question(
            self,
            "Confirm Delete Template",
            f"Are you sure you want to delete {count} planned template{'s' if count != 1 else ''}?\n"
            f"This will remove all future instances of this planned transaction.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                for planned_trans in planned_transactions:
                    # Find the template that generated this instance
                    templates = self._context.state.planned_templates.value
                    for template in templates:
                        # Check if this transaction matches the template
                        if (template.description == planned_trans.description and
                            template.amount == planned_trans.amount and
                            template.type == planned_trans.type):
                            # Delete the template entirely via undo stack
                            command = DeletePlannedCommand(
                                self._context.planned_repo,
                                template,
                            )
                            await self._context.undo_stack.execute(command)
                            break

                # Reload templates
                templates = await self._context.planned_repo.get_all()
                self._context.state.planned_templates.set(templates)

                # Note: No need to call _on_transactions_changed here because
                # the planned_templates.changed signal will trigger it automatically

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete template: {e}")

    def _on_planned_templates_changed(self, templates: list) -> None:
        """Handle planned templates list change.

        Args:
            templates: Updated planned templates list
        """
        # Only refresh if Show Planned is ON
        if self.show_planned_btn.isChecked():
            # Refresh the display to show updated planned instances
            self._on_transactions_changed(self._context.state.transactions.value)

    def _on_sheet_changed(self, sheet: str) -> None:
        """Handle sheet change from state.

        Args:
            sheet: New sheet name
        """
        self.add_form.set_sheet(sheet)

        # If switching to All Sheets mode, update available sheets and show sheet column
        sheets = self._context.state.sheets.value
        real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]
        if sheet == "All Sheets":
            sheet_names = self._get_ordered_sheet_names(sheets)
            self.add_form.set_available_sheets(sheet_names)
            # Show sheet column only if there are 2+ real sheets
            self.transaction_table.set_show_sheet_column(len(real_sheets) >= 2)
        else:
            # Hide sheet column when viewing a specific sheet
            self.transaction_table.set_show_sheet_column(False)

        # Refresh the transaction display with new sheet filter
        self._on_transactions_changed(self._context.state.transactions.value)

    def _on_sheets_list_changed(self, sheets: list) -> None:
        """Handle sheets list change from state.

        Args:
            sheets: Updated sheets list
        """
        # Update add form's available sheets if in All Sheets mode
        current_sheet = self._context.state.current_sheet.value
        real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]
        if current_sheet == "All Sheets":
            sheet_names = self._get_ordered_sheet_names(sheets)
            self.add_form.set_available_sheets(sheet_names)
            # Update sheet column visibility
            self.transaction_table.set_show_sheet_column(len(real_sheets) >= 2)

    def _get_ordered_sheet_names(self, sheets: list) -> list[str]:
        """Get real sheet names in saved dropdown order."""
        real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]
        saved_order = self._context.settings.sheet_order
        order_map = {name: idx for idx, name in enumerate(saved_order)}
        real_sheets.sort(key=lambda s: (order_map.get(s.name, len(order_map)), s.name.lower()))
        return [s.name for s in real_sheets]

    def _on_selection_changed(self) -> None:
        """Handle table selection change."""
        selected = self.transaction_table.get_selected_transactions()
        self.balance_display.set_selection(selected)

    # Attachment helpers

    async def _process_attachment_changes(
        self,
        transaction_id,
        new_files: list,
        remove_ids: list,
        transaction: Optional[Transaction] = None,
    ) -> None:
        """Process pending attachment additions and removals.

        Args:
            transaction_id: ID of the transaction
            new_files: List of file paths to attach
            remove_ids: List of attachment IDs to remove
            transaction: Optional transaction for descriptive file naming
        """
        svc = self._context.attachment_service
        if not svc:
            return

        try:
            for attachment_id in remove_ids:
                await svc.remove_attachment(attachment_id)

            for file_path in new_files:
                await svc.attach_file(transaction_id, file_path, transaction)
        except Exception:
            pass  # Best-effort; transaction was already saved

    # Keyboard shortcut handlers

    @qasync.asyncSlot()
    async def _on_undo(self) -> None:
        """Handle undo shortcut (Cmd+Z)."""
        if self._context.undo_stack.can_undo:
            try:
                await self._context.undo_stack.undo()
                await self._load_transactions()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to undo: {e}")

    @qasync.asyncSlot()
    async def _on_redo(self) -> None:
        """Handle redo shortcut (Cmd+Shift+Z)."""
        if self._context.undo_stack.can_redo:
            try:
                await self._context.undo_stack.redo()
                await self._load_transactions()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to redo: {e}")

    def _on_new_transaction(self) -> None:
        """Handle new transaction shortcut (Cmd+N)."""
        # If the form panel is hidden, show it first
        if not self._form_panel_visible:
            self._toggle_form_panel()

        # Focus the description field in the add form
        self.add_form.description_input.setFocus()

    def _on_submit_shortcut(self) -> None:
        """Handle submit shortcut (Shift+Enter)."""
        # Trigger the add form's submit button
        self.add_form.submit_btn.click()

    def _on_delete_shortcut(self) -> None:
        """Handle delete shortcut (Delete key)."""
        selected = self.transaction_table.get_selected_transactions()
        if not selected:
            return

        planned_only = [t for t in selected if t.status == ApprovalStatus.PLANNED]
        actual_only = [t for t in selected if t.status != ApprovalStatus.PLANNED]

        if planned_only and not actual_only:
            # Check if all selected are one-time planned (ONCE frequency)
            all_one_time = all(t.is_one_time_planned for t in planned_only)

            if all_one_time:
                # For one-time planned, just delete the template directly
                self._on_delete_template_requested(planned_only)
            else:
                # For recurring (or mixed), ask the user what to do
                msg = QMessageBox(self)
                msg.setWindowTitle("Delete Planned Transaction")
                msg.setText(
                    f"{len(planned_only)} planned transaction{'s' if len(planned_only) != 1 else ''} selected."
                )
                msg.setInformativeText(
                    "Choose whether to delete just the selected instance(s) or the entire template."
                )
                delete_instance_btn = msg.addButton("Delete Instance", QMessageBox.AcceptRole)
                delete_template_btn = msg.addButton("Delete Template", QMessageBox.DestructiveRole)
                msg.addButton(QMessageBox.Cancel)
                msg.exec()

                clicked = msg.clickedButton()
                if clicked == delete_instance_btn:
                    self._on_skip_instance_requested(planned_only)
                elif clicked == delete_template_btn:
                    self._on_delete_template_requested(planned_only)
            return

        if actual_only:
            # Call the async slot directly (it's already wrapped by asyncSlot)
            self._on_delete_requested(actual_only)

    def _on_edit_shortcut(self) -> None:
        """Handle edit shortcut (E key)."""
        selected = self.transaction_table.get_selected_transactions()
        if not selected:
            return

        # Check if any planned transactions are selected
        planned = [t for t in selected if t.status == ApprovalStatus.PLANNED]
        actual = [t for t in selected if t.status != ApprovalStatus.PLANNED]

        # If only planned transactions selected, edit the template
        if planned and not actual:
            if len(planned) == 1:
                self._edit_planned_template(planned[0])
            else:
                QMessageBox.information(
                    self,
                    "Edit Planned",
                    "Please select only one planned transaction to edit its template."
                )
            return

        # Edit actual transactions
        if len(actual) == 1:
            self._on_edit_requested(actual[0])
        elif len(actual) > 1:
            self._on_bulk_edit_requested(actual)

    def _on_view_shortcut(self) -> None:
        """Handle view shortcut (I key)."""
        selected = self.transaction_table.get_selected_transactions()
        if not selected:
            return

        if len(selected) != 1:
            QMessageBox.information(
                self,
                "View Transaction",
                "Please select a single transaction to view its details."
            )
            return

        dialog = ViewTransactionDialog(selected[0], self, context=self._context)
        dialog.exec()

    def _edit_planned_template(self, planned_instance: Transaction) -> None:
        """Find and edit the template for a planned transaction instance.

        Args:
            planned_instance: The planned transaction instance to find template for
        """
        # Find the template that matches this instance by description
        templates = self._context.state.planned_templates.value
        matching_template = None

        for template in templates:
            if template.description == planned_instance.description:
                matching_template = template
                break

        if not matching_template:
            QMessageBox.warning(
                self,
                "Template Not Found",
                "Could not find the template for this planned transaction.\n"
                "Please edit it in the Planned Transactions view."
            )
            return

        # Get available sheets for the dialog
        sheets = self._context.state.sheets.value
        available_sheets = self._get_ordered_sheet_names(sheets)

        # Show edit dialog
        dialog = EditPlannedDialog(
            matching_template,
            self,
            available_sheets=available_sheets,
            context=self._context,
        )
        if dialog.exec() == QMessageBox.Accepted:
            edited = dialog.get_edited_template()
            if edited:
                self._save_edited_template(edited)

    @qasync.asyncSlot()
    async def _save_edited_template(self, template) -> None:
        """Save an edited planned template.

        Args:
            template: The edited template to save
        """
        try:
            await self._context.planned_repo.save(template)

            # Reload templates
            templates = await self._context.planned_repo.get_all()
            self._context.state.planned_templates.set(templates)

            # Refresh the display (planned instances + table)
            self._on_transactions_changed(self._context.state.transactions.value)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save template: {e}")

    def _on_approve_shortcut(self) -> None:
        """Handle approve shortcut (A key)."""
        selected = self.transaction_table.get_selected_transactions()
        # Filter to only expenses that are not planned (income and planned can't be approved)
        expenses_only = [
            t for t in selected
            if t.type == TransactionType.EXPENSE and t.status != ApprovalStatus.PLANNED
        ]
        if expenses_only:
            # Call the async slot directly (it's already wrapped by asyncSlot)
            self._on_approve_requested(expenses_only)

    def _on_reject_shortcut(self) -> None:
        """Handle reject shortcut (R key)."""
        selected = self.transaction_table.get_selected_transactions()
        # Filter to only expenses that are not planned (income and planned can't be rejected)
        expenses_only = [
            t for t in selected
            if t.type == TransactionType.EXPENSE and t.status != ApprovalStatus.PLANNED
        ]
        if expenses_only:
            # Call the async slot directly (it's already wrapped by asyncSlot)
            self._on_reject_requested(expenses_only)

    def _on_export_dialog(self) -> None:
        """Handle export dialog shortcut (Ctrl+Shift+E)."""
        dialog = ExportDialog(self._context, self)
        dialog.exec()

    def _on_copy_to_clipboard(self) -> None:
        """Handle copy to clipboard shortcut (C key)."""
        selected = self.transaction_table.get_selected_transactions()
        if not selected:
            return

        # Export to TSV for easy paste into Excel
        tsv_content = self._context.export_service.export_to_tsv(
            selected,
            include_balance=False
        )

        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(tsv_content)

        # Show feedback (brief message)
        # Could use a status bar message instead, but for now just a quick message box
        QMessageBox.information(
            self,
            "Copied",
            f"Copied {len(selected)} transaction(s) to clipboard as TSV.\n"
            "You can now paste into Excel or any spreadsheet."
        )

    def refresh_theme(self) -> None:
        """Refresh table display after theme change."""
        # Force the table to repaint, which will re-query colors from the model
        self.transaction_table.viewport().update()
