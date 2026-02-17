"""Bulk edit transaction dialog."""

from decimal import Decimal
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QDateEdit,
    QComboBox,
    QPushButton,
    QDialogButtonBox,
    QButtonGroup,
    QFrame,
    QCompleter,
)

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.ui.components.completer_utils import install_tab_accept


class BulkEditTransactionDialog(QDialog):
    """Dialog for bulk editing multiple transactions.

    Only shows fields that are identical across all selected transactions.
    Those fields can be edited and the new value is applied to all.
    """

    def __init__(
        self,
        transactions: list[Transaction],
        parent=None,
        available_sheets: Optional[list[str]] = None,
        context=None,
    ):
        """Initialize the bulk edit dialog.

        Args:
            transactions: Transactions to edit
            parent: Parent widget
            available_sheets: List of available sheet names
        """
        super().__init__(parent)
        self._transactions = transactions
        self._edited_transactions: list[Transaction] = []
        self._available_sheets = available_sheets or []
        self._context = context

        self.setWindowTitle(f"Bulk Edit ({len(transactions)} transactions)")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._analyze_transactions()
        self._setup_ui()
        self._setup_completers()

    def _analyze_transactions(self) -> None:
        """Analyze transactions to find common values."""
        if not self._transactions:
            return

        first = self._transactions[0]

        # Check which fields have the same value across all transactions
        self._same_type = all(t.type == first.type for t in self._transactions)
        self._same_date = all(t.date == first.date for t in self._transactions)
        self._same_amount = all(t.amount == first.amount for t in self._transactions)
        self._same_description = all(t.description == first.description for t in self._transactions)
        self._same_category = all(t.category == first.category for t in self._transactions)
        self._same_party = all(t.party == first.party for t in self._transactions)
        self._same_sheet = all(t.sheet == first.sheet for t in self._transactions)
        self._same_status = all(t.status == first.status for t in self._transactions)
        self._same_notes = all(t.notes == first.notes for t in self._transactions)

        # Store common values
        self._common_type = first.type if self._same_type else None
        self._common_date = first.date if self._same_date else None
        self._common_amount = first.amount if self._same_amount else None
        self._common_description = first.description if self._same_description else None
        self._common_category = first.category if self._same_category else None
        self._common_party = first.party if self._same_party else None
        self._common_sheet = first.sheet if self._same_sheet else None
        self._common_status = first.status if self._same_status else None
        self._common_notes = first.notes if self._same_notes else None

        # Check if all are expenses (for status editing)
        self._all_expenses = all(t.type == TransactionType.EXPENSE for t in self._transactions)

    def _setup_ui(self) -> None:
        """Set up the dialog UI - only show fields that are identical."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Info label
        info = QLabel(f"Editing {len(self._transactions)} transactions.\nOnly fields with identical values are shown.")
        info.setObjectName("secondary_text")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        self._has_editable_fields = False

        # ===== TYPE TOGGLE (only if same) =====
        if self._same_type:
            self._has_editable_fields = True
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

            if self._common_type == TransactionType.EXPENSE:
                self.expense_btn.setChecked(True)
            else:
                self.income_btn.setChecked(True)

            type_layout.addWidget(self.expense_btn)
            type_layout.addWidget(self.income_btn)
            layout.addLayout(type_layout)

            self.type_group.buttonClicked.connect(self._update_category_list)
        else:
            self.expense_btn = None
            self.income_btn = None
            self.type_group = None

        # ===== AMOUNT & DATE ROW =====
        if self._same_amount or self._same_date:
            amount_date_layout = QHBoxLayout()
            amount_date_layout.setSpacing(8)

            if self._same_amount:
                self._has_editable_fields = True
                self.amount_input = QDoubleSpinBox()
                self.amount_input.setPrefix("£ ")
                self.amount_input.setRange(0.01, 999999.99)
                self.amount_input.setDecimals(2)
                self.amount_input.setValue(float(self._common_amount))
                self.amount_input.setMinimumHeight(32)
                amount_date_layout.addWidget(self.amount_input, 1)
            else:
                self.amount_input = None

            if self._same_date:
                self._has_editable_fields = True
                self.date_edit = QDateEdit()
                self.date_edit.setCalendarPopup(True)
                self.date_edit.setDisplayFormat("dd MMM yyyy")
                self.date_edit.setDate(QDate(
                    self._common_date.year,
                    self._common_date.month,
                    self._common_date.day
                ))
                self.date_edit.setMinimumHeight(32)
                amount_date_layout.addWidget(self.date_edit, 1)
            else:
                self.date_edit = None

            layout.addLayout(amount_date_layout)
        else:
            self.amount_input = None
            self.date_edit = None

        # ===== DESCRIPTION =====
        if self._same_description:
            self._has_editable_fields = True
            self.description_input = QLineEdit()
            self.description_input.setPlaceholderText("Description")
            self.description_input.setText(self._common_description or "")
            self.description_input.setMinimumHeight(32)
            layout.addWidget(self.description_input)
        else:
            self.description_input = None

        # ===== CATEGORY & PARTY ROW =====
        if self._same_category or self._same_party:
            cat_party_layout = QHBoxLayout()
            cat_party_layout.setSpacing(8)

            if self._same_category:
                self._has_editable_fields = True
                self.category_input = QComboBox()
                self.category_input.setEditable(True)
                self.category_input.setPlaceholderText("Category")
                self.category_input.setMinimumHeight(32)
                self._populate_categories()
                if self._common_category:
                    idx = self.category_input.findText(self._common_category)
                    if idx >= 0:
                        self.category_input.setCurrentIndex(idx)
                    else:
                        self.category_input.setCurrentText(self._common_category)
                cat_party_layout.addWidget(self.category_input, 1)
            else:
                self.category_input = None

            if self._same_party:
                self._has_editable_fields = True
                self.party_input = QLineEdit()
                self.party_input.setPlaceholderText("Party")
                self.party_input.setText(self._common_party or "")
                self.party_input.setMinimumHeight(32)
                cat_party_layout.addWidget(self.party_input, 1)
            else:
                self.party_input = None

            layout.addLayout(cat_party_layout)
        else:
            self.category_input = None
            self.party_input = None

        # ===== SHEET & STATUS ROW =====
        show_sheet = self._same_sheet and len(self._available_sheets) > 1
        show_status = self._same_status and self._all_expenses

        if show_sheet or show_status:
            sheet_status_layout = QHBoxLayout()
            sheet_status_layout.setSpacing(8)

            if show_sheet:
                self._has_editable_fields = True
                self.sheet_combo = QComboBox()
                self.sheet_combo.setMinimumHeight(32)
                self.sheet_combo.addItems(self._available_sheets)
                if self._common_sheet:
                    idx = self.sheet_combo.findText(self._common_sheet)
                    if idx >= 0:
                        self.sheet_combo.setCurrentIndex(idx)
                sheet_status_layout.addWidget(self.sheet_combo, 1)
            else:
                self.sheet_combo = None

            if show_status:
                self._has_editable_fields = True
                self.status_combo = QComboBox()
                self.status_combo.setMinimumHeight(32)
                self.status_combo.addItems(["Pending", "Approved", "Rejected"])
                status_map = {
                    ApprovalStatus.PENDING: 0,
                    ApprovalStatus.APPROVED: 1,
                    ApprovalStatus.REJECTED: 2,
                }
                if self._common_status in status_map:
                    self.status_combo.setCurrentIndex(status_map[self._common_status])
                sheet_status_layout.addWidget(self.status_combo, 1)
            else:
                self.status_combo = None

            layout.addLayout(sheet_status_layout)
        else:
            self.sheet_combo = None
            self.status_combo = None

        # ===== NOTES =====
        if self._same_notes:
            self._has_editable_fields = True
            self.notes_input = QLineEdit()
            self.notes_input.setPlaceholderText("Notes")
            self.notes_input.setText(self._common_notes or "")
            self.notes_input.setMinimumHeight(32)
            layout.addWidget(self.notes_input)
        else:
            self.notes_input = None

        # If no editable fields, show message
        if not self._has_editable_fields:
            no_fields_label = QLabel("No fields are identical across all selected transactions.")
            no_fields_label.setObjectName("secondary_text")
            no_fields_label.setWordWrap(True)
            layout.addWidget(no_fields_label)

        layout.addStretch()

        # ===== BUTTONS =====
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)

        # Disable save if no editable fields
        if not self._has_editable_fields:
            button_box.button(QDialogButtonBox.Save).setEnabled(False)

        layout.addWidget(button_box)

    def _populate_categories(self) -> None:
        """Populate category dropdown."""
        if not self.category_input:
            return

        # Determine type for category list
        is_expense = True
        if self.expense_btn:
            is_expense = self.expense_btn.isChecked()
        elif self._common_type:
            is_expense = self._common_type == TransactionType.EXPENSE

        if is_expense:
            categories = [
                "Groceries", "Transport", "Entertainment", "Utilities",
                "Rent", "Healthcare", "Education", "Other",
            ]
        else:
            categories = [
                "Salary", "Freelance", "Investment", "Gift", "Other",
            ]

        current_text = self.category_input.currentText()
        self.category_input.clear()
        self.category_input.addItems(categories)

        if current_text:
            idx = self.category_input.findText(current_text)
            if idx >= 0:
                self.category_input.setCurrentIndex(idx)
            else:
                self.category_input.setCurrentText(current_text)

    def _setup_completers(self) -> None:
        """Set up autocomplete for description, category, and party fields."""
        if not self._context:
            return

        transactions = self._context.state.transactions.value
        descriptions = sorted(
            {t.description for t in transactions if t.description},
            key=str.lower,
        )
        parties = sorted(
            {t.party for t in transactions if t.party},
            key=str.lower,
        )
        categories = sorted(
            {t.category for t in transactions if t.category},
            key=str.lower,
        )

        self._completer_filters = []

        if self.description_input:
            desc_completer = QCompleter(descriptions, self)
            desc_completer.setCaseSensitivity(Qt.CaseInsensitive)
            desc_completer.setFilterMode(Qt.MatchContains)
            self.description_input.setCompleter(desc_completer)
            self._completer_filters.append(
                install_tab_accept(self.description_input, desc_completer)
            )

        if self.party_input:
            party_completer = QCompleter(parties, self)
            party_completer.setCaseSensitivity(Qt.CaseInsensitive)
            party_completer.setFilterMode(Qt.MatchContains)
            self.party_input.setCompleter(party_completer)
            self._completer_filters.append(
                install_tab_accept(self.party_input, party_completer)
            )

        if self.category_input:
            category_completer = QCompleter(categories, self)
            category_completer.setCaseSensitivity(Qt.CaseInsensitive)
            category_completer.setFilterMode(Qt.MatchContains)
            self.category_input.setCompleter(category_completer)
            self._completer_filters.append(
                install_tab_accept(self.category_input, category_completer)
            )

    def _update_category_list(self) -> None:
        """Update category list when type changes."""
        self._populate_categories()

    def _on_save(self) -> None:
        """Handle save button click."""
        self._edited_transactions = []

        for trans in self._transactions:
            updates = {}

            # Apply changed fields
            if self.expense_btn and self.income_btn:
                new_type = TransactionType.EXPENSE if self.expense_btn.isChecked() else TransactionType.INCOME
                if new_type != trans.type:
                    updates["type"] = new_type
                    # Update status if type changed
                    if new_type == TransactionType.INCOME:
                        updates["status"] = ApprovalStatus.AUTO

            if self.amount_input:
                new_amount = Decimal(str(self.amount_input.value()))
                if new_amount != trans.amount:
                    updates["amount"] = new_amount

            if self.date_edit:
                new_date = self.date_edit.date().toPython()
                if new_date != trans.date:
                    updates["date"] = new_date

            if self.description_input:
                new_desc = self.description_input.text().strip()
                if new_desc and new_desc != trans.description:
                    updates["description"] = new_desc

            if self.category_input:
                new_cat = self.category_input.currentText().strip() or None
                if new_cat != trans.category:
                    updates["category"] = new_cat

            if self.party_input:
                new_party = self.party_input.text().strip() or None
                if new_party != trans.party:
                    updates["party"] = new_party

            if self.sheet_combo:
                new_sheet = self.sheet_combo.currentText()
                if new_sheet != trans.sheet:
                    updates["sheet"] = new_sheet

            if self.status_combo and trans.type == TransactionType.EXPENSE:
                status_map = [
                    ApprovalStatus.PENDING,
                    ApprovalStatus.APPROVED,
                    ApprovalStatus.REJECTED,
                ]
                new_status = status_map[self.status_combo.currentIndex()]
                if new_status != trans.status:
                    updates["status"] = new_status

            if self.notes_input:
                new_notes = self.notes_input.text().strip() or None
                if new_notes != trans.notes:
                    updates["notes"] = new_notes

            # Create updated transaction if any changes
            if updates:
                self._edited_transactions.append(trans.with_updates(**updates))
            else:
                self._edited_transactions.append(trans)

        self.accept()

    def get_edited_transactions(self) -> list[Transaction]:
        """Get the edited transactions."""
        return self._edited_transactions

    def has_changes(self) -> bool:
        """Check if there are any editable fields."""
        return self._has_editable_fields
