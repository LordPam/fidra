"""Audit log viewer dialog."""

from typing import TYPE_CHECKING

import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class AuditLogDialog(QDialog):
    """Dialog for viewing the audit trail of all changes."""

    def __init__(self, context: "ApplicationContext", parent=None):
        super().__init__(parent)
        self._context = context

        self.setWindowTitle("Audit Log")
        self.setModal(True)
        self.setMinimumSize(800, 500)
        self.resize(900, 600)

        self._setup_ui()
        self._load_entries()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QLabel("Audit Log")
        header.setObjectName("section_header")
        layout.addWidget(header)

        info = QLabel("A record of all changes made to transactions in this database.")
        info.setObjectName("secondary_text")
        layout.addWidget(info)

        # Filter bar
        filter_layout = QHBoxLayout()

        filter_label = QLabel("Filter:")
        filter_layout.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Changes", "Creates", "Updates", "Deletes"])
        self.filter_combo.currentIndexChanged.connect(lambda _: self._load_entries())
        filter_layout.addWidget(self.filter_combo)

        filter_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_entries)
        filter_layout.addWidget(refresh_btn)

        layout.addLayout(filter_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Time", "Action", "User", "Summary", "Details"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        # Column sizing
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table)

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)

    @qasync.asyncSlot()
    async def _load_entries(self) -> None:
        """Load audit log entries with current filter."""
        if not self._context.audit_service:
            return

        # Determine filter
        filter_map = {
            0: None,       # All
            1: "create",
            2: "update",
            3: "delete",
        }
        action_filter = filter_map.get(self.filter_combo.currentIndex())

        try:
            entries = await self._context.audit_service.get_log(limit=500)

            # Apply action filter client-side
            if action_filter:
                entries = [e for e in entries if e.action.value == action_filter]

            self.table.setRowCount(len(entries))

            for row, entry in enumerate(entries):
                # Time
                time_str = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                time_item = QTableWidgetItem(time_str)
                time_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(row, 0, time_item)

                # Action
                action_item = QTableWidgetItem(entry.action.value.title())
                self.table.setItem(row, 1, action_item)

                # User
                user_item = QTableWidgetItem(entry.user)
                self.table.setItem(row, 2, user_item)

                # Summary
                summary_item = QTableWidgetItem(entry.summary)
                self.table.setItem(row, 3, summary_item)

                # Details (abbreviated)
                details_text = ""
                if entry.details:
                    # Show a brief excerpt
                    details_text = entry.details[:80]
                    if len(entry.details) > 80:
                        details_text += "..."
                details_item = QTableWidgetItem(details_text)
                details_item.setToolTip(entry.details or "")
                self.table.setItem(row, 4, details_item)

        except Exception as e:
            self.table.setRowCount(1)
            error_item = QTableWidgetItem(f"Error loading audit log: {e}")
            self.table.setItem(0, 0, error_item)
