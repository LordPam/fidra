"""Export dialog for exporting transactions."""

from pathlib import Path
from datetime import date
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
    QFileDialog,
    QLineEdit,
    QDateEdit,
    QGroupBox,
    QMessageBox,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class ExportDialog(QDialog):
    """Dialog for configuring and executing transaction exports.

    Allows user to select:
    - Export format (CSV, Markdown, PDF)
    - Date range (optional)
    - Include balance column
    - Output file path
    """

    def __init__(self, context: "ApplicationContext", parent=None):
        """Initialize export dialog.

        Args:
            context: Application context
            parent: Parent widget
        """
        super().__init__(parent)
        self._context = context
        self._selected_path: Optional[Path] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        self.setWindowTitle("Export Transactions")
        self.setModal(True)
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Format selection
        format_group = QGroupBox("Export Format")
        format_layout = QVBoxLayout(format_group)

        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["CSV", "Markdown", "PDF"])
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        format_row.addWidget(self.format_combo, 1)
        format_layout.addLayout(format_row)

        layout.addWidget(format_group)

        # Date range
        date_group = QGroupBox("Date Range (Optional)")
        date_layout = QVBoxLayout(date_group)

        self.use_date_range_checkbox = QCheckBox("Filter by date range")
        self.use_date_range_checkbox.stateChanged.connect(self._on_date_range_toggled)
        date_layout.addWidget(self.use_date_range_checkbox)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("From:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(date.today().replace(day=1))  # First of month
        self.start_date_edit.setEnabled(False)
        date_row.addWidget(self.start_date_edit)

        date_row.addWidget(QLabel("To:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(date.today())
        self.end_date_edit.setEnabled(False)
        date_row.addWidget(self.end_date_edit)

        date_layout.addLayout(date_row)
        layout.addWidget(date_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.include_balance_checkbox = QCheckBox("Include running balance column")
        self.include_balance_checkbox.setChecked(True)
        options_layout.addWidget(self.include_balance_checkbox)

        layout.addWidget(options_group)

        # Output file
        output_group = QGroupBox("Output File")
        output_layout = QVBoxLayout(output_group)

        file_row = QHBoxLayout()
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setPlaceholderText("Choose output file...")
        self.file_path_edit.setReadOnly(True)
        file_row.addWidget(self.file_path_edit, 1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse_clicked)
        file_row.addWidget(self.browse_btn)

        output_layout.addLayout(file_row)
        layout.addWidget(output_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.export_btn.setDefault(True)
        button_layout.addWidget(self.export_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def _on_format_changed(self, format_text: str) -> None:
        """Handle format selection change.

        Args:
            format_text: Selected format text
        """
        # Update file extension in path if one is set
        if self._selected_path:
            format_lower = format_text.lower()
            extension = "md" if format_lower == "markdown" else format_lower
            new_path = self._selected_path.with_suffix(f".{extension}")
            self._selected_path = new_path
            self.file_path_edit.setText(str(new_path))

    def _on_date_range_toggled(self, state: int) -> None:
        """Handle date range checkbox toggle.

        Args:
            state: Checkbox state
        """
        enabled = state == Qt.CheckState.Checked.value
        self.start_date_edit.setEnabled(enabled)
        self.end_date_edit.setEnabled(enabled)

    def _on_browse_clicked(self) -> None:
        """Handle browse button click."""
        # Get format
        format_text = self.format_combo.currentText().lower()
        extension = "md" if format_text == "markdown" else format_text

        # File dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Transactions",
            f"transactions.{extension}",
            f"{format_text.upper()} Files (*.{extension});;All Files (*)"
        )

        if file_path:
            self._selected_path = Path(file_path)
            self.file_path_edit.setText(file_path)

    def _on_export_clicked(self) -> None:
        """Handle export button click."""
        # Validate
        if not self._selected_path:
            QMessageBox.warning(
                self,
                "No File Selected",
                "Please select an output file."
            )
            return

        # Get transactions
        transactions = self._context.state.transactions.value

        # Apply date range filter if enabled
        if self.use_date_range_checkbox.isChecked():
            start_date = self.start_date_edit.date().toPython()
            end_date = self.end_date_edit.date().toPython()

            transactions = [
                t for t in transactions
                if start_date <= t.date <= end_date
            ]

            if not transactions:
                QMessageBox.warning(
                    self,
                    "No Transactions",
                    f"No transactions found in date range {start_date} to {end_date}."
                )
                return

        # Get options
        format_text = self.format_combo.currentText().lower()
        include_balance = self.include_balance_checkbox.isChecked()

        try:
            # Export
            self._context.export_service.export(
                transactions,
                self._selected_path,
                format_text,
                include_balance
            )

            # Success
            QMessageBox.information(
                self,
                "Export Successful",
                f"Successfully exported {len(transactions)} transaction(s) to:\n{self._selected_path}"
            )

            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export transactions:\n{e}"
            )
