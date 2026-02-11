"""Supabase Storage attachment service for managing receipt/document files."""

import mimetypes
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from uuid import UUID

import httpx

from fidra.data.repository import AttachmentRepository
from fidra.domain.models import Attachment

if TYPE_CHECKING:
    from fidra.domain.settings import SupabaseSettings
    from fidra.domain.models import Transaction


class SupabaseAttachmentService:
    """Manages file attachments using Supabase Storage.

    Files are uploaded to a Supabase Storage bucket.
    Metadata is stored in the database for quick lookup.
    """

    def __init__(self, attachment_repo: AttachmentRepository, config: "SupabaseSettings"):
        self._repo = attachment_repo
        self._config = config
        self._bucket = config.storage_bucket

    @property
    def storage_url(self) -> str:
        """Get the Supabase Storage API URL."""
        return f"{self._config.project_url}/storage/v1"

    def _get_headers(self) -> dict:
        """Get headers for Supabase Storage API requests."""
        return {
            "Authorization": f"Bearer {self._config.anon_key}",
            "apikey": self._config.anon_key,
        }

    def _generate_stored_name(self, transaction: "Transaction", suffix: str) -> str:
        """Generate a descriptive storage name for the attachment.

        Format: date_type_amount_party.extension
        """
        date_str = transaction.date.isoformat()
        type_str = transaction.type.value
        amount_str = f"{transaction.amount:.2f}"
        party = transaction.party or "unknown"
        party_clean = "".join(c if c.isalnum() else "_" for c in party)[:30]

        return f"{date_str}_{type_str}_{amount_str}_{party_clean}{suffix}"

    async def attach_file(
        self, transaction_id: UUID, source_path: Path, transaction: Optional["Transaction"] = None
    ) -> Attachment:
        """Attach a file to a transaction by uploading to Supabase Storage.

        Args:
            transaction_id: Transaction to attach to
            source_path: Path to the source file
            transaction: Optional transaction for descriptive naming

        Returns:
            Created Attachment record
        """
        suffix = source_path.suffix

        # Generate stored name
        if transaction:
            stored_name = self._generate_stored_name(transaction, suffix)
        else:
            from uuid import uuid4
            stored_name = f"{uuid4().hex}{suffix}"

        # Read file content
        with open(source_path, "rb") as f:
            file_content = f.read()

        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(source_path.name)

        # Upload to Supabase Storage
        upload_url = f"{self.storage_url}/object/{self._bucket}/{stored_name}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                upload_url,
                headers={
                    **self._get_headers(),
                    "Content-Type": mime_type or "application/octet-stream",
                },
                content=file_content,
            )
            response.raise_for_status()

        # Create and save metadata
        attachment = Attachment.create(
            transaction_id=transaction_id,
            filename=source_path.name,
            stored_name=stored_name,
            mime_type=mime_type,
            file_size=len(file_content),
        )

        await self._repo.save(attachment)
        return attachment

    async def get_attachments(self, transaction_id: UUID) -> list[Attachment]:
        """Get all attachments for a transaction."""
        return await self._repo.get_for_transaction(transaction_id)

    async def get_attachment(self, attachment_id: UUID) -> Optional[Attachment]:
        """Get a specific attachment by ID."""
        return await self._repo.get_by_id(attachment_id)

    def get_file_path(self, attachment: Attachment) -> str:
        """Get the public URL for an attachment's stored file.

        Returns a signed URL that can be used to download/view the file.
        """
        return f"{self.storage_url}/object/public/{self._bucket}/{attachment.stored_name}"

    async def get_signed_url(self, attachment: Attachment, expires_in: int = 3600) -> str:
        """Get a signed URL for private bucket access.

        Args:
            attachment: Attachment to get URL for
            expires_in: Expiration time in seconds (default 1 hour)

        Returns:
            Signed URL for downloading the file
        """
        sign_url = f"{self.storage_url}/object/sign/{self._bucket}/{attachment.stored_name}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                sign_url,
                headers=self._get_headers(),
                json={"expiresIn": expires_in},
            )
            response.raise_for_status()
            data = response.json()
            return f"{self._config.project_url}/storage/v1{data['signedURL']}"

    async def download_file(self, attachment: Attachment) -> bytes:
        """Download an attachment file from Supabase Storage.

        Args:
            attachment: Attachment to download

        Returns:
            File content as bytes
        """
        download_url = f"{self.storage_url}/object/{self._bucket}/{attachment.stored_name}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                download_url,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.content

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

        # Delete from Supabase Storage
        delete_url = f"{self.storage_url}/object/{self._bucket}/{attachment.stored_name}"

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                delete_url,
                headers=self._get_headers(),
            )
            # Don't fail if file already deleted
            if response.status_code not in (200, 404):
                response.raise_for_status()

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

        # Delete from Supabase Storage
        async with httpx.AsyncClient() as client:
            for attachment in attachments:
                delete_url = f"{self.storage_url}/object/{self._bucket}/{attachment.stored_name}"
                response = await client.delete(
                    delete_url,
                    headers=self._get_headers(),
                )
                # Don't fail if file already deleted
                if response.status_code not in (200, 404):
                    response.raise_for_status()

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
