"""Edit transaction dialog."""

import asyncio
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import qasync
from PySide6.QtCore import QDate, Qt, QStringListModel, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QDateEdit,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QDialogButtonBox,
    QButtonGroup,
    QCompleter,
    QVBoxLayout,
)

from fidra.domain.models import Attachment, Transaction, TransactionType, ApprovalStatus
from fidra.ui.components.completer_utils import install_tab_accept

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class EditTransactionDialog(QDialog):
    """Dialog for editing an existing transaction.

    Similar to AddTransactionForm but as a modal dialog
    with pre-populated fields.
    """

    def __init__(
        self,
        transaction: Transaction,
        parent=None,
        available_sheets: Optional[list[str]] = None,
        context: Optional["ApplicationContext"] = None
    ):
        """Initialize the edit dialog.

        Args:
            transaction: Transaction to edit
            parent: Parent widget
            available_sheets: List of available sheet names (for sheet selector)
            context: Application context for autocomplete data
        """
        super().__init__(parent)
        self._original_transaction = transaction
        self._edited_transaction: Optional[Transaction] = None
        self._available_sheets = available_sheets or []
        self._context = context
        self._attachments_task: Optional[asyncio.Task] = None

        self.setWindowTitle("Edit Transaction")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._setup_ui()
        self._setup_completers()
        self._populate_fields()

    def _setup_ui(self) -> None:
        """Set up the dialog UI - compact 2-column layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # ===== TYPE TOGGLE =====
        type_layout = QHBoxLayout()
        type_layout.setSpacing(0)

        self.expense_btn = QPushButton("Expense")
        self.expense_btn.setObjectName("type_expense")
        self.income_btn = QPushButton("Income")
        self.income_btn.setObjectName("type_income")

        self.expense_btn.setCheckable(True)
        self.income_btn.setCheckable(True)

        self.type_group = QButtonGroup(self)
        self.type_group.addButton(self.expense_btn, 0)
        self.type_group.addButton(self.income_btn, 1)

        type_layout.addWidget(self.expense_btn)
        type_layout.addWidget(self.income_btn)
        layout.addLayout(type_layout)

        # ===== AMOUNT & DATE ROW =====
        amount_date_layout = QHBoxLayout()
        amount_date_layout.setSpacing(8)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setPrefix("£ ")
        self.amount_input.setRange(0.01, 999999.99)
        self.amount_input.setDecimals(2)
        self.amount_input.setMinimumHeight(32)
        amount_date_layout.addWidget(self.amount_input, 1)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd MMM yyyy")
        self.date_edit.setMinimumHeight(32)
        amount_date_layout.addWidget(self.date_edit, 1)

        layout.addLayout(amount_date_layout)

        # ===== DESCRIPTION =====
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Description *")
        self.description_input.setMinimumHeight(32)
        layout.addWidget(self.description_input)

        # ===== CATEGORY & PARTY ROW =====
        cat_party_layout = QHBoxLayout()
        cat_party_layout.setSpacing(8)

        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.setPlaceholderText("Category")
        self.category_input.setMinimumHeight(32)
        self._update_category_list()
        cat_party_layout.addWidget(self.category_input, 1)

        self.party_input = QLineEdit()
        self.party_input.setPlaceholderText("Party")
        self.party_input.setMinimumHeight(32)
        cat_party_layout.addWidget(self.party_input, 1)

        layout.addLayout(cat_party_layout)

        # ===== SHEET & STATUS ROW =====
        sheet_status_layout = QHBoxLayout()
        sheet_status_layout.setSpacing(8)

        # Sheet selector
        self.sheet_combo = QComboBox()
        self.sheet_combo.setMinimumHeight(32)
        if self._available_sheets:
            self.sheet_combo.addItems(self._available_sheets)
        sheet_status_layout.addWidget(self.sheet_combo, 1)

        # Status selector
        self.status_combo = QComboBox()
        self.status_combo.setMinimumHeight(32)
        self.status_combo.addItems(["Auto", "Pending", "Approved", "Rejected"])
        sheet_status_layout.addWidget(self.status_combo, 1)

        layout.addLayout(sheet_status_layout)

        # Hide sheet selector if only one or no sheets (but keep status visible)
        if len(self._available_sheets) <= 1:
            self.sheet_combo.setVisible(False)

        # ===== REFERENCE (For bank statement matching) =====
        self.reference_input = QLineEdit()
        self.reference_input.setPlaceholderText("Reference (for bank matching)")
        self.reference_input.setMinimumHeight(32)
        layout.addWidget(self.reference_input)

        # ===== NOTES (Single line) =====
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Notes (optional)")
        self.notes_input.setMinimumHeight(32)
        layout.addWidget(self.notes_input)

        # ===== ATTACHMENTS =====
        if self._context and self._context.attachment_service:
            attach_header_layout = QHBoxLayout()
            attach_label = QLabel("Attachments")
            attach_label.setObjectName("secondary_text")
            attach_header_layout.addWidget(attach_label)

            attach_header_layout.addStretch()

            self.attach_btn = QPushButton("Attach File...")
            self.attach_btn.clicked.connect(self._on_attach_file)
            attach_header_layout.addWidget(self.attach_btn)
            layout.addLayout(attach_header_layout)

            self.attachment_list = QListWidget()
            self.attachment_list.setMaximumHeight(80)
            self.attachment_list.setContextMenuPolicy(
                Qt.ContextMenuPolicy.CustomContextMenu
            )
            self.attachment_list.customContextMenuRequested.connect(
                self._on_attachment_context_menu
            )
            self.attachment_list.itemDoubleClicked.connect(self._on_attachment_open)
            layout.addWidget(self.attachment_list)

            # Load existing attachments (deferred to avoid qasync re-entrancy)
            self._pending_new_files: list[Path] = []
            self._pending_remove_ids: list = []
            QTimer.singleShot(0, self._start_load_attachments)

        # ===== BUTTONS =====
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Connect type button to category update and status update
        self.type_group.buttonClicked.connect(self._update_category_list)
        self.type_group.buttonClicked.connect(self._update_status_options)

    def _update_category_list(self) -> None:
        """Update category dropdown based on selected type."""
        is_expense = self.expense_btn.isChecked()

        # Get categories from settings if context is available, otherwise use defaults
        if self._context:
            if is_expense:
                categories = self._context.settings.expense_categories.copy()
            else:
                categories = self._context.settings.income_categories.copy()
        else:
            # Fallback defaults
            if is_expense:
                categories = [
                    "Equipment",
                    "Training",
                    "Events",
                    "Administration",
                    "Travel",
                    "Other",
                ]
            else:
                categories = [
                    "Membership Dues",
                    "Event Income",
                    "Donations",
                    "Grants",
                    "Other Income",
                ]

        current_text = self.category_input.currentText()
        self.category_input.clear()
        self.category_input.addItems(categories)

        # Restore previous value if it was set
        if current_text:
            index = self.category_input.findText(current_text)
            if index >= 0:
                self.category_input.setCurrentIndex(index)
            else:
                self.category_input.setCurrentText(current_text)

    def _update_status_options(self) -> None:
        """Update status options based on transaction type.

        Income transactions can only be AUTO (no manual status changes).
        Expense transactions can be Pending, Approved, or Rejected.
        PLANNED status is not available for manual editing - it's only for
        instances generated from planned transaction templates.
        """
        is_income = self.income_btn.isChecked()

        if is_income:
            # Income: AUTO only (no other manual options)
            self.status_combo.setEnabled(False)  # Disable for income
            self.status_combo.clear()
            self.status_combo.addItems(["Auto"])
            self.status_combo.setCurrentIndex(0)
        else:
            # Expense: Pending, Approved, or Rejected
            self.status_combo.setEnabled(True)
            current_index = self.status_combo.currentIndex()
            self.status_combo.clear()
            self.status_combo.addItems([
                "Pending",
                "Approved",
                "Rejected",
            ])
            # Default to Pending
            self.status_combo.setCurrentIndex(0)

    def _populate_fields(self) -> None:
        """Populate form fields with transaction data."""
        trans = self._original_transaction

        # Type
        if trans.type == TransactionType.EXPENSE:
            self.expense_btn.setChecked(True)
        else:
            self.income_btn.setChecked(True)

        self._update_category_list()
        self._update_status_options()

        # Date
        q_date = QDate(trans.date.year, trans.date.month, trans.date.day)
        self.date_edit.setDate(q_date)

        # Description
        self.description_input.setText(trans.description)

        # Amount
        self.amount_input.setValue(float(trans.amount))

        # Category
        if trans.category:
            index = self.category_input.findText(trans.category)
            if index >= 0:
                self.category_input.setCurrentIndex(index)
            else:
                self.category_input.setCurrentText(trans.category)

        # Party
        if trans.party:
            self.party_input.setText(trans.party)

        # Sheet
        if trans.sheet and self._available_sheets:
            index = self.sheet_combo.findText(trans.sheet)
            if index >= 0:
                self.sheet_combo.setCurrentIndex(index)
            else:
                # Sheet not in list, add it
                self.sheet_combo.addItem(trans.sheet)
                self.sheet_combo.setCurrentText(trans.sheet)

        # Status (set after _update_status_options which adjusts available options)
        if trans.type == TransactionType.INCOME:
            # Income: AUTO only (always index 0)
            self.status_combo.setCurrentIndex(0)
        else:
            # Expense: Pending (0), Approved (1), Rejected (2)
            expense_status_map = {
                ApprovalStatus.PENDING: 0,
                ApprovalStatus.APPROVED: 1,
                ApprovalStatus.REJECTED: 2,
            }
            # If transaction somehow has PLANNED status, default to PENDING
            self.status_combo.setCurrentIndex(expense_status_map.get(trans.status, 0))

        # Reference
        if trans.reference:
            self.reference_input.setText(trans.reference)
        else:
            self.reference_input.clear()

        # Notes
        if trans.notes:
            self.notes_input.setText(trans.notes)
        else:
            self.notes_input.clear()

    def _on_save(self) -> None:
        """Handle save button click."""
        if not self._validate():
            return

        # Get values
        trans_date = self.date_edit.date().toPython()
        description = self.description_input.text().strip()
        amount = Decimal(str(self.amount_input.value()))
        trans_type = TransactionType.EXPENSE if self.expense_btn.isChecked() else TransactionType.INCOME
        category = self.category_input.currentText().strip() or None
        party = self.party_input.text().strip() or None
        reference = self.reference_input.text().strip() or None
        notes = self.notes_input.text().strip() or None

        # Sheet (use selected if available, otherwise keep original)
        if self._available_sheets and len(self._available_sheets) > 1:
            sheet = self.sheet_combo.currentText()
        else:
            sheet = self._original_transaction.sheet

        # Map status based on type
        if trans_type == TransactionType.INCOME:
            # Income: Always AUTO
            status = ApprovalStatus.AUTO
        else:
            # Expense: Pending (0), Approved (1), Rejected (2)
            expense_status_map = [
                ApprovalStatus.PENDING,
                ApprovalStatus.APPROVED,
                ApprovalStatus.REJECTED,
            ]
            status = expense_status_map[self.status_combo.currentIndex()]

        # Create updated transaction
        self._edited_transaction = self._original_transaction.with_updates(
            date=trans_date,
            description=description,
            amount=amount,
            type=trans_type,
            sheet=sheet,
            category=category,
            party=party,
            reference=reference,
            notes=notes,
            status=status,
        )

        self.accept()

    def _validate(self) -> bool:
        """Validate form inputs.

        Returns:
            True if valid, False otherwise
        """
        # Description is required
        if not self.description_input.text().strip():
            self.description_input.setFocus()
            return False

        # Amount must be positive
        if self.amount_input.value() <= 0:
            self.amount_input.setFocus()
            return False

        return True

    def _setup_completers(self) -> None:
        """Set up autocomplete for description and party fields."""
        if not self._context:
            return
        self._completer_filters = []

        # Get existing descriptions and parties from transactions
        transactions = self._context.state.transactions.value
        descriptions = set()
        parties = set()

        for t in transactions:
            if t.description:
                descriptions.add(t.description)
            if t.party:
                parties.add(t.party)

        # Description completer
        desc_completer = QCompleter(sorted(descriptions, key=str.lower), self)
        desc_completer.setCaseSensitivity(Qt.CaseInsensitive)
        desc_completer.setFilterMode(Qt.MatchContains)
        self.description_input.setCompleter(desc_completer)
        self._completer_filters.append(
            install_tab_accept(self.description_input, desc_completer)
        )

        # Party completer
        party_completer = QCompleter(sorted(parties, key=str.lower), self)
        party_completer.setCaseSensitivity(Qt.CaseInsensitive)
        party_completer.setFilterMode(Qt.MatchContains)
        self.party_input.setCompleter(party_completer)
        self._completer_filters.append(
            install_tab_accept(self.party_input, party_completer)
        )

    def get_edited_transaction(self) -> Optional[Transaction]:
        """Get the edited transaction.

        Returns:
            Edited transaction if dialog was accepted, None otherwise
        """
        return self._edited_transaction

    def get_pending_attachments(self) -> list[Path]:
        """Get list of new files to attach after save."""
        return getattr(self, "_pending_new_files", [])

    def get_pending_removals(self) -> list:
        """Get list of attachment IDs to remove after save."""
        return getattr(self, "_pending_remove_ids", [])

    def _start_load_attachments(self) -> None:
        """Start async load of attachments safely after dialog is shown."""
        if not self._context or not self._context.attachment_service:
            return

        if self._attachments_task and not self._attachments_task.done():
            self._attachments_task.cancel()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = qasync.get_event_loop()
        self._attachments_task = loop.create_task(self._load_attachments())

    async def _load_attachments(self) -> None:
        """Load existing attachments for this transaction."""
        if not self._context or not self._context.attachment_service:
            return

        try:
            attachments = await self._context.attachment_service.get_attachments(
                self._original_transaction.id
            )
            self.attachment_list.clear()
            for att in attachments:
                size_str = self._context.attachment_service.format_file_size(att.file_size)
                item = QListWidgetItem(f"{att.stored_name}  ({size_str})")
                item.setData(Qt.ItemDataRole.UserRole, att)
                self.attachment_list.addItem(item)
        except Exception:
            pass  # Silently handle - attachments are optional

    def closeEvent(self, event) -> None:
        """Ensure any attachment task is cancelled on close."""
        if self._attachments_task and not self._attachments_task.done():
            self._attachments_task.cancel()
        super().closeEvent(event)

    def _on_attach_file(self) -> None:
        """Open file dialog to select files to attach."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Attach Files",
            str(Path.home()),
            "All Files (*);;Images (*.png *.jpg *.jpeg *.gif *.bmp)"
            ";;Documents (*.pdf *.doc *.docx *.txt)"
        )
        for file_path in files:
            path = Path(file_path)
            if path.exists():
                self._pending_new_files.append(path)
                size = path.stat().st_size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                item = QListWidgetItem(f"{path.name}  ({size_str})  [NEW]")
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.attachment_list.addItem(item)

    def _on_attachment_context_menu(self, position) -> None:
        """Show context menu for attachment list."""
        item = self.attachment_list.itemAt(position)
        if not item:
            return

        data = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)

        if isinstance(data, Attachment):
            open_action = menu.addAction("Open")
            open_action.triggered.connect(lambda: self._open_attachment(data))

            remove_action = menu.addAction("Remove")
            remove_action.triggered.connect(
                lambda: self._remove_attachment(item, data)
            )
        elif isinstance(data, Path):
            # Pending new file
            remove_action = menu.addAction("Remove")
            remove_action.triggered.connect(
                lambda: self._remove_pending_file(item, data)
            )

        menu.exec(self.attachment_list.mapToGlobal(position))

    def _on_attachment_open(self, item: QListWidgetItem) -> None:
        """Handle double-click to open attachment."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, Attachment):
            self._open_attachment(data)
        elif isinstance(data, Path):
            self._open_file(data)

    def _open_attachment(self, attachment: Attachment) -> None:
        """Open an existing attachment with the system default application."""
        if not self._context or not self._context.attachment_service:
            return
        file_path = self._context.attachment_service.get_file_path(attachment)
        self._open_file(file_path)

    def _open_file(self, path: Path) -> None:
        """Open a file with the system default application."""
        if not path.exists():
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform == "win32":
            subprocess.Popen(["start", "", str(path)], shell=True)
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _remove_attachment(self, item: QListWidgetItem, attachment: Attachment) -> None:
        """Mark an existing attachment for removal."""
        self._pending_remove_ids.append(attachment.id)
        row = self.attachment_list.row(item)
        self.attachment_list.takeItem(row)

    def _remove_pending_file(self, item: QListWidgetItem, path: Path) -> None:
        """Remove a pending (not yet saved) file from the list."""
        if path in self._pending_new_files:
            self._pending_new_files.remove(path)
        row = self.attachment_list.row(item)
        self.attachment_list.takeItem(row)
