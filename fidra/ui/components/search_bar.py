"""Search bar component with boolean query support."""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QCheckBox,
)


class SearchBar(QWidget):
    """Search bar widget with boolean query support.

    Features:
    - Real-time search with debouncing
    - Clear button
    - Result count display
    - Filtered balance mode toggle
    - Query syntax tooltip

    Signals:
        search_changed(str): Emitted when search query changes (debounced)
        filter_mode_changed(bool): Emitted when filtered balance toggle changes
    """

    # Signals
    search_changed = Signal(str)
    filter_mode_changed = Signal(bool)

    def __init__(self, parent=None):
        """Initialize search bar.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emit_search_changed)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search transactions... (e.g. coffee AND NOT pending)")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_text_changed)
        self.search_input.setToolTip(
            "Boolean search syntax:\n"
            "  • coffee - simple term\n"
            "  • coffee AND fuel - both terms\n"
            "  • coffee OR fuel - either term\n"
            "  • NOT pending - exclude term\n"
            "  • (coffee OR fuel) AND car - grouping\n"
            "\n"
            "Searches: description, amount, type, status, category, party, notes"
        )
        layout.addWidget(self.search_input, 1)

        # Result count label
        self.result_label = QLabel("")
        self.result_label.setObjectName("secondary_text")
        layout.addWidget(self.result_label)

        # Filtered balance toggle
        self.filter_mode_checkbox = QCheckBox("Filtered Balance")
        self.filter_mode_checkbox.setToolTip(
            "When checked, balance is calculated from visible (filtered) transactions only.\n"
            "When unchecked, balance shows all transactions regardless of filter."
        )
        self.filter_mode_checkbox.stateChanged.connect(self._on_filter_mode_changed)
        layout.addWidget(self.filter_mode_checkbox)

    def _on_text_changed(self, text: str) -> None:
        """Handle search input text change with debouncing.

        Args:
            text: New search text
        """
        # Restart debounce timer (300ms delay)
        self._debounce_timer.stop()
        self._debounce_timer.start(300)

    def _emit_search_changed(self) -> None:
        """Emit search changed signal after debounce."""
        query = self.search_input.text()
        self.search_changed.emit(query)

    def _on_filter_mode_changed(self, state: int) -> None:
        """Handle filter mode checkbox change.

        Args:
            state: Checkbox state
        """
        is_filtered = state == Qt.CheckState.Checked.value
        self.filter_mode_changed.emit(is_filtered)

    def set_result_count(self, visible: int, total: int) -> None:
        """Update result count display.

        Args:
            visible: Number of visible (filtered) transactions
            total: Total number of transactions

        Example:
            >>> search_bar.set_result_count(12, 150)
            >>> # Shows "12 of 150 transactions"
        """
        if visible == total:
            # No filter active or all match
            self.result_label.setText(f"{total} transaction{'s' if total != 1 else ''}")
        else:
            # Filter active
            self.result_label.setText(
                f"{visible} of {total} transaction{'s' if total != 1 else ''}"
            )

    def clear(self) -> None:
        """Clear search input."""
        self.search_input.clear()

    def get_query(self) -> str:
        """Get current search query.

        Returns:
            Current query text
        """
        return self.search_input.text()

    def is_filter_mode(self) -> bool:
        """Check if filtered balance mode is enabled.

        Returns:
            True if filtered balance mode is on
        """
        return self.filter_mode_checkbox.isChecked()

    def set_filter_mode(self, enabled: bool) -> None:
        """Set filtered balance mode.

        Args:
            enabled: Whether to enable filtered balance mode
        """
        self.filter_mode_checkbox.setChecked(enabled)
