"""Attachment service for managing receipt/document files linked to transactions."""

import mimetypes
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fidra.data.repository import AttachmentRepository
from fidra.domain.models import Attachment


class AttachmentService:
    """Manages file attachments (receipts, invoices) for transactions.

    Files are stored in an 'attachments' directory next to the database file.
    Metadata is stored in the database for quick lookup.
    """

    def __init__(self, attachment_repo: AttachmentRepository, db_path: Path):
        self._repo = attachment_repo
        self._storage_dir = db_path.parent / f"{db_path.stem}_attachments"

    @property
    def storage_dir(self) -> Path:
        return self._storage_dir

    def _ensure_storage(self) -> None:
        """Create storage directory if it doesn't exist."""
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    async def attach_file(
        self, transaction_id: UUID, source_path: Path
    ) -> Attachment:
        """Attach a file to a transaction.

        Copies the file into the managed storage directory and creates
        a database record linking it to the transaction.

        Args:
            transaction_id: Transaction to attach to
            source_path: Path to the source file

        Returns:
            Created Attachment record
        """
        self._ensure_storage()

        # Generate a unique stored name to avoid conflicts
        suffix = source_path.suffix
        stored_name = f"{uuid4().hex}{suffix}"
        dest_path = self._storage_dir / stored_name

        # Copy file to storage
        shutil.copy2(source_path, dest_path)

        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(source_path.name)

        # Get file size
        file_size = dest_path.stat().st_size

        # Create and save metadata
        attachment = Attachment.create(
            transaction_id=transaction_id,
            filename=source_path.name,
            stored_name=stored_name,
            mime_type=mime_type,
            file_size=file_size,
        )

        await self._repo.save(attachment)
        return attachment

    async def get_attachments(self, transaction_id: UUID) -> list[Attachment]:
        """Get all attachments for a transaction."""
        return await self._repo.get_for_transaction(transaction_id)

    async def get_attachment(self, attachment_id: UUID) -> Optional[Attachment]:
        """Get a specific attachment by ID."""
        return await self._repo.get_by_id(attachment_id)

    def get_file_path(self, attachment: Attachment) -> Path:
        """Get the full filesystem path for an attachment's stored file."""
        return self._storage_dir / attachment.stored_name

    async def remove_attachment(self, attachment_id: UUID) -> bool:
        """Remove an attachment (both file and database record).

        Args:
            attachment_id: Attachment to remove

        Returns:
            True if removed, False if not found
        """
        attachment = await self._repo.get_by_id(attachment_id)
        if not attachment:
            return False

        # Delete the physical file
        file_path = self._storage_dir / attachment.stored_name
        if file_path.exists():
            file_path.unlink()

        # Delete the database record
        return await self._repo.delete(attachment_id)

    async def remove_all_for_transaction(self, transaction_id: UUID) -> int:
        """Remove all attachments for a transaction.

        Args:
            transaction_id: Transaction whose attachments to remove

        Returns:
            Number of attachments removed
        """
        attachments = await self._repo.get_for_transaction(transaction_id)

        # Delete physical files
        for attachment in attachments:
            file_path = self._storage_dir / attachment.stored_name
            if file_path.exists():
                file_path.unlink()

        # Delete database records
        return await self._repo.delete_for_transaction(transaction_id)

    def format_file_size(self, size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
