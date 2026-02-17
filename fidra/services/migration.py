"""Data migration service for transferring data between SQLite and cloud backends."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

import httpx

from fidra.data.repository import (
    AttachmentRepository,
    AuditRepository,
    PlannedRepository,
    SheetRepository,
    TransactionRepository,
)
from fidra.domain.models import (
    Attachment,
    AuditEntry,
    PlannedTemplate,
    Sheet,
    Transaction,
)

if TYPE_CHECKING:
    from fidra.domain.settings import CloudStorageProvider


@dataclass
class MigrationProgress:
    """Progress update for migration operations."""

    phase: str  # e.g., "transactions", "attachments"
    current: int
    total: int
    message: str


@dataclass
class MigrationResult:
    """Result of a migration operation."""

    success: bool
    transactions_migrated: int
    planned_templates_migrated: int
    sheets_migrated: int
    attachments_migrated: int
    audit_entries_migrated: int
    errors: list[str]


ProgressCallback = Callable[[MigrationProgress], None]


class MigrationService:
    """Handles data migration between SQLite and cloud backends.

    Supports:
    - Export from any backend to JSON format
    - Import from JSON to any backend
    - Attachment file migration between local and cloud storage
    """

    async def export_to_json(
        self,
        transaction_repo: TransactionRepository,
        planned_repo: PlannedRepository,
        sheet_repo: SheetRepository,
        audit_repo: AuditRepository,
        attachment_repo: AttachmentRepository,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> dict:
        """Export all data from repositories to a portable JSON format.

        Args:
            transaction_repo: Transaction repository to export from
            planned_repo: Planned templates repository
            sheet_repo: Sheet repository
            audit_repo: Audit log repository
            attachment_repo: Attachment metadata repository
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary containing all exported data
        """
        data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "transactions": [],
            "planned_templates": [],
            "sheets": [],
            "attachments": [],
            "audit_log": [],
        }

        # Export transactions
        if progress_callback:
            progress_callback(MigrationProgress("transactions", 0, 0, "Loading transactions..."))

        transactions = await transaction_repo.get_all()
        data["transactions"] = [self._transaction_to_dict(t) for t in transactions]

        if progress_callback:
            progress_callback(MigrationProgress(
                "transactions", len(transactions), len(transactions),
                f"Exported {len(transactions)} transactions"
            ))

        # Export planned templates
        if progress_callback:
            progress_callback(MigrationProgress("planned_templates", 0, 0, "Loading planned templates..."))

        templates = await planned_repo.get_all()
        data["planned_templates"] = [self._template_to_dict(t) for t in templates]

        if progress_callback:
            progress_callback(MigrationProgress(
                "planned_templates", len(templates), len(templates),
                f"Exported {len(templates)} planned templates"
            ))

        # Export sheets
        if progress_callback:
            progress_callback(MigrationProgress("sheets", 0, 0, "Loading sheets..."))

        sheets = await sheet_repo.get_all()
        data["sheets"] = [self._sheet_to_dict(s) for s in sheets]

        if progress_callback:
            progress_callback(MigrationProgress(
                "sheets", len(sheets), len(sheets),
                f"Exported {len(sheets)} sheets"
            ))

        # Export attachments (metadata only)
        if progress_callback:
            progress_callback(MigrationProgress("attachments", 0, 0, "Loading attachment metadata..."))

        # Get attachments for all transactions
        all_attachments = []
        for trans in transactions:
            attachments = await attachment_repo.get_for_transaction(trans.id)
            all_attachments.extend(attachments)

        data["attachments"] = [self._attachment_to_dict(a) for a in all_attachments]

        if progress_callback:
            progress_callback(MigrationProgress(
                "attachments", len(all_attachments), len(all_attachments),
                f"Exported {len(all_attachments)} attachment records"
            ))

        # Export audit log
        if progress_callback:
            progress_callback(MigrationProgress("audit_log", 0, 0, "Loading audit log..."))

        audit_entries = await audit_repo.get_all(limit=10000)
        data["audit_log"] = [self._audit_entry_to_dict(e) for e in audit_entries]

        if progress_callback:
            progress_callback(MigrationProgress(
                "audit_log", len(audit_entries), len(audit_entries),
                f"Exported {len(audit_entries)} audit entries"
            ))

        return data

    async def import_from_json(
        self,
        data: dict,
        transaction_repo: TransactionRepository,
        planned_repo: PlannedRepository,
        sheet_repo: SheetRepository,
        audit_repo: AuditRepository,
        attachment_repo: AttachmentRepository,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> MigrationResult:
        """Import data from JSON to repositories.

        Args:
            data: Dictionary containing exported data
            transaction_repo: Target transaction repository
            planned_repo: Target planned templates repository
            sheet_repo: Target sheet repository
            audit_repo: Target audit log repository
            attachment_repo: Target attachment metadata repository
            progress_callback: Optional callback for progress updates

        Returns:
            MigrationResult with counts and any errors
        """
        errors = []
        counts = {
            "transactions": 0,
            "planned_templates": 0,
            "sheets": 0,
            "attachments": 0,
            "audit_entries": 0,
        }

        # Import sheets first (may be referenced by transactions)
        sheets_data = data.get("sheets", [])
        total_sheets = len(sheets_data)

        for i, sheet_dict in enumerate(sheets_data):
            if progress_callback:
                progress_callback(MigrationProgress(
                    "sheets", i + 1, total_sheets, f"Importing sheet {i + 1}/{total_sheets}"
                ))
            try:
                sheet = self._dict_to_sheet(sheet_dict)
                await sheet_repo.save(sheet)
                counts["sheets"] += 1
            except Exception as e:
                errors.append(f"Sheet import error: {e}")

        # Import transactions
        transactions_data = data.get("transactions", [])
        total_trans = len(transactions_data)

        for i, trans_dict in enumerate(transactions_data):
            if progress_callback:
                progress_callback(MigrationProgress(
                    "transactions", i + 1, total_trans, f"Importing transaction {i + 1}/{total_trans}"
                ))
            try:
                transaction = self._dict_to_transaction(trans_dict)
                await transaction_repo.save(transaction)
                counts["transactions"] += 1
            except Exception as e:
                errors.append(f"Transaction import error: {e}")

        # Import planned templates
        templates_data = data.get("planned_templates", [])
        total_templates = len(templates_data)

        for i, template_dict in enumerate(templates_data):
            if progress_callback:
                progress_callback(MigrationProgress(
                    "planned_templates", i + 1, total_templates,
                    f"Importing template {i + 1}/{total_templates}"
                ))
            try:
                template = self._dict_to_template(template_dict)
                await planned_repo.save(template)
                counts["planned_templates"] += 1
            except Exception as e:
                errors.append(f"Template import error: {e}")

        # Import attachment metadata
        attachments_data = data.get("attachments", [])
        total_attachments = len(attachments_data)

        for i, att_dict in enumerate(attachments_data):
            if progress_callback:
                progress_callback(MigrationProgress(
                    "attachments", i + 1, total_attachments,
                    f"Importing attachment {i + 1}/{total_attachments}"
                ))
            try:
                attachment = self._dict_to_attachment(att_dict)
                await attachment_repo.save(attachment)
                counts["attachments"] += 1
            except Exception as e:
                errors.append(f"Attachment import error: {e}")

        # Import audit log
        audit_data = data.get("audit_log", [])
        total_audit = len(audit_data)

        for i, entry_dict in enumerate(audit_data):
            if progress_callback:
                progress_callback(MigrationProgress(
                    "audit_log", i + 1, total_audit,
                    f"Importing audit entry {i + 1}/{total_audit}"
                ))
            try:
                entry = self._dict_to_audit_entry(entry_dict)
                await audit_repo.log(entry)
                counts["audit_entries"] += 1
            except Exception as e:
                errors.append(f"Audit entry import error: {e}")

        return MigrationResult(
            success=len(errors) == 0,
            transactions_migrated=counts["transactions"],
            planned_templates_migrated=counts["planned_templates"],
            sheets_migrated=counts["sheets"],
            attachments_migrated=counts["attachments"],
            audit_entries_migrated=counts["audit_entries"],
            errors=errors,
        )

    async def migrate_attachments_to_cloud(
        self,
        local_dir: Path,
        attachments: list[Attachment],
        storage_config: "CloudStorageProvider",
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[int, list[str]]:
        """Upload local attachment files to cloud storage.

        Args:
            local_dir: Local directory containing attachment files
            attachments: List of attachment records to migrate
            storage_config: Cloud storage provider configuration
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (success_count, list of errors)
        """
        storage_url = f"{storage_config.project_url}/storage/v1"
        bucket = storage_config.bucket
        headers = {
            "Authorization": f"Bearer {storage_config.anon_key}",
            "apikey": storage_config.anon_key,
        }

        success_count = 0
        errors = []
        total = len(attachments)

        async with httpx.AsyncClient() as client:
            for i, attachment in enumerate(attachments):
                if progress_callback:
                    progress_callback(MigrationProgress(
                        "attachments_upload", i + 1, total,
                        f"Uploading {attachment.stored_name}"
                    ))

                local_path = local_dir / attachment.stored_name
                if not local_path.exists():
                    errors.append(f"File not found: {attachment.stored_name}")
                    continue

                try:
                    with open(local_path, "rb") as f:
                        content = f.read()

                    upload_url = f"{storage_url}/object/{bucket}/{attachment.stored_name}"
                    response = await client.post(
                        upload_url,
                        headers={
                            **headers,
                            "Content-Type": attachment.mime_type or "application/octet-stream",
                        },
                        content=content,
                    )
                    response.raise_for_status()
                    success_count += 1
                except Exception as e:
                    errors.append(f"Upload failed for {attachment.stored_name}: {e}")

        return success_count, errors

    async def migrate_attachments_to_local(
        self,
        local_dir: Path,
        attachments: list[Attachment],
        storage_config: "CloudStorageProvider",
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[int, list[str]]:
        """Download attachment files from cloud storage to local directory.

        Args:
            local_dir: Local directory to save files to
            attachments: List of attachment records to download
            storage_config: Cloud storage provider configuration
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (success_count, list of errors)
        """
        storage_url = f"{storage_config.project_url}/storage/v1"
        bucket = storage_config.bucket
        headers = {
            "Authorization": f"Bearer {storage_config.anon_key}",
            "apikey": storage_config.anon_key,
        }

        # Ensure local directory exists
        local_dir.mkdir(parents=True, exist_ok=True)

        success_count = 0
        errors = []
        total = len(attachments)

        async with httpx.AsyncClient() as client:
            for i, attachment in enumerate(attachments):
                if progress_callback:
                    progress_callback(MigrationProgress(
                        "attachments_download", i + 1, total,
                        f"Downloading {attachment.stored_name}"
                    ))

                try:
                    download_url = f"{storage_url}/object/{bucket}/{attachment.stored_name}"
                    response = await client.get(download_url, headers=headers)
                    response.raise_for_status()

                    local_path = local_dir / attachment.stored_name
                    with open(local_path, "wb") as f:
                        f.write(response.content)

                    success_count += 1
                except Exception as e:
                    errors.append(f"Download failed for {attachment.stored_name}: {e}")

        return success_count, errors

    # Serialization helpers

    def _transaction_to_dict(self, t: Transaction) -> dict:
        return {
            "id": str(t.id),
            "date": t.date.isoformat(),
            "description": t.description,
            "amount": str(t.amount),
            "type": t.type.value,
            "status": t.status.value,
            "sheet": t.sheet,
            "category": t.category,
            "party": t.party,
            "notes": t.notes,
            "reference": t.reference,
            "version": t.version,
            "created_at": t.created_at.isoformat(),
            "modified_at": t.modified_at.isoformat() if t.modified_at else None,
            "modified_by": t.modified_by,
        }

    def _dict_to_transaction(self, d: dict) -> Transaction:
        from uuid import UUID
        from datetime import date, datetime
        from decimal import Decimal
        from fidra.domain.models import TransactionType, ApprovalStatus

        return Transaction(
            id=UUID(d["id"]),
            date=date.fromisoformat(d["date"]),
            description=d["description"],
            amount=Decimal(d["amount"]),
            type=TransactionType(d["type"]),
            status=ApprovalStatus(d["status"]),
            sheet=d["sheet"],
            category=d.get("category"),
            party=d.get("party"),
            notes=d.get("notes"),
            reference=d.get("reference"),
            version=d.get("version", 1),
            created_at=datetime.fromisoformat(d["created_at"]),
            modified_at=datetime.fromisoformat(d["modified_at"]) if d.get("modified_at") else None,
            modified_by=d.get("modified_by"),
        )

    def _template_to_dict(self, t: PlannedTemplate) -> dict:
        return {
            "id": str(t.id),
            "start_date": t.start_date.isoformat(),
            "description": t.description,
            "amount": str(t.amount),
            "type": t.type.value,
            "frequency": t.frequency.value,
            "target_sheet": t.target_sheet,
            "category": t.category,
            "party": t.party,
            "end_date": t.end_date.isoformat() if t.end_date else None,
            "occurrence_count": t.occurrence_count,
            "skipped_dates": [d.isoformat() for d in t.skipped_dates],
            "fulfilled_dates": [d.isoformat() for d in t.fulfilled_dates],
            "version": t.version,
            "created_at": t.created_at.isoformat(),
        }

    def _dict_to_template(self, d: dict) -> PlannedTemplate:
        from uuid import UUID
        from datetime import date, datetime
        from decimal import Decimal
        from fidra.domain.models import TransactionType, Frequency

        return PlannedTemplate(
            id=UUID(d["id"]),
            start_date=date.fromisoformat(d["start_date"]),
            description=d["description"],
            amount=Decimal(d["amount"]),
            type=TransactionType(d["type"]),
            frequency=Frequency(d["frequency"]),
            target_sheet=d["target_sheet"],
            category=d.get("category"),
            party=d.get("party"),
            end_date=date.fromisoformat(d["end_date"]) if d.get("end_date") else None,
            occurrence_count=d.get("occurrence_count"),
            skipped_dates=tuple(date.fromisoformat(dt) for dt in d.get("skipped_dates", [])),
            fulfilled_dates=tuple(date.fromisoformat(dt) for dt in d.get("fulfilled_dates", [])),
            version=d.get("version", 1),
            created_at=datetime.fromisoformat(d["created_at"]),
        )

    def _sheet_to_dict(self, s: Sheet) -> dict:
        return {
            "id": str(s.id),
            "name": s.name,
            "is_virtual": s.is_virtual,
            "is_planned": s.is_planned,
            "created_at": s.created_at.isoformat(),
        }

    def _dict_to_sheet(self, d: dict) -> Sheet:
        from uuid import UUID
        from datetime import datetime

        return Sheet(
            id=UUID(d["id"]),
            name=d["name"],
            is_virtual=d.get("is_virtual", False),
            is_planned=d.get("is_planned", False),
            created_at=datetime.fromisoformat(d["created_at"]),
        )

    def _attachment_to_dict(self, a: Attachment) -> dict:
        return {
            "id": str(a.id),
            "transaction_id": str(a.transaction_id),
            "filename": a.filename,
            "stored_name": a.stored_name,
            "mime_type": a.mime_type,
            "file_size": a.file_size,
            "created_at": a.created_at.isoformat(),
        }

    def _dict_to_attachment(self, d: dict) -> Attachment:
        from uuid import UUID
        from datetime import datetime

        return Attachment(
            id=UUID(d["id"]),
            transaction_id=UUID(d["transaction_id"]),
            filename=d["filename"],
            stored_name=d["stored_name"],
            mime_type=d.get("mime_type"),
            file_size=d.get("file_size", 0),
            created_at=datetime.fromisoformat(d["created_at"]),
        )

    def _audit_entry_to_dict(self, e: AuditEntry) -> dict:
        return {
            "id": str(e.id),
            "timestamp": e.timestamp.isoformat(),
            "action": e.action.value,
            "entity_type": e.entity_type,
            "entity_id": str(e.entity_id),
            "user": e.user,
            "summary": e.summary,
            "details": e.details,
        }

    def _dict_to_audit_entry(self, d: dict) -> AuditEntry:
        from uuid import UUID
        from datetime import datetime
        from fidra.domain.models import AuditAction

        return AuditEntry(
            id=UUID(d["id"]),
            timestamp=datetime.fromisoformat(d["timestamp"]),
            action=AuditAction(d["action"]),
            entity_type=d["entity_type"],
            entity_id=UUID(d["entity_id"]),
            user=d["user"],
            summary=d["summary"],
            details=d.get("details"),
        )
