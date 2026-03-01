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

    @property
    def path(self) -> Path:
        """Get the settings file path."""
        return self._path

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
                # Migrate old settings formats
                data = self._migrate_settings(data)
                return AppSettings.model_validate(data)
            except Exception as e:
                # If settings file is corrupted, return defaults
                print(f"Warning: Could not load settings: {e}")
                return AppSettings()
        return AppSettings()

    def _migrate_settings(self, data: dict) -> dict:
        """Migrate old settings formats to current format.

        Args:
            data: Raw settings dictionary

        Returns:
            Migrated settings dictionary
        """
        storage = data.get("storage", {})

        # Migrate "supabase" backend to "cloud"
        if storage.get("backend") == "supabase":
            storage["backend"] = "cloud"

            # Migrate old supabase settings to cloud_servers list
            old_supabase = storage.get("supabase", {})
            if old_supabase and old_supabase.get("db_connection_string"):
                from uuid import uuid4
                from datetime import datetime

                # Create a cloud server config from old supabase settings
                server_config = {
                    "id": uuid4().hex,
                    "name": old_supabase.get("project_name") or "Supabase Server",
                    "db_connection_string": old_supabase.get("db_connection_string"),
                    "pool_min_size": old_supabase.get("pool_min_size", 2),
                    "pool_max_size": old_supabase.get("pool_max_size", 10),
                    "created_at": datetime.now().isoformat(),
                    "storage": {
                        "provider": "supabase",
                        "project_url": old_supabase.get("project_url"),
                        "anon_key": old_supabase.get("anon_key"),
                        "bucket": old_supabase.get("storage_bucket", "attachments"),
                    },
                }

                # Add to cloud_servers list
                if "cloud_servers" not in storage:
                    storage["cloud_servers"] = []
                storage["cloud_servers"].append(server_config)
                storage["active_server_id"] = server_config["id"]

            # Remove old supabase key
            storage.pop("supabase", None)

        data["storage"] = storage

        # Migrate conflict strategy: last_write_wins → ask_user
        sync = data.get("sync", {})
        if sync.get("conflict_strategy") == "last_write_wins":
            sync["conflict_strategy"] = "ask_user"
            data["sync"] = sync

        # Remove activity_notes (moved from settings to database)
        data.pop("activity_notes", None)

        return data

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
