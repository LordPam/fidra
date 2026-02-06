"""Dialog for adding a planned transaction template."""

from datetime import date
from decimal import Decimal
from typing import Optional

from PySide6.QtCore import Qt, QDate
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


class AddPlannedDialog(QDialog):
    """Dialog for creating a new planned transaction template.

    Compact layout similar to EditPlannedDialog.
    """

    def __init__(
        self,
        current_sheet: str,
        parent=None,
        available_sheets: list[str] | None = None,
        context=None,
    ):
        """Initialize the add planned dialog.

        Args:
            current_sheet: Current sheet name for the template
            parent: Parent widget
            available_sheets: List of available sheet names (for All Sheets mode)
        """
        super().__init__(parent)
        self._current_sheet = current_sheet
        self._available_sheets = available_sheets or []
        self._is_all_sheets_mode = current_sheet == "All Sheets" and len(self._available_sheets) >= 2
        self._template: Optional[PlannedTemplate] = None
        self._context = context

        self.setWindowTitle("Add Planned Transaction")
        self.setModal(True)
        self.setMinimumWidth(500)

        self._setup_ui()
        self._setup_completers()

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
        self.expense_btn.setChecked(True)  # Default to expense

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
        self.date_edit.setDate(QDate.currentDate())
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
            # Select "Main" by default if available
            main_index = self.sheet_combo.findText("Main")
            if main_index >= 0:
                self.sheet_combo.setCurrentIndex(main_index)
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

        # Hide sheet selector if not in All Sheets mode or only one sheet
        if not self._is_all_sheets_mode:
            self.sheet_combo.setVisible(False)

        # ===== END CONDITIONS (for recurring) =====
        end_frame = QFrame()
        end_frame.setObjectName("secondary_frame")
        end_layout = QVBoxLayout(end_frame)
        end_layout.setContentsMargins(8, 8, 8, 8)
        end_layout.setSpacing(6)

        end_label = QLabel("End Condition (for recurring)")
        end_label.setObjectName("secondary_text")
        end_layout.addWidget(end_label)

        # End date row
        end_date_row = QHBoxLayout()
        self.end_date_check = QCheckBox("End Date:")
        self.end_date_check.stateChanged.connect(self._on_end_date_checked)
        end_date_row.addWidget(self.end_date_check)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("dd MMM yyyy")
        self.end_date_edit.setDate(QDate.currentDate().addMonths(3))
        self.end_date_edit.setEnabled(False)
        self.end_date_edit.setMinimumHeight(28)
        end_date_row.addWidget(self.end_date_edit, 1)
        end_layout.addLayout(end_date_row)

        # Occurrence count row
        occurrence_row = QHBoxLayout()
        self.occurrence_check = QCheckBox("After:")
        self.occurrence_check.stateChanged.connect(self._on_occurrence_checked)
        occurrence_row.addWidget(self.occurrence_check)

        self.occurrence_spin = QSpinBox()
        self.occurrence_spin.setRange(1, 1000)
        self.occurrence_spin.setValue(12)
        self.occurrence_spin.setEnabled(False)
        self.occurrence_spin.setMinimumHeight(28)
        occurrence_row.addWidget(self.occurrence_spin)

        occurrence_row.addWidget(QLabel("occurrences"))
        occurrence_row.addStretch()
        end_layout.addLayout(occurrence_row)

        self.end_frame = end_frame
        layout.addWidget(end_frame)

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

    def _update_category_list(self) -> None:
        """Update category dropdown based on selected type."""
        is_expense = self.expense_btn.isChecked()

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
            index = self.category_input.findText(current_text)
            if index >= 0:
                self.category_input.setCurrentIndex(index)
            else:
                self.category_input.setCurrentText(current_text)

    def _on_frequency_changed(self, index: int) -> None:
        """Handle frequency change - enable/disable end conditions."""
        is_once = index == 0
        self.end_frame.setEnabled(not is_once)
        self.end_date_check.setEnabled(not is_once)
        self.occurrence_check.setEnabled(not is_once)

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
        if self._is_all_sheets_mode:
            target_sheet = self.sheet_combo.currentText()
            if not target_sheet and self._available_sheets:
                target_sheet = self._available_sheets[0]
        else:
            target_sheet = self._current_sheet

        # Create template
        self._template = PlannedTemplate.create(
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

        if self._is_all_sheets_mode and not self.sheet_combo.currentText():
            self.sheet_combo.setFocus()
            return False

        if self.end_date_check.isChecked():
            start = self.date_edit.date()
            end = self.end_date_edit.date()
            if end <= start:
                self.end_date_edit.setFocus()
                return False

        return True

    def get_template(self) -> Optional[PlannedTemplate]:
        """Get the created template."""
        return self._template
