"""Tests for Backup Service."""

import json
import pytest
from datetime import datetime
from pathlib import Path

from fidra.services.backup import BackupService, FIDRA_VERSION
from fidra.domain.settings import BackupSettings
from fidra.domain.models import BackupMetadata


class TestBackupService:
    """Tests for BackupService."""

    @pytest.fixture
    def backup_setup(self, tmp_path):
        """Set up a backup service with a test database."""
        # Create a fake database file
        db_path = tmp_path / "test.db"
        db_path.write_text("test database content")

        # Create settings with default retention
        settings = BackupSettings(retention_count=3)

        # Create service
        service = BackupService(db_path, settings)

        return service, db_path, tmp_path

    def test_backup_dir_default(self, backup_setup):
        """Default backup directory is next to database."""
        service, db_path, tmp_path = backup_setup

        expected = tmp_path / "test_backups"
        assert service.backup_dir == expected

    def test_backup_dir_custom(self, backup_setup, tmp_path):
        """Custom backup directory from settings."""
        service, db_path, _ = backup_setup

        custom_dir = tmp_path / "custom_backups"
        service.settings.backup_dir = custom_dir

        assert service.backup_dir == custom_dir

    def test_create_backup_creates_folder(self, backup_setup):
        """Creating a backup creates a timestamped folder."""
        service, db_path, tmp_path = backup_setup

        backup_path, metadata = service.create_backup(trigger="manual")

        assert backup_path.exists()
        assert backup_path.name.startswith("backup_")
        assert (backup_path / "test.db").exists()
        assert (backup_path / "metadata.json").exists()

    def test_create_backup_copies_database(self, backup_setup):
        """Backup contains a copy of the database file."""
        service, db_path, tmp_path = backup_setup

        backup_path, metadata = service.create_backup()

        backup_db = backup_path / "test.db"
        assert backup_db.exists()
        assert backup_db.read_text() == "test database content"

    def test_create_backup_copies_attachments(self, backup_setup):
        """Backup includes attachments folder if it exists."""
        service, db_path, tmp_path = backup_setup

        # Create attachments folder with a file
        attachments_dir = tmp_path / "test_attachments"
        attachments_dir.mkdir()
        (attachments_dir / "receipt.pdf").write_text("pdf content")

        backup_path, metadata = service.create_backup()

        backup_attachments = backup_path / "test_attachments"
        assert backup_attachments.exists()
        assert (backup_attachments / "receipt.pdf").exists()
        assert metadata.attachments_count == 1

    def test_create_backup_metadata(self, backup_setup):
        """Backup metadata contains correct information."""
        service, db_path, tmp_path = backup_setup

        backup_path, metadata = service.create_backup(trigger="manual")

        assert metadata.db_name == "test.db"
        assert metadata.db_size > 0
        assert metadata.trigger == "manual"
        assert metadata.fidra_version == FIDRA_VERSION
        assert isinstance(metadata.created_at, datetime)

    def test_create_backup_saves_metadata_json(self, backup_setup):
        """Metadata is saved as JSON file."""
        service, db_path, tmp_path = backup_setup

        backup_path, metadata = service.create_backup()

        metadata_path = backup_path / "metadata.json"
        assert metadata_path.exists()

        with open(metadata_path) as f:
            data = json.load(f)

        assert data["db_name"] == "test.db"
        assert data["trigger"] == "manual"

    def test_list_backups_empty(self, backup_setup):
        """List backups returns empty list when no backups exist."""
        service, db_path, tmp_path = backup_setup

        backups = service.list_backups()
        assert backups == []

    def test_list_backups_returns_all(self, backup_setup):
        """List backups returns all created backups."""
        service, db_path, tmp_path = backup_setup

        # Create multiple backups
        service.create_backup()
        service.create_backup()

        backups = service.list_backups()
        assert len(backups) == 2

    def test_list_backups_sorted_newest_first(self, backup_setup):
        """Backups are sorted with newest first."""
        service, db_path, tmp_path = backup_setup

        # Create backups
        path1, meta1 = service.create_backup()
        path2, meta2 = service.create_backup()

        backups = service.list_backups()

        # Second backup should be first (newest)
        assert backups[0][0] == path2
        assert backups[1][0] == path1

    def test_delete_backup(self, backup_setup):
        """Delete removes backup folder."""
        service, db_path, tmp_path = backup_setup

        backup_path, _ = service.create_backup()
        assert backup_path.exists()

        result = service.delete_backup(backup_path)

        assert result is True
        assert not backup_path.exists()

    def test_delete_backup_not_found(self, backup_setup):
        """Delete returns False for non-existent backup."""
        service, db_path, tmp_path = backup_setup

        result = service.delete_backup(tmp_path / "nonexistent")

        assert result is False

    def test_restore_backup(self, backup_setup):
        """Restore replaces database with backup."""
        service, db_path, tmp_path = backup_setup

        # Create backup
        backup_path, _ = service.create_backup()

        # Modify the database
        db_path.write_text("modified content")
        assert db_path.read_text() == "modified content"

        # Restore
        service.restore_backup(backup_path)

        # Database should have original content
        assert db_path.read_text() == "test database content"

    def test_restore_backup_with_attachments(self, backup_setup):
        """Restore replaces attachments folder."""
        service, db_path, tmp_path = backup_setup

        # Create attachments folder with a file
        attachments_dir = tmp_path / "test_attachments"
        attachments_dir.mkdir()
        (attachments_dir / "receipt.pdf").write_text("original receipt")

        # Create backup
        backup_path, _ = service.create_backup()

        # Modify attachments
        (attachments_dir / "receipt.pdf").write_text("modified receipt")
        (attachments_dir / "new_file.pdf").write_text("new file")

        # Restore
        service.restore_backup(backup_path)

        # Attachments should be restored
        assert (attachments_dir / "receipt.pdf").read_text() == "original receipt"
        assert not (attachments_dir / "new_file.pdf").exists()

    def test_restore_backup_not_found(self, backup_setup):
        """Restore raises error for non-existent backup."""
        service, db_path, tmp_path = backup_setup

        with pytest.raises(FileNotFoundError):
            service.restore_backup(tmp_path / "nonexistent")

    def test_retention_enforcement(self, backup_setup):
        """Old backups are deleted beyond retention limit."""
        service, db_path, tmp_path = backup_setup

        # Retention is set to 3
        assert service.settings.retention_count == 3

        # Create 5 backups
        for _ in range(5):
            service.create_backup()

        # Only 3 should remain
        backups = service.list_backups()
        assert len(backups) == 3

    def test_retention_keeps_newest(self, backup_setup):
        """Retention keeps the newest backups."""
        service, db_path, tmp_path = backup_setup

        # Retention is set to 3
        paths = []
        for _ in range(5):
            path, _ = service.create_backup()
            paths.append(path)

        backups = service.list_backups()
        backup_paths = [b[0] for b in backups]

        # Should keep the last 3 created (newest)
        assert paths[-1] in backup_paths
        assert paths[-2] in backup_paths
        assert paths[-3] in backup_paths
        assert paths[0] not in backup_paths
        assert paths[1] not in backup_paths

    def test_get_backup_metadata(self, backup_setup):
        """Get metadata for a specific backup."""
        service, db_path, tmp_path = backup_setup

        backup_path, original_metadata = service.create_backup(trigger="test")

        loaded_metadata = service.get_backup_metadata(backup_path)

        assert loaded_metadata is not None
        assert loaded_metadata.id == original_metadata.id
        assert loaded_metadata.trigger == "test"
        assert loaded_metadata.db_name == "test.db"

    def test_get_backup_metadata_not_found(self, backup_setup):
        """Get metadata returns None for non-existent backup."""
        service, db_path, tmp_path = backup_setup

        result = service.get_backup_metadata(tmp_path / "nonexistent")

        assert result is None

    def test_format_size_bytes(self):
        """Format size shows bytes for small sizes."""
        assert BackupService.format_size(100) == "100 B"
        assert BackupService.format_size(1023) == "1023 B"

    def test_format_size_kilobytes(self):
        """Format size shows KB for medium sizes."""
        assert BackupService.format_size(1024) == "1.0 KB"
        assert BackupService.format_size(10240) == "10.0 KB"

    def test_format_size_megabytes(self):
        """Format size shows MB for large sizes."""
        assert BackupService.format_size(1024 * 1024) == "1.0 MB"
        assert BackupService.format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_auto_close_trigger(self, backup_setup):
        """Backup with auto_close trigger is recorded correctly."""
        service, db_path, tmp_path = backup_setup

        backup_path, metadata = service.create_backup(trigger="auto_close")

        assert metadata.trigger == "auto_close"

    def test_pre_restore_trigger(self, backup_setup):
        """Backup with pre_restore trigger is recorded correctly."""
        service, db_path, tmp_path = backup_setup

        backup_path, metadata = service.create_backup(trigger="pre_restore")

        assert metadata.trigger == "pre_restore"

    def test_db_path_property(self, backup_setup):
        """Database path can be updated."""
        service, db_path, tmp_path = backup_setup

        new_path = tmp_path / "new.db"
        new_path.write_text("new db content")

        service.db_path = new_path

        assert service.db_path == new_path


class TestBackupMetadata:
    """Tests for BackupMetadata dataclass."""

    def test_create_metadata(self):
        """Create metadata with factory method."""
        metadata = BackupMetadata.create(
            db_name="test.db",
            db_size=1024,
            attachments_count=5,
            attachments_size=2048,
            trigger="manual",
            fidra_version="2.0.0",
        )

        assert metadata.db_name == "test.db"
        assert metadata.db_size == 1024
        assert metadata.attachments_count == 5
        assert metadata.attachments_size == 2048
        assert metadata.trigger == "manual"
        assert metadata.fidra_version == "2.0.0"
        assert metadata.id is not None
        assert isinstance(metadata.created_at, datetime)

    def test_metadata_is_frozen(self):
        """Metadata is immutable."""
        metadata = BackupMetadata.create(
            db_name="test.db",
            db_size=1024,
            attachments_count=0,
            attachments_size=0,
            trigger="manual",
            fidra_version="2.0.0",
        )

        with pytest.raises(AttributeError):
            metadata.db_name = "changed.db"
