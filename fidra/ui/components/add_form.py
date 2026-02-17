"""Add transaction form widget."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, TYPE_CHECKING

import qasync
from PySide6.QtCore import Signal, QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QDateEdit,
    QComboBox,
    QPushButton,
    QButtonGroup,
    QFrame,
    QCompleter,
    QSizePolicy,
)

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.ui.components.completer_utils import install_tab_accept

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class AddTransactionForm(QWidget):
    """Form for adding new transactions.

    Modern card-style design with:
    - Type toggle (segmented control style)
    - Conditional sheet selector (shown in "All Sheets" view)
    - Grouped fields with subtle labels
    - Prominent submit button
    """

    # Signal emitted when form is submitted
    transaction_added = Signal(Transaction)
    # Internal signal for async category loading (to work with qasync)
    _trigger_load_categories = Signal()

    def __init__(self, sheet: str = "Main", parent=None, context: Optional["ApplicationContext"] = None):
        """Initialize the add form.

        Args:
            sheet: Default sheet name for transactions
            parent: Parent widget
            context: Application context for autocomplete data
        """
        super().__init__(parent)
        self._sheet = sheet
        self._is_all_sheets_mode = False
        self._available_sheets: list[str] = []
        self._context = context

        # Category cache - loaded from database asynchronously
        self._income_categories: list[str] = []
        self._expense_categories: list[str] = []
        self._categories_loaded = False

        # Connect internal signal to async handler
        self._trigger_load_categories.connect(self._handle_load_categories)

        self._setup_ui()
        self._setup_completers()

        # Load categories from database (deferred to avoid qasync re-entrancy)
        QTimer.singleShot(0, self._start_load_categories)

    def _setup_ui(self) -> None:
        """Set up the form UI - elements spread to fill available space."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)  # We'll use stretches for spacing

        # ===== HEADER =====
        header = QLabel("New Transaction")
        header.setObjectName("form_header")
        layout.addWidget(header)

        layout.addStretch(1)

        # ===== TYPE TOGGLE (Segmented Control Style) =====
        type_container = QFrame()
        type_container.setObjectName("type_toggle_container")
        type_layout = QHBoxLayout(type_container)
        type_layout.setContentsMargins(3, 3, 3, 3)
        type_layout.setSpacing(0)

        self.expense_btn = QPushButton("Expense")
        self.expense_btn.setObjectName("type_expense")
        self.expense_btn.setCheckable(True)
        self.expense_btn.setChecked(True)  # Default to expense

        self.income_btn = QPushButton("Income")
        self.income_btn.setObjectName("type_income")
        self.income_btn.setCheckable(True)

        self.type_group = QButtonGroup(self)
        self.type_group.addButton(self.expense_btn, 0)
        self.type_group.addButton(self.income_btn, 1)

        type_layout.addWidget(self.expense_btn)
        type_layout.addWidget(self.income_btn)

        layout.addWidget(type_container)

        layout.addStretch(1)

        # ===== AMOUNT & DATE ROW =====
        amount_date_layout = QHBoxLayout()
        amount_date_layout.setSpacing(8)

        self.amount_input = QDoubleSpinBox()
        self.amount_input.setObjectName("amount_input")
        self.amount_input.setPrefix("£ ")
        self.amount_input.setRange(0.01, 999999.99)
        self.amount_input.setDecimals(2)
        self.amount_input.setValue(0.00)
        self.amount_input.setMinimumHeight(26)
        amount_date_layout.addWidget(self.amount_input, 1)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd MMM")
        self.date_edit.setMinimumHeight(26)
        amount_date_layout.addWidget(self.date_edit, 1)

        layout.addLayout(amount_date_layout)

        layout.addStretch(1)

        # ===== DESCRIPTION =====
        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Description")
        self.description_input.setMinimumHeight(26)
        layout.addWidget(self.description_input)

        layout.addStretch(1)

        # ===== CATEGORY & PARTY ROW =====
        cat_party_layout = QHBoxLayout()
        cat_party_layout.setSpacing(8)

        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.setPlaceholderText("Category")
        self.category_input.setMinimumHeight(26)
        self.category_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._update_category_list()
        cat_party_layout.addWidget(self.category_input, 1)

        self.party_input = QLineEdit()
        self.party_input.setPlaceholderText("Party")
        self.party_input.setMinimumHeight(26)
        self.party_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        cat_party_layout.addWidget(self.party_input, 1)

        layout.addLayout(cat_party_layout)

        layout.addStretch(1)

        # ===== REFERENCE =====
        self.reference_input = QLineEdit()
        self.reference_input.setPlaceholderText("Reference (bank statement, invoice #, etc.)")
        self.reference_input.setMinimumHeight(26)
        layout.addWidget(self.reference_input)

        layout.addStretch(1)

        # ===== NOTES (Single line, optional) =====
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Notes (optional)")
        self.notes_input.setMinimumHeight(26)
        layout.addWidget(self.notes_input)

        layout.addStretch(1)

        # ===== SHEET SELECTOR (Only shown in All Sheets mode with 2+ sheets) =====
        self.sheet_input = QComboBox()
        self.sheet_input.setPlaceholderText("Sheet")
        self.sheet_input.setMinimumHeight(26)
        self.sheet_input.setVisible(False)  # Hidden by default
        layout.addWidget(self.sheet_input)

        # Stretch only added when sheet selector is hidden (managed in set methods)
        self.sheet_stretch = layout.addStretch(1)

        # ===== SUBMIT BUTTON =====
        self.submit_btn = QPushButton("Add Transaction")
        self.submit_btn.setObjectName("submit_button")
        self.submit_btn.setMinimumHeight(30)
        self.submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.submit_btn)

        # Connect type button to category update
        self.type_group.buttonClicked.connect(self._update_category_list)

    def _start_load_categories(self) -> None:
        """Start loading categories from database."""
        if self._context:
            self._trigger_load_categories.emit()

    @qasync.asyncSlot()
    async def _handle_load_categories(self) -> None:
        """Handle async category loading (via signal)."""
        try:
            await self._load_categories()
        except RuntimeError as e:
            if "Cannot enter into task" not in str(e):
                pass  # Ignore qasync re-entrancy, fall back to defaults
        except Exception:
            pass  # Fall back to defaults on error

    async def _load_categories(self) -> None:
        """Load categories from database asynchronously."""
        try:
            self._income_categories = await self._context.get_categories("income")
            self._expense_categories = await self._context.get_categories("expense")
            self._categories_loaded = True
            # Update the category dropdown with loaded categories
            self._update_category_list()
        except Exception:
            # Fall back to defaults on error
            self._categories_loaded = True

    def _update_category_list(self) -> None:
        """Update category dropdown based on selected type."""
        is_expense = self.expense_btn.isChecked()

        # Get categories from cache if loaded, otherwise use defaults
        if self._categories_loaded and self._context:
            if is_expense:
                categories = self._expense_categories.copy()
            else:
                categories = self._income_categories.copy()
        else:
            # Fallback defaults (used before async load completes)
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

    def _on_submit(self) -> None:
        """Handle form submission."""
        # Validate
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

        # Determine which sheet to use
        if self._is_all_sheets_mode:
            # In All Sheets mode: use selected sheet from dropdown, or first available
            if self.sheet_input.currentText():
                sheet = self.sheet_input.currentText()
            elif self._available_sheets:
                sheet = self._available_sheets[0]
            else:
                sheet = "Main"  # Fallback
        else:
            sheet = self._sheet

        # Income is auto-approved, expenses are pending
        status = ApprovalStatus.AUTO if trans_type == TransactionType.INCOME else ApprovalStatus.PENDING

        # Create transaction
        transaction = Transaction.create(
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

        # Emit signal
        self.transaction_added.emit(transaction)

        # Clear form
        self._clear_form()

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

        # In All Sheets mode with 2+ sheets, sheet must be selected
        if self._is_all_sheets_mode and len(self._available_sheets) >= 2:
            if not self.sheet_input.currentText():
                self.sheet_input.setFocus()
                return False

        return True

    def _clear_form(self) -> None:
        """Clear all form fields."""
        self.description_input.clear()
        self.amount_input.setValue(0.00)
        self.category_input.setCurrentIndex(0)
        self.party_input.clear()
        self.reference_input.clear()
        self.notes_input.clear()
        self.date_edit.setDate(QDate.currentDate())
        self.amount_input.setFocus()

    def set_sheet(self, sheet: str) -> None:
        """Set the sheet for new transactions.

        Args:
            sheet: Sheet name (or "All Sheets" for all sheets mode)
        """
        if sheet == "All Sheets":
            self._is_all_sheets_mode = True
            # Only show selector if there are 2+ sheets
            # With 0-1 sheets, "All Sheets" is synonymous with that sheet
            self.sheet_input.setVisible(len(self._available_sheets) >= 2)
            self._select_default_sheet()
        else:
            self._is_all_sheets_mode = False
            self._sheet = sheet
            self.sheet_input.setVisible(False)

    def set_available_sheets(self, sheets: list[str]) -> None:
        """Set the list of available sheets for the sheet selector.

        Args:
            sheets: List of sheet names
        """
        self._available_sheets = sheets
        self.sheet_input.clear()
        self.sheet_input.addItems(sheets)
        # Only show selector if in All Sheets mode AND there are 2+ sheets
        if self._is_all_sheets_mode:
            self.sheet_input.setVisible(len(sheets) >= 2)
        self._select_default_sheet()

    def _select_default_sheet(self) -> None:
        """Select the default sheet (Main if available, otherwise first)."""
        if not self._available_sheets:
            return

        # Try to select "Main" first
        main_index = self.sheet_input.findText("Main")
        if main_index >= 0:
            self.sheet_input.setCurrentIndex(main_index)
        elif self.sheet_input.count() > 0:
            self.sheet_input.setCurrentIndex(0)

    def _setup_completers(self) -> None:
        """Set up autocomplete for description and party fields."""
        if not self._context:
            return
        self._completer_filters = []

        # Description completer
        self._description_completer = QCompleter(self)
        self._description_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._description_completer.setFilterMode(Qt.MatchContains)
        self.description_input.setCompleter(self._description_completer)
        self._completer_filters.append(
            install_tab_accept(self.description_input, self._description_completer)
        )

        # Party completer
        self._party_completer = QCompleter(self)
        self._party_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._party_completer.setFilterMode(Qt.MatchContains)
        self.party_input.setCompleter(self._party_completer)
        self._completer_filters.append(
            install_tab_accept(self.party_input, self._party_completer)
        )

        # Connect to transactions changes to update completers
        self._context.state.transactions.changed.connect(self._update_completer_data)

        # Initial update
        self._update_completer_data(self._context.state.transactions.value)

    def _update_completer_data(self, transactions: list[Transaction]) -> None:
        """Update completer data from transactions.

        Args:
            transactions: List of transactions to extract data from
        """
        if not self._context:
            return

        # Extract unique descriptions and parties
        descriptions = set()
        parties = set()

        for t in transactions:
            if t.description:
                descriptions.add(t.description)
            if t.party:
                parties.add(t.party)

        # Sort alphabetically
        desc_list = sorted(descriptions, key=str.lower)
        party_list = sorted(parties, key=str.lower)

        # Update completers with QStringListModel
        from PySide6.QtCore import QStringListModel
        self._description_completer.setModel(QStringListModel(desc_list))
        self._party_completer.setModel(QStringListModel(party_list))
