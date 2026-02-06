"""Reactive state container with Qt signal integration.

Observable provides a reactive primitive that automatically notifies listeners
when values change, enabling reactive UI updates.
"""

from typing import Callable, Generic, Optional, TypeVar

from PySide6.QtCore import QObject, Signal

T = TypeVar("T")


class Observable(QObject, Generic[T]):
    """Reactive state container with Qt signal integration.

    Observable wraps a value and emits Qt signals when the value changes.
    This enables automatic UI updates when state changes.

    Example:
        >>> counter = Observable(0)
        >>> counter.changed.connect(lambda val: print(f"New value: {val}"))
        >>> counter.set(5)  # Prints: "New value: 5"
    """

    changed = Signal(object)  # Emitted when value changes

    def __init__(self, initial: T, parent: Optional[QObject] = None):
        """Initialize observable with initial value.

        Args:
            initial: Initial value
            parent: Optional Qt parent object
        """
        super().__init__(parent)
        self._value = initial

    @property
    def value(self) -> T:
        """Get current value.

        Returns:
            Current value
        """
        return self._value

    def set(self, new_value: T) -> None:
        """Set new value and emit change signal if different.

        Args:
            new_value: New value to set

        Note:
            Signal is only emitted if new_value != current value
        """
        if new_value != self._value:
            self._value = new_value
            self.changed.emit(new_value)

    def update(self, fn: Callable[[T], T]) -> None:
        """Update value using a function.

        Args:
            fn: Function that takes current value and returns new value

        Example:
            >>> counter = Observable(0)
            >>> counter.update(lambda x: x + 1)
            >>> counter.value  # 1
        """
        self.set(fn(self._value))

    def subscribe(self, callback: Callable[[T], None]) -> None:
        """Subscribe to value changes.

        Args:
            callback: Function called with new value when changed

        Example:
            >>> counter = Observable(0)
            >>> counter.subscribe(lambda val: print(val))
            >>> counter.set(5)  # Prints: 5
        """
        self.changed.connect(callback)

    def emit_changed(self) -> None:
        """Force emit the changed signal with current value.

        This is useful when the underlying data has been mutated in place
        or when you need to trigger a refresh without changing the value.
        """
        self.changed.emit(self._value)
