"""Attachment service for managing receipt/document files linked to transactions."""

import mimetypes
import re
import shutil
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from fidra.data.repository import AttachmentRepository
from fidra.domain.models import Attachment

if TYPE_CHECKING:
    from fidra.domain.models import Transaction


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
        self,
        transaction_id: UUID,
        source_path: Path,
        transaction: Optional["Transaction"] = None,
    ) -> Attachment:
        """Attach a file to a transaction.

        Copies the file into the managed storage directory and creates
        a database record linking it to the transaction.

        Args:
            transaction_id: Transaction to attach to
            source_path: Path to the source file
            transaction: Optional transaction for descriptive file naming

        Returns:
            Created Attachment record
        """
        self._ensure_storage()

        # Generate stored name - descriptive if transaction provided, UUID otherwise
        suffix = source_path.suffix
        if transaction:
            stored_name = self._generate_descriptive_name(transaction, suffix)
        else:
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

    def _generate_descriptive_name(self, transaction: "Transaction", suffix: str) -> str:
        """Generate a descriptive filename for an attachment.

        Format: date_type_amount_party.extension (party in camelCase)
        Example: 2026-02-10_expense_25.50_johnSmith.pdf

        Args:
            transaction: Transaction to generate name from
            suffix: File extension (e.g., '.pdf')

        Returns:
            Descriptive filename
        """
        # Date in ISO format
        date_str = transaction.date.isoformat()

        # Transaction type
        type_str = transaction.type.value  # 'income' or 'expense'

        # Amount (formatted without currency symbol)
        amount_str = f"{transaction.amount:.2f}"

        # Party in camelCase (or 'unknown' if not set)
        party = transaction.party or "unknown"
        party_camel = self._to_camel_case(party)

        # Base name
        base_name = f"{date_str}_{type_str}_{amount_str}_{party_camel}"

        # Ensure uniqueness by adding index if file exists
        stored_name = f"{base_name}{suffix}"
        index = 1
        while (self._storage_dir / stored_name).exists():
            stored_name = f"{base_name}_{index}{suffix}"
            index += 1

        return stored_name

    def _to_camel_case(self, text: str) -> str:
        """Convert text to camelCase.

        Args:
            text: Input text (e.g., 'John Smith', 'john-smith', 'ACME Corp')

        Returns:
            camelCase version (e.g., 'johnSmith', 'acmeCorp')
        """
        # Remove special characters and split into words
        words = re.split(r'[\s\-_\.]+', text.strip())

        if not words:
            return "unknown"

        # First word lowercase, rest title case
        result = []
        for i, word in enumerate(words):
            if not word:
                continue
            if i == 0:
                result.append(word.lower())
            else:
                result.append(word.capitalize())

        return ''.join(result) or "unknown"

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
