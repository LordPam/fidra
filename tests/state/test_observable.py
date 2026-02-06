"""Tests for Observable reactive state container."""

import pytest
from fidra.state.observable import Observable


class TestObservable:
    """Tests for Observable."""

    def test_initial_value(self):
        """Observable stores initial value."""
        obs = Observable(42)
        assert obs.value == 42

    def test_set_value(self):
        """Setting value updates the observable."""
        obs = Observable(0)
        obs.set(10)
        assert obs.value == 10

    def test_signal_emitted_on_change(self, qtbot):
        """Signal is emitted when value changes."""
        obs = Observable(0)

        # Track signal emissions
        received = []
        obs.changed.connect(lambda val: received.append(val))

        obs.set(5)
        assert received == [5]

        obs.set(10)
        assert received == [5, 10]

    def test_signal_not_emitted_for_same_value(self, qtbot):
        """Signal is NOT emitted when setting to same value."""
        obs = Observable(5)

        received = []
        obs.changed.connect(lambda val: received.append(val))

        obs.set(5)  # Same value
        assert received == []  # No emission

    def test_update_with_function(self):
        """Update method applies function to current value."""
        obs = Observable(10)
        obs.update(lambda x: x + 5)
        assert obs.value == 15

        obs.update(lambda x: x * 2)
        assert obs.value == 30

    def test_subscribe(self, qtbot):
        """Subscribe method connects callback."""
        obs = Observable(0)

        results = []
        obs.subscribe(lambda val: results.append(val))

        obs.set(1)
        obs.set(2)
        obs.set(3)

        assert results == [1, 2, 3]

    def test_observable_with_list(self):
        """Observable works with list values."""
        obs = Observable([1, 2, 3])
        assert obs.value == [1, 2, 3]

        obs.set([4, 5, 6])
        assert obs.value == [4, 5, 6]

    def test_observable_with_dict(self):
        """Observable works with dict values."""
        obs = Observable({"a": 1})
        assert obs.value == {"a": 1}

        obs.set({"b": 2})
        assert obs.value == {"b": 2}
