"""Manage sheets dialog for adding, editing, and deleting sheets."""

from typing import TYPE_CHECKING, Optional
import qasync

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLineEdit,
    QInputDialog,
    QMessageBox,
)

from fidra.domain.models import Sheet

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class ManageSheetsDialog(QDialog):
    """Dialog for managing sheets (add, edit, delete).

    Features:
    - List all sheets
    - Add new sheet
    - Edit sheet name
    - Delete sheet (with confirmation)
    - Set current/active sheet
    """

    def __init__(self, context: "ApplicationContext", parent=None):
        """Initialize manage sheets dialog.

        Args:
            context: Application context
            parent: Parent widget
        """
        super().__init__(parent)
        self._context = context
        self._setup_ui()
        self._load_sheets()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        self.setWindowTitle("Manage Sheets")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Manage Sheets")
        header.setObjectName("section_header")
        layout.addWidget(header)

        # Info label
        info = QLabel(
            "Sheets are separate accounts or ledgers. "
            "Each transaction belongs to one sheet."
        )
        info.setWordWrap(True)
        info.setObjectName("secondary_text")
        layout.addWidget(info)

        # Sheet list with drag and drop reordering
        self.sheet_list = QListWidget()
        self.sheet_list.setDragDropMode(QListWidget.InternalMove)
        self.sheet_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.sheet_list.itemDoubleClicked.connect(self._on_edit_clicked)
        self.sheet_list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.sheet_list)

        # Reorder instructions
        reorder_info = QLabel("Drag items to reorder how sheets appear in the dropdown.")
        reorder_info.setObjectName("secondary_text")
        layout.addWidget(reorder_info)

        # Current sheet indicator
        self.current_label = QLabel()
        self.current_label.setObjectName("success_text")
        self._update_current_label()
        layout.addWidget(self.current_label)

        # Button bar
        button_layout = QHBoxLayout()

        self.add_btn = QPushButton("Add Sheet")
        self.add_btn.clicked.connect(self._on_add_clicked)
        button_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit Name")
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        self.edit_btn.setEnabled(False)
        button_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        button_layout.addWidget(self.delete_btn)

        self.set_current_btn = QPushButton("Set as Current")
        self.set_current_btn.clicked.connect(self._on_set_current_clicked)
        self.set_current_btn.setEnabled(False)
        button_layout.addWidget(self.set_current_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)

        layout.addLayout(close_layout)

    @qasync.asyncSlot()
    async def _load_sheets(self) -> None:
        """Load sheets from repository."""
        try:
            sheets = await self._context.sheet_repo.get_all()
            self._context.state.sheets.set(sheets)
            self._refresh_list()
            self._update_current_label()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load sheets: {e}"
            )

    def _refresh_list(self) -> None:
        """Refresh the sheet list display."""
        self.sheet_list.clear()

        sheets = self._context.state.sheets.value
        current_sheet = self._context.state.current_sheet.value

        # Filter out virtual sheets - "All Sheets" is a view concept, not a real sheet
        real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]

        # Sort by saved order (sheets not in order list go to end)
        saved_order = self._context.settings.sheet_order
        def sort_key(sheet):
            try:
                return saved_order.index(sheet.name)
            except ValueError:
                return len(saved_order) + 1  # Put unlisted sheets at end

        real_sheets = sorted(real_sheets, key=sort_key)

        for sheet in real_sheets:
            item = QListWidgetItem(sheet.name)
            item.setData(Qt.ItemDataRole.UserRole, sheet)

            # Highlight current sheet (compare with actual sheet name, not "All Sheets")
            if sheet.name == current_sheet or (current_sheet == "All Sheets" and len(real_sheets) == 1):
                item.setBackground(Qt.GlobalColor.lightGray)
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.sheet_list.addItem(item)

    def _on_rows_moved(self) -> None:
        """Handle rows being moved (drag and drop reorder)."""
        # Get new order from list widget
        new_order = []
        for i in range(self.sheet_list.count()):
            item = self.sheet_list.item(i)
            if item:
                new_order.append(item.text())

        # Save to settings
        self._context.settings.sheet_order = new_order
        self._context.save_settings()

        # Update state to trigger UI refresh
        self._context.state.sheets.emit_changed()

    def _update_current_label(self) -> None:
        """Update the current sheet label display."""
        current_sheet = self._context.state.current_sheet.value
        sheets = self._context.state.sheets.value
        real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]

        # If current is "All Sheets" but there's only 1 real sheet, show that sheet's name
        if current_sheet == "All Sheets" and len(real_sheets) == 1:
            display_name = real_sheets[0].name
        else:
            display_name = current_sheet

        self.current_label.setText(f"Current view: {display_name}")

    def _on_selection_changed(self) -> None:
        """Handle selection change in list."""
        has_selection = bool(self.sheet_list.selectedItems())
        sheets = self._context.state.sheets.value
        real_sheets = [s for s in sheets if not s.is_virtual and not s.is_planned]

        self.edit_btn.setEnabled(has_selection)

        # Delete only enabled if there are 2+ sheets (can't delete the last one)
        self.delete_btn.setEnabled(has_selection and len(real_sheets) > 1)

        # Set as Current only makes sense when there are 2+ sheets
        # With 1 sheet, that sheet IS the only view
        self.set_current_btn.setEnabled(has_selection and len(real_sheets) > 1)

    @qasync.asyncSlot()
    async def _on_add_clicked(self) -> None:
        """Handle add button click."""
        # Prompt for sheet name
        name, ok = QInputDialog.getText(
            self,
            "Add Sheet",
            "Enter sheet name:",
            QLineEdit.EchoMode.Normal,
            ""
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        # Prevent reserved names
        if name.lower() == "all sheets":
            QMessageBox.warning(
                self,
                "Reserved Name",
                "'All Sheets' is a reserved name for viewing all sheets together. "
                "Please choose a different name."
            )
            return

        # Check if sheet already exists
        sheets = self._context.state.sheets.value
        if any(s.name == name for s in sheets):
            QMessageBox.warning(
                self,
                "Duplicate Sheet",
                f"A sheet named '{name}' already exists."
            )
            return

        try:
            # Create new sheet
            new_sheet = Sheet.create(name=name)
            await self._context.sheet_repo.save(new_sheet)

            # Reload sheets
            await self._load_sheets()

            QMessageBox.information(
                self,
                "Success",
                f"Sheet '{name}' created successfully."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create sheet: {e}"
            )

    @qasync.asyncSlot()
    async def _on_edit_clicked(self) -> None:
        """Handle edit button click."""
        selected = self.sheet_list.selectedItems()
        if not selected:
            return

        item = selected[0]
        sheet = item.data(Qt.ItemDataRole.UserRole)

        # Prompt for new name
        name, ok = QInputDialog.getText(
            self,
            "Edit Sheet",
            "Enter new sheet name:",
            QLineEdit.EchoMode.Normal,
            sheet.name
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        # Prevent reserved names
        if name.lower() == "all sheets":
            QMessageBox.warning(
                self,
                "Reserved Name",
                "'All Sheets' is a reserved name for viewing all sheets together. "
                "Please choose a different name."
            )
            return

        # Check if new name already exists (excluding current sheet)
        sheets = self._context.state.sheets.value
        if any(s.name == name and s.id != sheet.id for s in sheets):
            QMessageBox.warning(
                self,
                "Duplicate Sheet",
                f"A sheet named '{name}' already exists."
            )
            return

        try:
            old_name = sheet.name

            # Update sheet name
            updated_sheet = sheet.with_updates(name=name)
            await self._context.sheet_repo.save(updated_sheet)

            # Update all transactions that belong to the old sheet
            all_transactions = await self._context.transaction_repo.get_all(sheet=old_name)
            for trans in all_transactions:
                updated_trans = trans.with_updates(sheet=name)
                await self._context.transaction_repo.save(updated_trans)

            # Update all planned templates that target the old sheet
            all_templates = await self._context.planned_repo.get_all()
            for template in all_templates:
                if template.target_sheet == old_name:
                    updated_template = template.with_updates(target_sheet=name)
                    await self._context.planned_repo.save(updated_template)

            # Update current sheet if this was the current one
            if self._context.state.current_sheet.value == old_name:
                self._context.state.current_sheet.set(name)

            # Reload sheets and transactions
            await self._load_sheets()

            # Refresh transactions in state
            transactions = await self._context.transaction_repo.get_all()
            self._context.state.transactions.set(transactions)

            templates = await self._context.planned_repo.get_all()
            self._context.state.planned_templates.set(templates)

            QMessageBox.information(
                self,
                "Success",
                f"Sheet renamed to '{name}' successfully."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to update sheet: {e}"
            )

    @qasync.asyncSlot()
    async def _on_delete_clicked(self) -> None:
        """Handle delete button click."""
        selected = self.sheet_list.selectedItems()
        if not selected:
            return

        item = selected[0]
        sheet = item.data(Qt.ItemDataRole.UserRole)

        # Count real (non-virtual) sheets
        all_sheets = self._context.state.sheets.value
        real_sheets = [s for s in all_sheets if not s.is_virtual and not s.is_planned]

        # Prevent deleting the last sheet
        if len(real_sheets) <= 1:
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "You cannot delete the last sheet. There must always be at least one sheet."
            )
            return

        # Get remaining sheets (for move target selection)
        remaining_sheets = [s for s in real_sheets if s.id != sheet.id]
        move_target = None

        # Check if there are transactions in this sheet
        # Fetch directly from DB to ensure we see ALL transactions for this sheet,
        # not just those in the current view (state might only have current sheet's transactions)
        all_transactions = await self._context.transaction_repo.get_all(sheet=sheet.name)
        sheet_transactions = list(all_transactions)

        # Also check for planned templates targeting this sheet
        all_templates = await self._context.planned_repo.get_all()
        sheet_templates = [t for t in all_templates if t.target_sheet == sheet.name]

        move_transactions = False
        delete_transactions = False

        if sheet_transactions or sheet_templates:
            # Show dialog with options: Move to default sheet, Delete transactions, or Cancel
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Delete Sheet")
            msg_box.setIcon(QMessageBox.Icon.Warning)

            items_text = []
            if sheet_transactions:
                items_text.append(f"{len(sheet_transactions)} transaction(s)")
            if sheet_templates:
                items_text.append(f"{len(sheet_templates)} planned template(s)")

            msg_box.setText(
                f"Sheet '{sheet.name}' contains {' and '.join(items_text)}.\n\n"
                f"What would you like to do with them?"
            )

            move_btn = msg_box.addButton(
                "Merge",
                QMessageBox.ButtonRole.AcceptRole
            )
            delete_btn = msg_box.addButton(
                "Delete them",
                QMessageBox.ButtonRole.DestructiveRole
            )
            cancel_btn = msg_box.addButton(
                "Cancel",
                QMessageBox.ButtonRole.RejectRole
            )

            msg_box.setDefaultButton(cancel_btn)
            msg_box.exec()

            clicked = msg_box.clickedButton()
            if clicked == cancel_btn:
                return
            elif clicked == move_btn:
                move_transactions = True
            elif clicked == delete_btn:
                delete_transactions = True
        else:
            # No transactions, simple confirmation
            reply = QMessageBox.question(
                self,
                "Delete Sheet",
                f"Are you sure you want to delete sheet '{sheet.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            # Handle transactions based on user choice
            if move_transactions:
                # Ask user for target sheet
                target_names = [s.name for s in remaining_sheets]
                if not target_names:
                    return
                chosen, ok = QInputDialog.getItem(
                    self,
                    "Move Items",
                    "Move items to sheet:",
                    target_names,
                    0,
                    False,
                )
                if not ok or not chosen:
                    return
                move_target = next((s for s in remaining_sheets if s.name == chosen), None)
                if not move_target:
                    return

                # Move transactions to chosen sheet
                for trans in sheet_transactions:
                    updated = trans.with_updates(sheet=move_target.name)
                    await self._context.transaction_repo.save(updated)

                # Move planned templates to chosen sheet
                for template in sheet_templates:
                    updated = template.with_updates(target_sheet=move_target.name)
                    await self._context.planned_repo.save(updated)

            elif delete_transactions:
                # Delete all transactions in this sheet
                for trans in sheet_transactions:
                    await self._context.transaction_repo.delete(trans.id)

                # Delete all planned templates targeting this sheet
                for template in sheet_templates:
                    await self._context.planned_repo.delete(template.id)

            # Delete sheet
            await self._context.sheet_repo.delete(sheet.id)

            # If this was the current sheet, set to first available real sheet
            current = self._context.state.current_sheet.value
            if current == sheet.name:
                if remaining_sheets:
                    self._context.state.current_sheet.set(remaining_sheets[0].name)

            # Reload all data
            await self._load_sheets()

            # Reload transactions and templates to reflect changes
            transactions = await self._context.transaction_repo.get_all()
            self._context.state.transactions.set(transactions)

            templates = await self._context.planned_repo.get_all()
            self._context.state.planned_templates.set(templates)

            # Show success message
            if move_transactions:
                QMessageBox.information(
                    self,
                    "Success",
                    f"Sheet '{sheet.name}' deleted. Items moved to '{move_target.name}'."
                )
            elif delete_transactions:
                QMessageBox.information(
                    self,
                    "Success",
                    f"Sheet '{sheet.name}' and all its items deleted."
                )
            else:
                QMessageBox.information(
                    self,
                    "Success",
                    f"Sheet '{sheet.name}' deleted."
                )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to delete sheet: {e}"
            )

    def _on_set_current_clicked(self) -> None:
        """Handle set as current button click."""
        selected = self.sheet_list.selectedItems()
        if not selected:
            return

        item = selected[0]
        sheet = item.data(Qt.ItemDataRole.UserRole)

        # Set as current sheet (this triggers transaction reload via state change)
        self._context.state.current_sheet.set(sheet.name)

        # Update display
        self._update_current_label()
        self._refresh_list()

        QMessageBox.information(
            self,
            "Success",
            f"Now viewing sheet '{sheet.name}'."
        )
