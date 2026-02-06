"""Settings persistence to JSON file."""

import json
from pathlib import Path
from typing import Optional

from fidra.domain.settings import AppSettings


class SettingsStore:
    """Persists settings to JSON file.

    Settings are stored in the user's home directory by default.

    Example:
        >>> store = SettingsStore()
        >>> settings = store.load()
        >>> settings.theme.mode = "light"
        >>> store.save(settings)
    """

    DEFAULT_PATH = Path.home() / ".fidra_settings.json"

    def __init__(self, path: Optional[Path] = None):
        """Initialize settings store.

        Args:
            path: Optional custom path for settings file.
                  Defaults to ~/.fidra_settings.json
        """
        self._path = path or self.DEFAULT_PATH

    def exists(self) -> bool:
        """Check if settings file exists (indicates not first run)."""
        return self._path.exists()

    def load(self) -> AppSettings:
        """Load settings from file.

        Returns:
            AppSettings instance. If file doesn't exist or is invalid,
            returns default settings.

        Example:
            >>> store = SettingsStore()
            >>> settings = store.load()
            >>> print(settings.theme.mode)  # "dark"
        """
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                return AppSettings.model_validate(data)
            except Exception as e:
                # If settings file is corrupted, return defaults
                print(f"Warning: Could not load settings: {e}")
                return AppSettings()
        return AppSettings()

    def save(self, settings: AppSettings) -> None:
        """Save settings to file.

        Args:
            settings: AppSettings to save

        Example:
            >>> store = SettingsStore()
            >>> settings = AppSettings()
            >>> settings.theme.mode = "light"
            >>> store.save(settings)
        """
        # Ensure parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Write with pretty formatting
        self._path.write_text(settings.model_dump_json(indent=2))

    def delete(self) -> bool:
        """Delete settings file.

        Returns:
            True if file was deleted, False if it didn't exist
        """
        if self._path.exists():
            self._path.unlink()
            return True
        return False
