"""Tree model for planned transaction templates and their instances."""

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from fidra.domain.models import PlannedTemplate, Transaction

if TYPE_CHECKING:
    from fidra.app import ApplicationContext


class TreeItem:
    """Item in the planned transaction tree.

    Can be either a template (parent) or an instance (child).
    """

    def __init__(self, data: dict[str, Any], parent: Optional["TreeItem"] = None):
        """Initialize tree item.

        Args:
            data: Item data (template or instance info)
            parent: Parent item (None for root items)
        """
        self.data = data
        self.parent = parent
        self.children: list["TreeItem"] = []

    def append_child(self, child: "TreeItem") -> None:
        """Add a child item.

        Args:
            child: Child item to add
        """
        self.children.append(child)

    def child(self, row: int) -> Optional["TreeItem"]:
        """Get child at row.

        Args:
            row: Row index

        Returns:
            Child item or None if row is out of bounds
        """
        if 0 <= row < len(self.children):
            return self.children[row]
        return None

    def child_count(self) -> int:
        """Get number of children.

        Returns:
            Number of child items
        """
        return len(self.children)

    def row(self) -> int:
        """Get row index in parent.

        Returns:
            Row index, or 0 if no parent
        """
        if self.parent:
            return self.parent.children.index(self)
        return 0


class PlannedTreeModel(QAbstractItemModel):
    """Tree model for planned templates with expandable instances.

    Structure:
    - Root (invisible)
      - Template 1 (shows description, amount, sheet, frequency)
        - Instance 1 (shows date, amount)
        - Instance 2
        - ...
      - Template 2
        - Instance 1
        - ...

    Column indices:
    - 0: Description
    - 1: Amount
    - 2: Sheet (conditionally shown when 2+ sheets)
    - 3: Frequency/Type
    - 4: Next Due/Status
    """

    # Column indices
    COL_DESCRIPTION = 0
    COL_AMOUNT = 1
    COL_SHEET = 2
    COL_FREQUENCY = 3
    COL_NEXT_DUE = 4

    def __init__(self, context: "ApplicationContext", parent=None):
        """Initialize the tree model.

        Args:
            context: Application context
            parent: Parent Qt object
        """
        super().__init__(parent)
        self._context = context
        self._root_item = TreeItem({"type": "root"})
        self._show_sheet_column = False  # Controlled by PlannedView
        self._build_tree()

        # Connect to state changes
        self._context.state.planned_templates.changed.connect(self._on_templates_changed)

    def _build_tree(self) -> None:
        """Build the tree structure from templates."""
        self.beginResetModel()

        # Clear existing tree
        self._root_item = TreeItem({"type": "root"})

        # Get templates from state
        templates = self._context.state.planned_templates.value

        # Calculate horizon (90 days by default from settings)
        horizon = date.today() + timedelta(days=self._context.settings.forecast.horizon_days)

        # Build tree: templates as parents, instances as children
        for template in templates:
            # Create template item
            template_data = {
                "type": "template",
                "template": template,
                "is_template": True,
                "is_instance": False,
            }
            template_item = TreeItem(template_data, self._root_item)
            self._root_item.append_child(template_item)

            # Expand template to instances
            instances = self._context.forecast_service.expand_template(
                template,
                horizon,
                include_past=False  # Only show future instances
            )

            # Add instances as children
            for instance in instances:
                instance_data = {
                    "type": "instance",
                    "template": template,
                    "instance": instance,
                    "is_template": False,
                    "is_instance": True,
                }
                instance_item = TreeItem(instance_data, template_item)
                template_item.append_child(instance_item)

        self.endResetModel()

    def _on_templates_changed(self, templates: list[PlannedTemplate]) -> None:
        """Handle template list changes.

        Args:
            templates: Updated template list
        """
        self._build_tree()

    def refresh(self) -> None:
        """Force refresh of the tree."""
        self._build_tree()

    # QAbstractItemModel interface

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        """Create model index for row/column under parent.

        Args:
            row: Row index
            column: Column index
            parent: Parent model index

        Returns:
            Model index for the item
        """
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        """Get parent model index.

        Args:
            index: Child model index

        Returns:
            Parent model index
        """
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent

        if parent_item == self._root_item or parent_item is None:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Get number of rows under parent.

        Args:
            parent: Parent model index

        Returns:
            Number of child rows
        """
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()

        return parent_item.child_count()

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Get number of columns.

        Args:
            parent: Parent model index (unused)

        Returns:
            Number of columns (5: Description, Amount, Sheet, Frequency, Next Due)
        """
        return 5

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Get data for model index and role.

        Args:
            index: Model index
            role: Data role

        Returns:
            Data for the given role
        """
        if not index.isValid():
            return None

        item = index.internalPointer()
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            item_type = item.data.get("type")

            if item_type == "template":
                template = item.data["template"]
                if column == self.COL_DESCRIPTION:  # Description
                    return template.description
                elif column == self.COL_AMOUNT:  # Amount
                    return f"£{template.amount:.2f}"
                elif column == self.COL_SHEET:  # Sheet
                    return template.target_sheet
                elif column == self.COL_FREQUENCY:  # Frequency
                    return template.frequency.value.capitalize()
                elif column == self.COL_NEXT_DUE:  # Next Due
                    # Show start date if in future, otherwise first child instance date
                    if template.start_date >= date.today():
                        return template.start_date.strftime("%Y-%m-%d")
                    elif item.child_count() > 0:
                        first_child = item.child(0)
                        if first_child:
                            instance = first_child.data.get("instance")
                            if instance:
                                return instance.date.strftime("%Y-%m-%d")
                    return "N/A"

            elif item_type == "instance":
                instance = item.data["instance"]
                if column == self.COL_DESCRIPTION:  # Description (indent)
                    return f"  → {instance.date.strftime('%Y-%m-%d')}"
                elif column == self.COL_AMOUNT:  # Amount
                    return f"£{instance.amount:.2f}"
                elif column == self.COL_SHEET:  # Sheet (same as parent template)
                    return instance.sheet
                elif column == self.COL_FREQUENCY:  # Type
                    return instance.type.value.capitalize()
                elif column == self.COL_NEXT_DUE:  # Status
                    return "PLANNED"

        elif role == Qt.ItemDataRole.ForegroundRole:
            # Amber/orange text for overdue template rows
            if item.data.get("is_template"):
                template = item.data["template"]
                if template.start_date < date.today():
                    from fidra.ui.theme.engine import get_theme_engine, Theme
                    engine = get_theme_engine()
                    if engine.current_theme == Theme.DARK:
                        return QColor(251, 191, 36)   # warm gold
                    else:
                        return QColor(217, 119, 6)    # amber/orange

        elif role == Qt.ItemDataRole.FontRole:
            # Italic for overdue template rows
            if item.data.get("is_template"):
                template = item.data["template"]
                if template.start_date < date.today():
                    font = QFont()
                    font.setItalic(True)
                    return font

        elif role == Qt.ItemDataRole.UserRole:
            # Return the full item data for access by views
            return item.data

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Get header data.

        Args:
            section: Section index
            orientation: Horizontal or vertical
            role: Data role

        Returns:
            Header label
        """
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            headers = ["Description", "Amount", "Sheet", "Frequency/Type", "Next Due/Status"]
            if 0 <= section < len(headers):
                return headers[section]
        return None

    def item_at(self, index: QModelIndex) -> Optional[dict[str, Any]]:
        """Get item data at model index.

        Args:
            index: Model index

        Returns:
            Item data dictionary
        """
        if not index.isValid():
            return None
        item = index.internalPointer()
        return item.data
