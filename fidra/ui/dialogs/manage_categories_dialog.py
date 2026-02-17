"""Manage categories dialog for editing income and expense categories."""

from typing import TYPE_CHECKING

import qasync
from PySide6.QtCore import Qt, Signal, QTimer
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
    QTabWidget,
    QWidget,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class CategoryListWidget(QWidget):
    """Widget for managing a single category list."""

    def __init__(self, categories: list[str], category_type: str, parent=None):
        """Initialize category list widget.

        Args:
            categories: Initial list of categories
            category_type: Type name (e.g., "Income" or "Expense")
            parent: Parent widget
        """
        super().__init__(parent)
        self._category_type = category_type
        self._setup_ui(categories)

    def _setup_ui(self, categories: list[str]) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Category list
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_edit_clicked)

        for category in categories:
            self.list_widget.addItem(category)

        layout.addWidget(self.list_widget)

        # Buttons
        button_layout = QHBoxLayout()

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self._on_add_clicked)
        button_layout.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        self.edit_btn.setEnabled(False)
        button_layout.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        button_layout.addWidget(self.delete_btn)

        button_layout.addStretch()

        layout.addLayout(button_layout)

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        has_selection = bool(self.list_widget.selectedItems())
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def _on_add_clicked(self) -> None:
        """Handle add button click."""
        name, ok = QInputDialog.getText(
            self,
            f"Add {self._category_type} Category",
            "Category name:",
            QLineEdit.EchoMode.Normal,
            ""
        )

        if ok and name.strip():
            name = name.strip()
            # Check for duplicates
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).text().lower() == name.lower():
                    QMessageBox.warning(
                        self,
                        "Duplicate",
                        f"A category named '{name}' already exists."
                    )
                    return
            self.list_widget.addItem(name)

    def _on_edit_clicked(self) -> None:
        """Handle edit button click."""
        current = self.list_widget.currentItem()
        if not current:
            return

        name, ok = QInputDialog.getText(
            self,
            f"Edit {self._category_type} Category",
            "Category name:",
            QLineEdit.EchoMode.Normal,
            current.text()
        )

        if ok and name.strip():
            name = name.strip()
            # Check for duplicates (excluding current)
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item != current and item.text().lower() == name.lower():
                    QMessageBox.warning(
                        self,
                        "Duplicate",
                        f"A category named '{name}' already exists."
                    )
                    return
            current.setText(name)

    def _on_delete_clicked(self) -> None:
        """Handle delete button click."""
        current = self.list_widget.currentItem()
        if not current:
            return

        reply = QMessageBox.question(
            self,
            "Delete Category",
            f"Delete category '{current.text()}'?\n\n"
            "Existing transactions with this category will keep their category value.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            row = self.list_widget.row(current)
            self.list_widget.takeItem(row)

    def get_categories(self) -> list[str]:
        """Get the current list of categories.

        Returns:
            List of category names in order
        """
        return [
            self.list_widget.item(i).text()
            for i in range(self.list_widget.count())
        ]


class ManageCategoriesDialog(QDialog):
    """Dialog for managing income and expense categories.

    Features:
    - Separate tabs for income and expense categories
    - Add, edit, delete categories
    - Reorder categories (drag and drop or up/down buttons)
    - Categories stored per-database (not in global settings)
    """

    # Internal signals for async operations (to work with qasync)
    _trigger_load_categories = Signal()
    _trigger_save_categories = Signal()

    def __init__(self, context: "ApplicationContext", parent=None):
        """Initialize manage categories dialog.

        Args:
            context: Application context
            parent: Parent widget
        """
        super().__init__(parent)
        self._context = context

        # Connect internal signals to async handlers
        self._trigger_load_categories.connect(self._handle_load_categories)
        self._trigger_save_categories.connect(self._handle_save_categories)

        self._setup_ui()
        # Load categories from database asynchronously (deferred)
        QTimer.singleShot(0, lambda: self._trigger_load_categories.emit())

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        self.setWindowTitle("Manage Categories")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Manage Categories")
        header.setObjectName("section_header")
        layout.addWidget(header)

        info = QLabel(
            "Categories appear in the dropdown when adding or editing transactions. "
            "Drag items or use arrows to reorder."
        )
        info.setWordWrap(True)
        info.setObjectName("secondary_text")
        layout.addWidget(info)

        # Tab widget for income/expense
        self.tab_widget = QTabWidget()

        # Income categories tab - initially empty, loaded async
        self.income_list = CategoryListWidget([], "Income")
        self.tab_widget.addTab(self.income_list, "Income Categories")

        # Expense categories tab - initially empty, loaded async
        self.expense_list = CategoryListWidget([], "Expense")
        self.tab_widget.addTab(self.expense_list, "Expense Categories")

        layout.addWidget(self.tab_widget)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setEnabled(False)  # Disabled until categories loaded
        button_layout.addWidget(self.save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    @qasync.asyncSlot()
    async def _handle_load_categories(self) -> None:
        """Handle async category loading (via signal)."""
        try:
            await self._load_categories()
        except RuntimeError as e:
            if "Cannot enter into task" not in str(e):
                raise  # Re-raise non-qasync errors (handled by _load_categories)

    @qasync.asyncSlot()
    async def _handle_save_categories(self) -> None:
        """Handle async category saving (via signal)."""
        try:
            await self._save_categories()
        except RuntimeError as e:
            if "Cannot enter into task" not in str(e):
                raise  # Re-raise non-qasync errors (handled by _save_categories)

    async def _load_categories(self) -> None:
        """Load categories from database."""
        try:
            income_cats = await self._context.get_categories("income")
            expense_cats = await self._context.get_categories("expense")

            # Populate the list widgets
            for cat in income_cats:
                self.income_list.list_widget.addItem(cat)
            for cat in expense_cats:
                self.expense_list.list_widget.addItem(cat)

            # Enable save button now that categories are loaded
            self.save_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load categories:\n\n{e}"
            )

    def _on_save(self) -> None:
        """Save categories and close dialog."""
        self._trigger_save_categories.emit()

    async def _save_categories(self) -> None:
        """Save categories to database asynchronously."""
        try:
            # Get current categories from the list widgets
            income_cats = self.income_list.get_categories()
            expense_cats = self.expense_list.get_categories()

            # Save to database
            await self._context.set_categories("income", income_cats)
            await self._context.set_categories("expense", expense_cats)

            QMessageBox.information(
                self,
                "Saved",
                "Categories have been saved."
            )

            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save categories:\n\n{e}"
            )
