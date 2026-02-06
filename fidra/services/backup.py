"""Backup service for creating and restoring database backups."""

import json
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from fidra.domain.models import BackupMetadata
from fidra.domain.settings import BackupSettings

# Fidra version - should match pyproject.toml
FIDRA_VERSION = "2.0.0"


class BackupService:
    """Manages database and attachments backups.

    Backups are stored in a configurable directory with the structure:
        fidra_backups/
          backup_20260206_143022/
            fidra.db
            fidra_attachments/
            metadata.json
    """

    def __init__(self, db_path: Path, settings: BackupSettings):
        """Initialize backup service.

        Args:
            db_path: Path to the current database file
            settings: Backup configuration settings
        """
        self._db_path = db_path
        self._settings = settings

    @property
    def db_path(self) -> Path:
        """Get current database path."""
        return self._db_path

    @db_path.setter
    def db_path(self, value: Path) -> None:
        """Set database path (used when switching databases)."""
        self._db_path = value

    @property
    def settings(self) -> BackupSettings:
        """Get backup settings."""
        return self._settings

    @settings.setter
    def settings(self, value: BackupSettings) -> None:
        """Set backup settings."""
        self._settings = value

    @property
    def backup_dir(self) -> Path:
        """Get the backup directory.

        Returns configured backup_dir or default (next to database).
        """
        if self._settings.backup_dir:
            return self._settings.backup_dir
        return self._db_path.parent / f"{self._db_path.stem}_backups"

    @property
    def attachments_dir(self) -> Path:
        """Get the attachments directory for the current database."""
        return self._db_path.parent / f"{self._db_path.stem}_attachments"

    def _ensure_backup_dir(self) -> None:
        """Create backup directory if it doesn't exist."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, trigger: str = "manual") -> tuple[Path, BackupMetadata]:
        """Create a backup of the database and attachments.

        Args:
            trigger: What triggered the backup ("manual", "auto_close", "pre_restore")

        Returns:
            Tuple of (backup_path, metadata)
        """
        self._ensure_backup_dir()

        # Generate timestamp-based folder name (with microseconds to avoid collisions)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_folder = self.backup_dir / f"backup_{timestamp}"
        backup_folder.mkdir(parents=True, exist_ok=True)

        # Copy database file
        db_backup_path = backup_folder / self._db_path.name
        shutil.copy2(self._db_path, db_backup_path)
        db_size = db_backup_path.stat().st_size

        # Copy attachments folder if it exists
        attachments_count = 0
        attachments_size = 0
        if self.attachments_dir.exists():
            attachments_backup_path = backup_folder / self.attachments_dir.name
            shutil.copytree(self.attachments_dir, attachments_backup_path)
            # Count files and total size
            for file in attachments_backup_path.rglob("*"):
                if file.is_file():
                    attachments_count += 1
                    attachments_size += file.stat().st_size

        # Create metadata
        metadata = BackupMetadata.create(
            db_name=self._db_path.name,
            db_size=db_size,
            attachments_count=attachments_count,
            attachments_size=attachments_size,
            trigger=trigger,
            fidra_version=FIDRA_VERSION,
        )

        # Save metadata to JSON
        metadata_path = backup_folder / "metadata.json"
        metadata_dict = asdict(metadata)
        # Convert UUID and datetime to strings for JSON serialization
        metadata_dict["id"] = str(metadata_dict["id"])
        metadata_dict["created_at"] = metadata_dict["created_at"].isoformat()
        with open(metadata_path, "w") as f:
            json.dump(metadata_dict, f, indent=2)

        # Enforce retention policy
        self._enforce_retention()

        return backup_folder, metadata

    def list_backups(self) -> list[tuple[Path, BackupMetadata]]:
        """List all available backups, sorted by newest first.

        Returns:
            List of (backup_path, metadata) tuples
        """
        if not self.backup_dir.exists():
            return []

        backups = []
        for folder in self.backup_dir.iterdir():
            if folder.is_dir() and folder.name.startswith("backup_"):
                metadata_path = folder / "metadata.json"
                if metadata_path.exists():
                    try:
                        metadata = self._load_metadata(metadata_path)
                        backups.append((folder, metadata))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        # Skip invalid backups
                        continue

        # Sort by creation time, newest first
        backups.sort(key=lambda x: x[1].created_at, reverse=True)
        return backups

    def _load_metadata(self, metadata_path: Path) -> BackupMetadata:
        """Load metadata from a JSON file.

        Args:
            metadata_path: Path to metadata.json

        Returns:
            BackupMetadata instance
        """
        with open(metadata_path) as f:
            data = json.load(f)

        return BackupMetadata(
            id=UUID(data["id"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            db_name=data["db_name"],
            db_size=data["db_size"],
            attachments_count=data["attachments_count"],
            attachments_size=data["attachments_size"],
            trigger=data["trigger"],
            fidra_version=data["fidra_version"],
        )

    def restore_backup(self, backup_path: Path) -> None:
        """Restore database and attachments from a backup.

        IMPORTANT: The database connection must be closed before calling this.

        Args:
            backup_path: Path to the backup folder
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        # Find the database file in the backup
        db_files = list(backup_path.glob("*.db"))
        if not db_files:
            raise ValueError(f"No database file found in backup: {backup_path}")
        backup_db = db_files[0]

        # Copy database file over current
        shutil.copy2(backup_db, self._db_path)

        # Restore attachments if they exist in backup
        backup_attachments = backup_path / self.attachments_dir.name
        if backup_attachments.exists():
            # Remove current attachments
            if self.attachments_dir.exists():
                shutil.rmtree(self.attachments_dir)
            # Copy backup attachments
            shutil.copytree(backup_attachments, self.attachments_dir)
        elif self.attachments_dir.exists():
            # Backup had no attachments - remove current ones
            shutil.rmtree(self.attachments_dir)

    def delete_backup(self, backup_path: Path) -> bool:
        """Delete a backup folder.

        Args:
            backup_path: Path to the backup folder

        Returns:
            True if deleted, False if not found
        """
        if not backup_path.exists():
            return False

        shutil.rmtree(backup_path)
        return True

    def _enforce_retention(self) -> None:
        """Delete old backups beyond the retention limit."""
        backups = self.list_backups()
        retention_count = self._settings.retention_count

        if len(backups) > retention_count:
            # Delete oldest backups beyond retention limit
            for backup_path, _ in backups[retention_count:]:
                self.delete_backup(backup_path)

    def get_backup_metadata(self, backup_path: Path) -> Optional[BackupMetadata]:
        """Get metadata for a specific backup.

        Args:
            backup_path: Path to the backup folder

        Returns:
            BackupMetadata or None if not found/invalid
        """
        metadata_path = backup_path / "metadata.json"
        if not metadata_path.exists():
            return None

        try:
            return self._load_metadata(metadata_path)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format file size for display.

        Args:
            size_bytes: Size in bytes

        Returns:
            Human-readable size string
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
