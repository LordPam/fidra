"""Audit logging service.

Records all changes to transactions, planned templates, and sheets
for accountability and traceability.
"""

import json
import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from PySide6.QtCore import QTimer

from fidra.data.repository import AuditRepository
from fidra.domain.models import (
    Attachment,
    AuditAction,
    AuditEntry,
    Transaction,
)

logger = logging.getLogger(__name__)


class AuditService:
    """Service for recording and querying audit trail entries."""

    def __init__(self, audit_repo: AuditRepository, user: str = "", connection_state=None):
        self._repo = audit_repo
        self._user = user or "System"
        self._connection_state = connection_state

    async def _safe_log(self, entry: AuditEntry) -> None:
        """Log an entry, silently handling network errors when offline."""
        try:
            await self._repo.log(entry)
        except OSError as e:
            # Network errors when offline - report and continue
            logger.debug(f"Audit log skipped (offline): {entry.summary}")
            self._report_network_error()
        except Exception as e:
            # Other errors - log warning but don't fail the operation
            logger.warning(f"Audit log failed: {e}")
            # Check if it looks like a network error
            error_str = str(e).lower()
            if "nodename" in error_str or "network" in error_str or "connection" in error_str:
                self._report_network_error()

    def _report_network_error(self) -> None:
        """Report network error to connection state service if available.

        Deferred via QTimer to avoid triggering Qt events during exception
        handling, which can cause crashes when the exception's traceback
        (holding Qt object references) is garbage collected.
        """
        if self._connection_state and hasattr(self._connection_state, 'report_network_error'):
            # Defer to next event loop iteration to avoid Qt/GC lifecycle issues
            QTimer.singleShot(0, self._connection_state.report_network_error)

    @property
    def user(self) -> str:
        return self._user

    @user.setter
    def user(self, value: str) -> None:
        self._user = value or "System"

    async def log_transaction_created(self, transaction: Transaction) -> None:
        """Log creation of a new transaction."""
        summary = (
            f"Created {transaction.type.value} "
            f"'{transaction.description}' "
            f"for {_format_amount(transaction.amount)} "
            f"on {transaction.date.isoformat()}"
        )
        entry = AuditEntry.create(
            action=AuditAction.CREATE,
            entity_type="transaction",
            entity_id=transaction.id,
            user=self._user,
            summary=summary,
            details=json.dumps({
                "description": transaction.description,
                "amount": str(transaction.amount),
                "type": transaction.type.value,
                "date": transaction.date.isoformat(),
                "sheet": transaction.sheet,
                "category": transaction.category,
                "status": transaction.status.value,
                "party": transaction.party,
                "notes": transaction.notes,
                "reference": transaction.reference,
            }),
        )
        await self._safe_log(entry)

    async def log_transaction_updated(
        self, old: Transaction, new: Transaction
    ) -> None:
        """Log an update to a transaction, noting what changed."""
        changes = _diff_transactions(old, new)
        if not changes:
            return

        change_parts = [f"{k}: {v['old']} -> {v['new']}" for k, v in changes.items()]
        summary = (
            f"Updated '{new.description}': {', '.join(change_parts)}"
        )
        entry = AuditEntry.create(
            action=AuditAction.UPDATE,
            entity_type="transaction",
            entity_id=new.id,
            user=self._user,
            summary=summary,
            details=json.dumps(changes),
        )
        await self._safe_log(entry)

    async def log_transaction_deleted(self, transaction: Transaction) -> None:
        """Log deletion of a transaction."""
        summary = (
            f"Deleted {transaction.type.value} "
            f"'{transaction.description}' "
            f"({_format_amount(transaction.amount)})"
        )
        entry = AuditEntry.create(
            action=AuditAction.DELETE,
            entity_type="transaction",
            entity_id=transaction.id,
            user=self._user,
            summary=summary,
        )
        await self._safe_log(entry)

    async def log_attachment_added(
        self, transaction: Transaction, filename: str
    ) -> None:
        """Log addition of an attachment to a transaction."""
        summary = f"Added attachment '{filename}' to '{transaction.description}'"
        entry = AuditEntry.create(
            action=AuditAction.UPDATE,
            entity_type="transaction",
            entity_id=transaction.id,
            user=self._user,
            summary=summary,
            details=json.dumps({"attachment_added": filename}),
        )
        await self._safe_log(entry)

    async def log_attachment_removed(
        self, transaction: Transaction, filename: str
    ) -> None:
        """Log removal of an attachment from a transaction."""
        summary = f"Removed attachment '{filename}' from '{transaction.description}'"
        entry = AuditEntry.create(
            action=AuditAction.UPDATE,
            entity_type="transaction",
            entity_id=transaction.id,
            user=self._user,
            summary=summary,
            details=json.dumps({"attachment_removed": filename}),
        )
        await self._safe_log(entry)

    async def log_generic(
        self,
        action: AuditAction,
        entity_type: str,
        entity_id: UUID,
        summary: str,
        details: Optional[str] = None,
    ) -> None:
        """Log a generic audit entry."""
        entry = AuditEntry.create(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user=self._user,
            summary=summary,
            details=details,
        )
        await self._safe_log(entry)

    async def get_log(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[UUID] = None,
        limit: int = 500,
    ) -> list[AuditEntry]:
        """Retrieve audit log entries."""
        return await self._repo.get_all(
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )

    async def get_history(self, entity_id: UUID) -> list[AuditEntry]:
        """Get the full change history for an entity."""
        return await self._repo.get_for_entity(entity_id)


def _format_amount(amount: Decimal) -> str:
    return f"\u00a3{amount:,.2f}"


def _diff_transactions(old: Transaction, new: Transaction) -> dict:
    """Compare two transactions and return a dict of changed fields."""
    changes = {}
    fields = ["description", "amount", "type", "date", "sheet", "category",
              "party", "status", "notes", "reference"]

    for field in fields:
        old_val = getattr(old, field)
        new_val = getattr(new, field)
        if old_val != new_val:
            # Convert to string representations
            old_str = _field_to_str(field, old_val)
            new_str = _field_to_str(field, new_val)
            changes[field] = {"old": old_str, "new": new_str}

    return changes


def _field_to_str(field: str, value: object) -> str:
    if value is None:
        return ""
    if field == "amount":
        return f"\u00a3{value:,.2f}"
    if field in ("type", "status"):
        return value.value if hasattr(value, "value") else str(value)
    if field == "date":
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    return str(value)
