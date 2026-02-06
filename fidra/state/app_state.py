"""Central application state.

AppState holds all application-level state using Observable containers.
This enables reactive UI updates and centralized state management.
"""

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from fidra.domain.models import PlannedTemplate, Sheet, Transaction
from fidra.state.observable import Observable


@dataclass
class AppState:
    """Central application state.

    All state is stored in Observable containers that emit signals
    when values change. This enables automatic UI updates.

    Example:
        >>> state = AppState()
        >>> state.transactions.subscribe(lambda txns: print(f"Count: {len(txns)}"))
        >>> state.transactions.set([transaction1, transaction2])
        # Prints: "Count: 2"
    """

    # Data state
    transactions: Observable[list[Transaction]] = field(
        default_factory=lambda: Observable([])
    )
    planned_templates: Observable[list[PlannedTemplate]] = field(
        default_factory=lambda: Observable([])
    )
    sheets: Observable[list[Sheet]] = field(default_factory=lambda: Observable([]))

    # UI state
    current_sheet: Observable[str] = field(
        default_factory=lambda: Observable("All Sheets")
    )
    selected_ids: Observable[set[UUID]] = field(default_factory=lambda: Observable(set()))
    search_query: Observable[str] = field(default_factory=lambda: Observable(""))
    include_planned: Observable[bool] = field(default_factory=lambda: Observable(True))
    filtered_balance_mode: Observable[bool] = field(
        default_factory=lambda: Observable(False)
    )

    # Loading/error state
    is_loading: Observable[bool] = field(default_factory=lambda: Observable(False))
    error_message: Observable[Optional[str]] = field(
        default_factory=lambda: Observable(None)
    )

    def clear_selection(self) -> None:
        """Clear selected transaction IDs."""
        self.selected_ids.set(set())

    def set_loading(self, loading: bool) -> None:
        """Set loading state.

        Args:
            loading: True if loading, False otherwise
        """
        self.is_loading.set(loading)

    def set_error(self, message: Optional[str]) -> None:
        """Set error message.

        Args:
            message: Error message, or None to clear
        """
        self.error_message.set(message)

    def clear_error(self) -> None:
        """Clear error message."""
        self.error_message.set(None)
