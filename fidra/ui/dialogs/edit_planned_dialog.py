"""Edit planned transaction template dialog."""

from datetime import date
from decimal import Decimal
from typing import Optional

import qasync
from PySide6.QtCore import Qt, QDate, QTimer, Signal
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
    QSpinBox,
    QCheckBox,
    QFrame,
    QCompleter,
)

from fidra.domain.models import PlannedTemplate, TransactionType, Frequency
from fidra.ui.components.completer_utils import install_tab_accept


class EditPlannedDialog(QDialog):
    """Dialog for editing a planned transaction template.

    Compact layout similar to EditTransactionDialog.
    """

    # Internal signal for async category loading (to work with qasync)
    _trigger_load_categories = Signal()

    def __init__(
        self,
        template: PlannedTemplate,
        parent=None,
        available_sheets: Optional[list[str]] = None,
        context=None,
        income_categories: Optional[list[str]] = None,
        expense_categories: Optional[list[str]] = None,
    ):
        """Initialize the edit planned dialog.

        Args:
            template: PlannedTemplate to edit
            parent: Parent widget
            available_sheets: List of available sheet names
            context: Application context (optional if categories provided)
            income_categories: Pre-loaded income categories (avoids async loading)
            expense_categories: Pre-loaded expense categories (avoids async loading)
        """
        super().__init__(parent)
        self._original_template = template
        self._edited_template: Optional[PlannedTemplate] = None
        self._available_sheets = available_sheets or []
        self._context = context

        # Category cache - use pre-loaded if provided
        self._income_categories: list[str] = income_categories or []
        self._expense_categories: list[str] = expense_categories or []
        self._categories_loaded = bool(income_categories or expense_categories)

        self.setWindowTitle("Edit Planned Transaction")
        self.setModal(True)
        self.setMinimumWidth(500)

        # Connect internal signal to async handler
        self._trigger_load_categories.connect(self._handle_load_categories)

        self._setup_ui()
        self._setup_completers()
        self._populate_fields()

        # Load categories from database only if not pre-loaded
        if not self._categories_loaded:
            QTimer.singleShot(0, self._start_load_categories)

    def _setup_ui(self) -> None:
        """Set up the dialog UI - compact layout like transaction edit dialog."""
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

        # ===== AMOUNT & START DATE ROW =====
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

        # ===== SHEET & FREQUENCY ROW =====
        sheet_freq_layout = QHBoxLayout()
        sheet_freq_layout.setSpacing(8)

        # Sheet selector
        self.sheet_combo = QComboBox()
        self.sheet_combo.setMinimumHeight(32)
        if self._available_sheets:
            self.sheet_combo.addItems(self._available_sheets)
        sheet_freq_layout.addWidget(self.sheet_combo, 1)

        # Frequency selector
        self.frequency_combo = QComboBox()
        self.frequency_combo.setMinimumHeight(32)
        self.frequency_combo.addItems([
            "Once",
            "Weekly",
            "Biweekly",
            "Monthly",
            "Quarterly",
            "Yearly",
        ])
        self.frequency_combo.currentIndexChanged.connect(self._on_frequency_changed)
        sheet_freq_layout.addWidget(self.frequency_combo, 1)

        layout.addLayout(sheet_freq_layout)

        # Hide sheet selector if only one sheet
        if len(self._available_sheets) <= 1:
            self.sheet_combo.setVisible(False)

        # ===== END CONDITIONS (for recurring) =====
        self.end_frame = QFrame()
        self.end_frame.setObjectName("secondary_frame")
        end_layout = QHBoxLayout(self.end_frame)
        end_layout.setContentsMargins(10, 8, 10, 8)
        end_layout.setSpacing(12)

        # End date option
        self.end_date_check = QCheckBox("End date")
        self.end_date_check.stateChanged.connect(self._on_end_date_checked)
        end_layout.addWidget(self.end_date_check)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("dd MMM yyyy")
        self.end_date_edit.setEnabled(False)
        self.end_date_edit.setMinimumHeight(28)
        end_layout.addWidget(self.end_date_edit)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("toolbar_separator")
        sep.setFixedHeight(20)
        end_layout.addWidget(sep)

        # Occurrence count option
        self.occurrence_check = QCheckBox("After")
        self.occurrence_check.stateChanged.connect(self._on_occurrence_checked)
        end_layout.addWidget(self.occurrence_check)

        self.occurrence_spin = QSpinBox()
        self.occurrence_spin.setRange(1, 1000)
        self.occurrence_spin.setValue(12)
        self.occurrence_spin.setEnabled(False)
        self.occurrence_spin.setMinimumHeight(28)
        self.occurrence_spin.setFixedWidth(70)
        end_layout.addWidget(self.occurrence_spin)

        self.occurrence_label = QLabel("occurrences")
        end_layout.addWidget(self.occurrence_label)
        end_layout.addStretch()

        layout.addWidget(self.end_frame)

        # ===== BUTTONS =====
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Connect type button to category update
        self.type_group.buttonClicked.connect(self._update_category_list)

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

        desc_completer = QCompleter(descriptions, self)
        desc_completer.setCaseSensitivity(Qt.CaseInsensitive)
        desc_completer.setFilterMode(Qt.MatchContains)
        self.description_input.setCompleter(desc_completer)
        self._completer_filters.append(
            install_tab_accept(self.description_input, desc_completer)
        )

        party_completer = QCompleter(parties, self)
        party_completer.setCaseSensitivity(Qt.CaseInsensitive)
        party_completer.setFilterMode(Qt.MatchContains)
        self.party_input.setCompleter(party_completer)
        self._completer_filters.append(
            install_tab_accept(self.party_input, party_completer)
        )

        category_completer = QCompleter(categories, self)
        category_completer.setCaseSensitivity(Qt.CaseInsensitive)
        category_completer.setFilterMode(Qt.MatchContains)
        self.category_input.setCompleter(category_completer)
        self._completer_filters.append(
            install_tab_accept(self.category_input, category_completer)
        )

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

        if current_text:
            index = self.category_input.findText(current_text)
            if index >= 0:
                self.category_input.setCurrentIndex(index)
            else:
                self.category_input.setCurrentText(current_text)

    def _on_frequency_changed(self, index: int) -> None:
        """Handle frequency change - hide end conditions for one-time."""
        is_once = index == 0
        self.end_frame.setVisible(not is_once)

        if is_once:
            self.end_date_check.setChecked(False)
            self.occurrence_check.setChecked(False)

    def _on_end_date_checked(self, state: int) -> None:
        """Handle end date checkbox state change."""
        is_checked = state == Qt.CheckState.Checked.value
        self.end_date_edit.setEnabled(is_checked)
        if is_checked:
            self.occurrence_check.setChecked(False)

    def _on_occurrence_checked(self, state: int) -> None:
        """Handle occurrence count checkbox state change."""
        is_checked = state == Qt.CheckState.Checked.value
        self.occurrence_spin.setEnabled(is_checked)
        if is_checked:
            self.end_date_check.setChecked(False)

    def _populate_fields(self) -> None:
        """Populate form fields with template data."""
        t = self._original_template

        # Type
        if t.type == TransactionType.EXPENSE:
            self.expense_btn.setChecked(True)
        else:
            self.income_btn.setChecked(True)

        self._update_category_list()

        # Date
        q_date = QDate(t.start_date.year, t.start_date.month, t.start_date.day)
        self.date_edit.setDate(q_date)

        # Description
        self.description_input.setText(t.description)

        # Amount
        self.amount_input.setValue(float(t.amount))

        # Category
        if t.category:
            index = self.category_input.findText(t.category)
            if index >= 0:
                self.category_input.setCurrentIndex(index)
            else:
                self.category_input.setCurrentText(t.category)

        # Party
        if t.party:
            self.party_input.setText(t.party)

        # Sheet
        if t.target_sheet and self._available_sheets:
            index = self.sheet_combo.findText(t.target_sheet)
            if index >= 0:
                self.sheet_combo.setCurrentIndex(index)

        # Frequency
        frequency_map = {
            Frequency.ONCE: 0,
            Frequency.WEEKLY: 1,
            Frequency.BIWEEKLY: 2,
            Frequency.MONTHLY: 3,
            Frequency.QUARTERLY: 4,
            Frequency.YEARLY: 5,
        }
        self.frequency_combo.setCurrentIndex(frequency_map.get(t.frequency, 0))
        self._on_frequency_changed(self.frequency_combo.currentIndex())

        # End conditions
        if t.end_date:
            self.end_date_check.setChecked(True)
            q_end = QDate(t.end_date.year, t.end_date.month, t.end_date.day)
            self.end_date_edit.setDate(q_end)
        elif t.occurrence_count:
            self.occurrence_check.setChecked(True)
            self.occurrence_spin.setValue(t.occurrence_count)

    def _on_save(self) -> None:
        """Handle save button click."""
        if not self._validate():
            return

        # Get values
        start_date_py = self.date_edit.date().toPython()
        description = self.description_input.text().strip()
        amount = Decimal(str(self.amount_input.value()))
        trans_type = TransactionType.EXPENSE if self.expense_btn.isChecked() else TransactionType.INCOME
        category = self.category_input.currentText().strip() or None
        party = self.party_input.text().strip() or None

        # Frequency
        frequency_map = [
            Frequency.ONCE, Frequency.WEEKLY, Frequency.BIWEEKLY,
            Frequency.MONTHLY, Frequency.QUARTERLY, Frequency.YEARLY,
        ]
        frequency = frequency_map[self.frequency_combo.currentIndex()]

        # End condition
        end_date = None
        occurrence_count = None
        if self.end_date_check.isChecked():
            end_date = self.end_date_edit.date().toPython()
        elif self.occurrence_check.isChecked():
            occurrence_count = self.occurrence_spin.value()

        # Sheet
        if self._available_sheets and len(self._available_sheets) > 1:
            target_sheet = self.sheet_combo.currentText()
        else:
            target_sheet = self._original_template.target_sheet

        # Create updated template
        self._edited_template = self._original_template.with_updates(
            start_date=start_date_py,
            description=description,
            amount=amount,
            type=trans_type,
            target_sheet=target_sheet,
            frequency=frequency,
            end_date=end_date,
            occurrence_count=occurrence_count,
            category=category,
            party=party,
        )

        self.accept()

    def _validate(self) -> bool:
        """Validate form inputs."""
        if not self.description_input.text().strip():
            self.description_input.setFocus()
            return False

        if self.amount_input.value() <= 0:
            self.amount_input.setFocus()
            return False

        if self.end_date_check.isChecked():
            start = self.date_edit.date()
            end = self.end_date_edit.date()
            if end <= start:
                self.end_date_edit.setFocus()
                return False

        return True

    def get_edited_template(self) -> Optional[PlannedTemplate]:
        """Get the edited template."""
        return self._edited_template
