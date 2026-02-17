"""Cloud storage attachment service for managing receipt/document files.

Supports pluggable storage providers (Supabase Storage, S3, etc.)
"""

import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from uuid import UUID

import httpx

from fidra.data.repository import AttachmentRepository
from fidra.domain.models import Attachment

if TYPE_CHECKING:
    from fidra.domain.settings import CloudStorageProvider
    from fidra.domain.models import Transaction


class CloudAttachmentService(ABC):
    """Abstract base class for cloud attachment storage.

    Implementations handle file storage via different providers.
    """

    def __init__(self, attachment_repo: AttachmentRepository):
        self._repo = attachment_repo

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

    @abstractmethod
    async def attach_file(
        self, transaction_id: UUID, source_path: Path, transaction: Optional["Transaction"] = None
    ) -> Attachment:
        """Attach a file to a transaction by uploading to cloud storage."""
        pass

    async def get_attachments(self, transaction_id: UUID) -> list[Attachment]:
        """Get all attachments for a transaction."""
        return await self._repo.get_for_transaction(transaction_id)

    async def get_attachment(self, attachment_id: UUID) -> Optional[Attachment]:
        """Get a specific attachment by ID."""
        return await self._repo.get_by_id(attachment_id)

    @abstractmethod
    def get_file_path(self, attachment: Attachment) -> str:
        """Get the public URL for an attachment's stored file."""
        pass

    @abstractmethod
    async def download_file(self, attachment: Attachment) -> bytes:
        """Download an attachment file from cloud storage."""
        pass

    @abstractmethod
    async def remove_attachment(self, attachment_id: UUID) -> bool:
        """Remove an attachment (both file and database record)."""
        pass

    @abstractmethod
    async def remove_all_for_transaction(self, transaction_id: UUID) -> int:
        """Remove all attachments for a transaction."""
        pass

    def format_file_size(self, size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"


class SupabaseStorageProvider(CloudAttachmentService):
    """Supabase Storage implementation for cloud attachments.

    Files are uploaded to a Supabase Storage bucket.
    Metadata is stored in the database for quick lookup.
    """

    def __init__(self, attachment_repo: AttachmentRepository, config: "CloudStorageProvider"):
        super().__init__(attachment_repo)
        self._config = config
        self._bucket = config.bucket

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
        from urllib.parse import quote
        # Don't encode safe filename characters (hyphen, underscore, period)
        encoded_name = quote(stored_name, safe='-_.')
        upload_url = f"{self.storage_url}/object/{self._bucket}/{encoded_name}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                upload_url,
                headers={
                    **self._get_headers(),
                    "Content-Type": mime_type or "application/octet-stream",
                    "x-upsert": "true",  # Allow overwriting existing files
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

    def get_file_path(self, attachment: Attachment) -> str:
        """Get the public URL for an attachment's stored file."""
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
        from urllib.parse import quote

        # URL-encode the filename and use authenticated endpoint for private buckets
        encoded_name = quote(attachment.stored_name, safe='-_.')
        download_url = f"{self.storage_url}/object/authenticated/{self._bucket}/{encoded_name}"

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
        from urllib.parse import quote
        encoded_name = quote(attachment.stored_name, safe='-_.')
        delete_url = f"{self.storage_url}/object/{self._bucket}/{encoded_name}"

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                delete_url,
                headers=self._get_headers(),
            )
            # Don't fail if file doesn't exist (404) or request fails (400)
            # 400 can happen for orphaned records where file was never uploaded
            if response.status_code not in (200, 400, 404):
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
        from urllib.parse import quote
        async with httpx.AsyncClient() as client:
            for attachment in attachments:
                encoded_name = quote(attachment.stored_name, safe='-_.')
                delete_url = f"{self.storage_url}/object/{self._bucket}/{encoded_name}"
                response = await client.delete(
                    delete_url,
                    headers=self._get_headers(),
                )
                # Don't fail if file doesn't exist (404) or request fails (400)
                # 400 can happen for orphaned records where file was never uploaded
                if response.status_code not in (200, 400, 404):
                    response.raise_for_status()

        # Delete database records
        return await self._repo.delete_for_transaction(transaction_id)


def create_cloud_attachment_service(
    attachment_repo: AttachmentRepository,
    storage_config: "CloudStorageProvider",
) -> CloudAttachmentService:
    """Factory function to create the appropriate cloud attachment service.

    Args:
        attachment_repo: Repository for attachment metadata
        storage_config: Cloud storage provider configuration

    Returns:
        Configured CloudAttachmentService instance
    """
    if storage_config.provider == "supabase":
        return SupabaseStorageProvider(attachment_repo, storage_config)
    # Future providers can be added here:
    # elif storage_config.provider == "s3":
    #     return S3StorageProvider(attachment_repo, storage_config)
    else:
        raise ValueError(f"Unknown storage provider: {storage_config.provider}")
