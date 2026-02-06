"""Tests for settings persistence."""

import pytest
from pathlib import Path

from fidra.state.persistence import SettingsStore
from fidra.domain.settings import AppSettings


class TestSettingsStore:
    """Tests for SettingsStore."""

    def test_load_default_when_file_not_exists(self, tmp_path):
        """Load returns default settings when file doesn't exist."""
        store = SettingsStore(tmp_path / "settings.json")
        settings = store.load()

        assert isinstance(settings, AppSettings)
        assert settings.theme.mode == "dark"  # Default

    def test_save_and_load(self, tmp_path):
        """Save and load settings."""
        store = SettingsStore(tmp_path / "settings.json")

        # Create and save settings
        settings = AppSettings()
        settings.theme.mode = "light"
        settings.profile.name = "John Doe"
        store.save(settings)

        # Load and verify
        loaded = store.load()
        assert loaded.theme.mode == "light"
        assert loaded.profile.name == "John Doe"

    def test_save_creates_directory(self, tmp_path):
        """Save creates parent directory if it doesn't exist."""
        nested_path = tmp_path / "nested" / "dir" / "settings.json"
        store = SettingsStore(nested_path)

        settings = AppSettings()
        store.save(settings)

        assert nested_path.exists()

    def test_load_returns_default_on_corrupted_file(self, tmp_path):
        """Load returns default settings if file is corrupted."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text("invalid json {{{")

        store = SettingsStore(settings_path)
        settings = store.load()

        # Should return defaults, not crash
        assert isinstance(settings, AppSettings)
        assert settings.theme.mode == "dark"

    def test_delete_settings(self, tmp_path):
        """Delete removes settings file."""
        settings_path = tmp_path / "settings.json"
        store = SettingsStore(settings_path)

        # Create settings file
        settings = AppSettings()
        store.save(settings)
        assert settings_path.exists()

        # Delete
        deleted = store.delete()
        assert deleted is True
        assert not settings_path.exists()

        # Delete again (file doesn't exist)
        deleted = store.delete()
        assert deleted is False

    def test_default_path(self):
        """Default path is in home directory."""
        store = SettingsStore()
        assert store._path == Path.home() / ".fidra_settings.json"

    def test_json_formatting(self, tmp_path):
        """Saved JSON is pretty-formatted."""
        settings_path = tmp_path / "settings.json"
        store = SettingsStore(settings_path)

        settings = AppSettings()
        store.save(settings)

        # Check that JSON is indented
        content = settings_path.read_text()
        assert "  " in content  # Has indentation
        assert "\n" in content  # Has newlines
