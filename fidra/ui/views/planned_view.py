"""Planned transactions view - manage planned transaction templates."""

from datetime import date
from typing import TYPE_CHECKING

import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeView,
    QHeaderView,
    QMessageBox,
    QDialog,
)
from PySide6.QtGui import QShortcut, QKeySequence

from fidra.ui.models.planned_tree_model import PlannedTreeModel
from fidra.ui.dialogs.add_planned_dialog import AddPlannedDialog
from fidra.ui.dialogs.edit_planned_dialog import EditPlannedDialog

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class PlannedView(QWidget):
    """View for managing planned transaction templates.

    Shows templates in a tree view with expandable instances.
    Provides actions for templates (Add, Edit, Delete, Duplicate)
    and instances (Convert to Actual, Skip).
    """

    def __init__(self, context: "ApplicationContext", parent=None):
        """Initialize the planned view.

        Args:
            context: Application context
            parent: Parent widget
        """
        super().__init__(parent)
        self._context = context
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header with Add button
        header = QHBoxLayout()
        title = QLabel("Planned Transactions")
        title.setObjectName("page_header")
        header.addWidget(title)
        header.addStretch()

        self.add_btn = QPushButton("+ Add Planned")
        self.add_btn.setObjectName("primary_button")
        self.add_btn.clicked.connect(self._on_add_clicked)
        header.addWidget(self.add_btn)

        layout.addLayout(header)

        # Tree view for templates with expandable instances
        self.tree = QTreeView()
        self.tree.setAlternatingRowColors(False)
        self.tree.setAnimated(True)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setRootIsDecorated(True)

        # Configure header
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Model
        self.model = PlannedTreeModel(self._context)
        self.tree.setModel(self.model)

        # Set column widths
        self.tree.setColumnWidth(0, 300)  # Description
        self.tree.setColumnWidth(1, 100)  # Amount
        self.tree.setColumnWidth(2, 100)  # Sheet
        self.tree.setColumnWidth(3, 120)  # Frequency/Type
        self.tree.setColumnWidth(4, 120)  # Next Due/Status

        # Hide sheet column by default (only shown when 2+ sheets)
        self.tree.setColumnHidden(self.model.COL_SHEET, True)

        layout.addWidget(self.tree, 1)

        # Action bar
        action_bar = QHBoxLayout()

        # Template actions (left side)
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.duplicate_btn = QPushButton("Duplicate")

        action_bar.addWidget(self.edit_btn)
        action_bar.addWidget(self.delete_btn)
        action_bar.addWidget(self.duplicate_btn)
        action_bar.addSpacing(20)

        # Instance actions (right side)
        self.convert_btn = QPushButton("Convert to Actual")
        self.delete_instance_btn = QPushButton("Delete This Instance")

        action_bar.addWidget(self.convert_btn)
        action_bar.addWidget(self.delete_instance_btn)
        action_bar.addStretch()

        layout.addLayout(action_bar)

        # Initially disable all action buttons
        self._update_action_buttons(None)

        # Keyboard shortcuts
        self._setup_shortcuts()

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts."""
        # E to edit selected template
        edit_shortcut = QShortcut(QKeySequence("E"), self)
        edit_shortcut.activated.connect(self._on_edit_shortcut)

        # Cmd+N (Ctrl+N on Windows) to add new planned transaction
        new_shortcut = QShortcut(QKeySequence.StandardKey.New, self)
        new_shortcut.activated.connect(self._on_add_clicked)

    def _on_edit_shortcut(self) -> None:
        """Handle E key press for editing."""
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes:
            return

        item_data = self.model.item_at(indexes[0])
        if item_data and item_data.get("is_template"):
            self._on_edit_clicked()

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        # Selection changes
        self.tree.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # Double-click to edit
        self.tree.doubleClicked.connect(self._on_double_clicked)

        # Template actions
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.duplicate_btn.clicked.connect(self._on_duplicate_clicked)

        # Instance actions
        self.convert_btn.clicked.connect(self._on_convert_clicked)
        self.delete_instance_btn.clicked.connect(self._on_delete_instance_clicked)

        # State changes for sheet column visibility
        self._context.state.sheets.changed.connect(self._on_sheets_list_changed)
        self._context.state.current_sheet.changed.connect(self._on_sheet_changed)

        # Initialize sheet column visibility
        self._update_sheet_column_visibility()

    def _on_selection_changed(self, selected, deselected) -> None:
        """Handle selection changes.

        Args:
            selected: Selected items
            deselected: Deselected items
        """
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes:
            self._update_action_buttons(None)
            return

        # Get first selected item
        item_data = self.model.item_at(indexes[0])
        self._update_action_buttons(item_data)

    def _on_double_clicked(self, index) -> None:
        """Handle double-click on tree item.

        Double-click on a template opens edit dialog.
        Double-click on an instance converts it to actual.

        Args:
            index: Model index of clicked item
        """
        item_data = self.model.item_at(index)
        if not item_data:
            return

        if item_data.get("is_template"):
            # Edit template
            self._on_edit_clicked()
        elif item_data.get("is_instance"):
            # Convert instance to actual
            self._on_convert_clicked()

    def _update_action_buttons(self, item_data: dict | None) -> None:
        """Update action button states based on selection.

        Args:
            item_data: Selected item data or None
        """
        if not item_data:
            # No selection - disable all
            self.edit_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.duplicate_btn.setEnabled(False)
            self.convert_btn.setEnabled(False)
            self.delete_instance_btn.setEnabled(False)
            return

        is_template = item_data.get("is_template", False)
        is_instance = item_data.get("is_instance", False)

        # Template actions
        self.edit_btn.setEnabled(is_template)
        self.delete_btn.setEnabled(is_template)
        self.duplicate_btn.setEnabled(is_template)

        # Instance actions
        self.convert_btn.setEnabled(is_instance)
        self.delete_instance_btn.setEnabled(is_instance)

    @qasync.asyncSlot()
    async def _on_add_clicked(self) -> None:
        """Handle add button click."""
        current_sheet = self._context.state.current_sheet.value

        # Get available sheets for the dialog (for All Sheets mode)
        sheets = self._context.state.sheets.value
        available_sheets = self._get_ordered_sheet_names(sheets)

        dialog = AddPlannedDialog(
            current_sheet,
            self,
            available_sheets=available_sheets,
            context=self._context,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            template = dialog.get_template()
            if template:
                try:
                    # Save template
                    await self._context.planned_repo.save(template)

                    # Reload templates
                    await self._reload_templates()

                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to add template: {e}")

    @qasync.asyncSlot()
    async def _on_edit_clicked(self) -> None:
        """Handle edit button click."""
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes:
            return

        item_data = self.model.item_at(indexes[0])
        if not item_data or not item_data.get("is_template"):
            return

        template = item_data["template"]

        # Get available sheets for the dialog
        sheets = self._context.state.sheets.value
        available_sheets = self._get_ordered_sheet_names(sheets)

        # Show edit dialog
        dialog = EditPlannedDialog(
            template,
            self,
            available_sheets=available_sheets,
            context=self._context,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            edited = dialog.get_edited_template()
            if edited:
                try:
                    # Save updated template
                    await self._context.planned_repo.save(edited)

                    # Reload templates
                    await self._reload_templates()

                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to edit template: {e}")

    @qasync.asyncSlot()
    async def _on_delete_clicked(self) -> None:
        """Handle delete button click."""
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes:
            return

        item_data = self.model.item_at(indexes[0])
        if not item_data or not item_data.get("is_template"):
            return

        template = item_data["template"]

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete the planned transaction '{template.description}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Delete template
                await self._context.planned_repo.delete(template.id)

                # Reload templates
                await self._reload_templates()

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete template: {e}")

    def _on_duplicate_clicked(self) -> None:
        """Handle duplicate button click."""
        # TODO: Implement duplicate (create new template from existing)
        QMessageBox.information(self, "Duplicate", "Duplicate functionality coming soon!")

    @qasync.asyncSlot()
    async def _on_convert_clicked(self) -> None:
        """Handle convert to actual button click."""
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes:
            return

        item_data = self.model.item_at(indexes[0])
        if not item_data or not item_data.get("is_instance"):
            return

        template = item_data["template"]
        instance = item_data["instance"]

        # Confirm conversion
        reply = QMessageBox.question(
            self,
            "Convert to Actual",
            f"Convert planned transaction '{instance.description}' on {instance.date.strftime('%Y-%m-%d')} to actual?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Create actual transaction from instance
                # Remove the PLANNED status and use AUTO for income, PENDING for expense
                from fidra.domain.models import TransactionType, ApprovalStatus, Frequency

                if instance.type == TransactionType.INCOME:
                    status = ApprovalStatus.AUTO
                else:
                    status = ApprovalStatus.PENDING

                # Build updates - optionally set date to today on conversion
                updates = {"status": status}
                if self._context.settings.transactions.date_on_planned_conversion:
                    updates["date"] = date.today()

                actual_transaction = instance.with_updates(**updates)

                # Save actual transaction
                from fidra.services.undo import AddTransactionCommand
                command = AddTransactionCommand(
                    self._context.transaction_repo, actual_transaction,
                    audit_service=self._context.audit_service,
                )
                await self._context.undo_stack.execute(command)

                # Check if this is a one-time template
                if template.frequency == Frequency.ONCE:
                    # Delete the template entirely (it's fulfilled and won't generate more instances)
                    await self._context.planned_repo.delete(template.id)
                else:
                    # Mark template as fulfilled for this date (recurring template)
                    updated_template = template.mark_fulfilled(instance.date)
                    await self._context.planned_repo.save(updated_template)

                # Reload templates and transactions
                await self._reload_templates()
                transactions = await self._context.transaction_repo.get_all()
                self._context.state.transactions.set(transactions)

                QMessageBox.information(self, "Success", "Planned transaction converted to actual!")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to convert to actual: {e}")

    @qasync.asyncSlot()
    async def _on_delete_instance_clicked(self) -> None:
        """Handle delete instance button click."""
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes:
            return

        item_data = self.model.item_at(indexes[0])
        if not item_data or not item_data.get("is_instance"):
            return

        template = item_data["template"]
        instance = item_data["instance"]

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete This Instance",
            f"Permanently delete this occurrence on {instance.date.strftime('%Y-%m-%d')}?\n\n"
            f"This will remove only this single occurrence. Other future instances will remain.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Skip this instance date (adds to skipped_dates permanently)
                updated_template = template.skip_instance(instance.date)
                await self._context.planned_repo.save(updated_template)

                # Reload templates
                await self._reload_templates()

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete instance: {e}")

    @qasync.asyncSlot()
    async def _reload_templates(self) -> None:
        """Reload templates from repository."""
        try:
            templates = await self._context.planned_repo.get_all()
            self._context.state.planned_templates.set(templates)
        except Exception as e:
            print(f"Error reloading templates: {e}")

    def _on_sheets_list_changed(self, sheets: list) -> None:
        """Handle sheets list change from state.

        Args:
            sheets: Updated sheets list
        """
        self._update_sheet_column_visibility()

    def _on_sheet_changed(self, sheet: str) -> None:
        """Handle sheet change from state.

        Args:
            sheet: New sheet name
        """
        self._update_sheet_column_visibility()

    def _update_sheet_column_visibility(self) -> None:
        """Update sheet column visibility based on sheets count and current sheet."""
        sheets = self._context.state.sheets.value
        current_sheet = self._context.state.current_sheet.value

        # Show sheet column only when in "All Sheets" mode AND there are 2+ sheets
        show_sheet_column = current_sheet == "All Sheets" and len(sheets) >= 2
        self.tree.setColumnHidden(self.model.COL_SHEET, not show_sheet_column)

    def _get_ordered_sheet_names(self, sheets: list) -> list[str]:
        """Get real sheet names in saved dropdown order."""
        real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]
        saved_order = self._context.settings.sheet_order
        order_map = {name: idx for idx, name in enumerate(saved_order)}
        real_sheets.sort(key=lambda s: (order_map.get(s.name, len(order_map)), s.name.lower()))
        return [s.name for s in real_sheets]
