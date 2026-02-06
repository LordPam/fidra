"""Undo/Redo service with Command pattern.

Implements the Command pattern for all state-mutating operations,
enabling undo/redo functionality throughout the application.
"""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import asdict
from typing import TYPE_CHECKING, Optional

from fidra.data.repository import TransactionRepository
from fidra.domain.models import Transaction

if TYPE_CHECKING:
    from fidra.services.audit import AuditService


class Command(ABC):
    """Abstract base class for undoable commands."""

    @abstractmethod
    async def execute(self) -> None:
        """Execute the command (do the action)."""
        pass

    @abstractmethod
    async def undo(self) -> None:
        """Undo the command (reverse the action)."""
        pass

    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of the command."""
        pass


class AddTransactionCommand(Command):
    """Command to add a new transaction."""

    def __init__(
        self,
        repository: TransactionRepository,
        transaction: Transaction,
        audit_service: Optional["AuditService"] = None,
    ):
        self.repository = repository
        self.transaction = transaction
        self._audit = audit_service

    async def execute(self) -> None:
        """Add the transaction to the repository."""
        await self.repository.save(self.transaction)
        if self._audit:
            await self._audit.log_transaction_created(self.transaction)

    async def undo(self) -> None:
        """Remove the transaction from the repository."""
        await self.repository.delete(self.transaction.id)
        if self._audit:
            await self._audit.log_transaction_deleted(self.transaction)

    def description(self) -> str:
        """Describe the add operation."""
        return f"Add transaction: {self.transaction.description}"


class EditTransactionCommand(Command):
    """Command to edit an existing transaction."""

    def __init__(
        self,
        repository: TransactionRepository,
        old_transaction: Transaction,
        new_transaction: Transaction,
        audit_service: Optional["AuditService"] = None,
    ):
        self.repository = repository
        self.old_transaction = old_transaction
        self.new_transaction = new_transaction
        self._first_execute = True  # Track if this is initial execute vs redo
        self._audit = audit_service

    async def execute(self) -> None:
        """Save the new transaction state."""
        if self._first_execute:
            await self.repository.save(self.new_transaction)
            self._first_execute = False
        else:
            current_version = await self.repository.get_version(self.new_transaction.id)
            if current_version is not None:
                data = asdict(self.new_transaction)
                data['version'] = current_version + 1
                to_save = Transaction(**data)
                await self.repository.save(to_save)
            else:
                await self.repository.save(self.new_transaction)
        if self._audit:
            await self._audit.log_transaction_updated(
                self.old_transaction, self.new_transaction
            )

    async def undo(self) -> None:
        """Restore the old transaction state."""
        current_version = await self.repository.get_version(self.old_transaction.id)
        if current_version is not None:
            data = asdict(self.old_transaction)
            data['version'] = current_version + 1
            restored = Transaction(**data)
            await self.repository.save(restored)
        if self._audit:
            await self._audit.log_transaction_updated(
                self.new_transaction, self.old_transaction
            )

    def description(self) -> str:
        """Describe the edit operation."""
        return f"Edit transaction: {self.new_transaction.description}"


class DeleteTransactionCommand(Command):
    """Command to delete a transaction."""

    def __init__(
        self,
        repository: TransactionRepository,
        transaction: Transaction,
        audit_service: Optional["AuditService"] = None,
    ):
        self.repository = repository
        self.transaction = transaction
        self._audit = audit_service

    async def execute(self) -> None:
        """Delete the transaction from the repository."""
        await self.repository.delete(self.transaction.id)
        if self._audit:
            await self._audit.log_transaction_deleted(self.transaction)

    async def undo(self) -> None:
        """Restore the deleted transaction."""
        await self.repository.save(self.transaction)
        if self._audit:
            await self._audit.log_transaction_created(self.transaction)

    def description(self) -> str:
        """Describe the delete operation."""
        return f"Delete transaction: {self.transaction.description}"


class BulkEditCommand(Command):
    """Command to edit multiple transactions at once."""

    def __init__(
        self,
        repository: TransactionRepository,
        old_transactions: list[Transaction],
        new_transactions: list[Transaction],
        audit_service: Optional["AuditService"] = None,
    ):
        self.repository = repository
        self.old_transactions = old_transactions
        self.new_transactions = new_transactions
        self._first_execute = True  # Track if this is initial execute vs redo
        self._audit = audit_service

    async def execute(self) -> None:
        """Save all new transaction states."""
        if self._first_execute:
            for transaction in self.new_transactions:
                await self.repository.save(transaction)
            self._first_execute = False
        else:
            for transaction in self.new_transactions:
                current_version = await self.repository.get_version(transaction.id)
                if current_version is not None:
                    data = asdict(transaction)
                    data['version'] = current_version + 1
                    to_save = Transaction(**data)
                    await self.repository.save(to_save)
                else:
                    await self.repository.save(transaction)
        if self._audit:
            for old, new in zip(self.old_transactions, self.new_transactions):
                await self._audit.log_transaction_updated(old, new)

    async def undo(self) -> None:
        """Restore all old transaction states."""
        for transaction in self.old_transactions:
            current_version = await self.repository.get_version(transaction.id)
            if current_version is not None:
                data = asdict(transaction)
                data['version'] = current_version + 1
                restored = Transaction(**data)
                await self.repository.save(restored)
        if self._audit:
            for old, new in zip(self.old_transactions, self.new_transactions):
                await self._audit.log_transaction_updated(new, old)

    def description(self) -> str:
        """Describe the bulk edit operation."""
        count = len(self.new_transactions)
        return f"Bulk edit: {count} transaction{'s' if count != 1 else ''}"


class UndoStack:
    """Manages undo/redo stacks for commands.

    Maintains two stacks:
    - undo_stack: Commands that can be undone
    - redo_stack: Commands that can be redone

    When a new command is executed, the redo stack is cleared.
    """

    def __init__(self, max_size: int = 50):
        """Initialize the undo stack.

        Args:
            max_size: Maximum number of commands to keep in history
        """
        self._undo: deque[Command] = deque(maxlen=max_size)
        self._redo: deque[Command] = deque(maxlen=max_size)
        self._enabled = True

    async def execute(self, command: Command) -> None:
        """Execute a command and add it to the undo stack.

        Args:
            command: The command to execute
        """
        await command.execute()

        if self._enabled:
            self._undo.append(command)
            self._redo.clear()  # Clear redo stack on new action

    async def undo(self) -> None:
        """Undo the most recent command.

        Raises:
            IndexError: If there are no commands to undo
        """
        if not self.can_undo:
            raise IndexError("No commands to undo")

        command = self._undo.pop()
        await command.undo()
        self._redo.append(command)

    async def redo(self) -> None:
        """Redo the most recently undone command.

        Raises:
            IndexError: If there are no commands to redo
        """
        if not self.can_redo:
            raise IndexError("No commands to redo")

        command = self._redo.pop()
        await command.execute()
        self._undo.append(command)

    @property
    def can_undo(self) -> bool:
        """Check if there are commands available to undo."""
        return len(self._undo) > 0

    @property
    def can_redo(self) -> bool:
        """Check if there are commands available to redo."""
        return len(self._redo) > 0

    @property
    def undo_description(self) -> Optional[str]:
        """Get description of the next command to undo."""
        if self.can_undo:
            return self._undo[-1].description()
        return None

    @property
    def redo_description(self) -> Optional[str]:
        """Get description of the next command to redo."""
        if self.can_redo:
            return self._redo[-1].description()
        return None

    def disable(self) -> None:
        """Disable undo tracking.

        When disabled, executed commands will not be added to the undo stack.
        Useful for operations that shouldn't be undoable (e.g., loading data).
        """
        self._enabled = False

    def enable(self) -> None:
        """Enable undo tracking."""
        self._enabled = True

    def clear(self) -> None:
        """Clear all undo and redo history."""
        self._undo.clear()
        self._redo.clear()
