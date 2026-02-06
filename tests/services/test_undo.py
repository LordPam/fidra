"""Tests for Undo Service with Command pattern."""

import pytest
from datetime import date
from decimal import Decimal

from fidra.services.undo import (
    AddTransactionCommand,
    EditTransactionCommand,
    DeleteTransactionCommand,
    BulkEditCommand,
    UndoStack,
)
from fidra.domain.models import Transaction, TransactionType


class TestCommands:
    """Tests for Command implementations."""

    @pytest.mark.asyncio
    async def test_add_transaction_command(self, repos):
        """AddTransactionCommand executes and undoes correctly."""
        trans_repo, *_ = repos

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Test",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        command = AddTransactionCommand(trans_repo, trans)

        # Execute
        await command.execute()
        retrieved = await trans_repo.get_by_id(trans.id)
        assert retrieved is not None
        assert retrieved.description == "Test"

        # Undo
        await command.undo()
        retrieved = await trans_repo.get_by_id(trans.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_edit_transaction_command(self, repos):
        """EditTransactionCommand executes and undoes correctly."""
        trans_repo, *_ = repos

        # Create initial transaction
        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Original",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )
        await trans_repo.save(trans)

        # Edit it
        updated = trans.with_updates(description="Updated")
        command = EditTransactionCommand(trans_repo, trans, updated)

        # Execute
        await command.execute()
        retrieved = await trans_repo.get_by_id(trans.id)
        assert retrieved.description == "Updated"

        # Undo
        await command.undo()
        retrieved = await trans_repo.get_by_id(trans.id)
        assert retrieved.description == "Original"

    @pytest.mark.asyncio
    async def test_delete_transaction_command(self, repos):
        """DeleteTransactionCommand executes and undoes correctly."""
        trans_repo, *_ = repos

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="To Delete",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )
        await trans_repo.save(trans)

        command = DeleteTransactionCommand(trans_repo, trans)

        # Execute
        await command.execute()
        retrieved = await trans_repo.get_by_id(trans.id)
        assert retrieved is None

        # Undo (restore)
        await command.undo()
        retrieved = await trans_repo.get_by_id(trans.id)
        assert retrieved is not None
        assert retrieved.description == "To Delete"

    @pytest.mark.asyncio
    async def test_bulk_edit_command(self, repos):
        """BulkEditCommand handles multiple transactions."""
        trans_repo, *_ = repos

        # Create 3 transactions
        trans1 = Transaction.create(
            date=date(2024, 1, 1),
            description="Trans 1",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )
        trans2 = Transaction.create(
            date=date(2024, 1, 2),
            description="Trans 2",
            amount=Decimal("200.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )
        trans3 = Transaction.create(
            date=date(2024, 1, 3),
            description="Trans 3",
            amount=Decimal("300.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        old_states = [trans1, trans2, trans3]
        for t in old_states:
            await trans_repo.save(t)

        # Update all to different sheet
        new_states = [t.with_updates(sheet="Other") for t in old_states]

        command = BulkEditCommand(trans_repo, old_states, new_states)

        # Execute
        await command.execute()
        for t in new_states:
            retrieved = await trans_repo.get_by_id(t.id)
            assert retrieved.sheet == "Other"

        # Undo
        await command.undo()
        for t in old_states:
            retrieved = await trans_repo.get_by_id(t.id)
            assert retrieved.sheet == "Main"


class TestUndoStack:
    """Tests for UndoStack."""

    @pytest.mark.asyncio
    async def test_execute_adds_to_undo_stack(self, repos):
        """Executing command adds it to undo stack."""
        trans_repo, *_ = repos
        stack = UndoStack()

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Test",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )
        command = AddTransactionCommand(trans_repo, trans)

        assert not stack.can_undo
        await stack.execute(command)
        assert stack.can_undo

    @pytest.mark.asyncio
    async def test_undo_moves_to_redo_stack(self, repos):
        """Undoing moves command to redo stack."""
        trans_repo, *_ = repos
        stack = UndoStack()

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Test",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )
        command = AddTransactionCommand(trans_repo, trans)

        await stack.execute(command)
        assert not stack.can_redo

        await stack.undo()
        assert stack.can_redo

    @pytest.mark.asyncio
    async def test_redo_moves_back_to_undo_stack(self, repos):
        """Redoing moves command back to undo stack."""
        trans_repo, *_ = repos
        stack = UndoStack()

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Test",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )
        command = AddTransactionCommand(trans_repo, trans)

        await stack.execute(command)
        await stack.undo()
        await stack.redo()

        assert stack.can_undo
        assert not stack.can_redo

    @pytest.mark.asyncio
    async def test_new_command_clears_redo_stack(self, repos):
        """Executing new command clears redo stack."""
        trans_repo, *_ = repos
        stack = UndoStack()

        trans1 = Transaction.create(
            date=date(2024, 1, 15),
            description="Test 1",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )
        trans2 = Transaction.create(
            date=date(2024, 1, 16),
            description="Test 2",
            amount=Decimal("200.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        # Execute, then undo
        await stack.execute(AddTransactionCommand(trans_repo, trans1))
        await stack.undo()
        assert stack.can_redo

        # Execute new command - should clear redo
        await stack.execute(AddTransactionCommand(trans_repo, trans2))
        assert not stack.can_redo

    @pytest.mark.asyncio
    async def test_undo_description(self, repos):
        """Undo description returns command description."""
        trans_repo, *_ = repos
        stack = UndoStack()

        trans = Transaction.create(
            date=date(2024, 1, 15),
            description="Coffee",
            amount=Decimal("4.50"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        await stack.execute(AddTransactionCommand(trans_repo, trans))
        assert "Coffee" in stack.undo_description

    @pytest.mark.asyncio
    async def test_stack_size_limit(self, repos):
        """Stack respects max size limit."""
        trans_repo, *_ = repos
        stack = UndoStack(max_size=3)

        # Add 5 commands
        for i in range(5):
            trans = Transaction.create(
                date=date(2024, 1, i + 1),
                description=f"Trans {i}",
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                sheet="Main",
            )
            await stack.execute(AddTransactionCommand(trans_repo, trans))

        # Should only have 3 (max_size)
        undo_count = 0
        while stack.can_undo:
            await stack.undo()
            undo_count += 1

        assert undo_count == 3

    @pytest.mark.asyncio
    async def test_disable_enable_undo(self, repos):
        """Undo can be temporarily disabled."""
        trans_repo, *_ = repos
        stack = UndoStack()

        trans1 = Transaction.create(
            date=date(2024, 1, 15),
            description="Test 1",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        trans2 = Transaction.create(
            date=date(2024, 1, 16),
            description="Test 2",
            amount=Decimal("200.00"),
            type=TransactionType.EXPENSE,
            sheet="Main",
        )

        # Disable undo
        stack.disable()
        await stack.execute(AddTransactionCommand(trans_repo, trans1))
        assert not stack.can_undo  # Not tracked

        # Re-enable
        stack.enable()
        await stack.execute(AddTransactionCommand(trans_repo, trans2))
        assert stack.can_undo  # Now tracked

    def test_clear_undo_stack(self):
        """Clear removes all history."""
        stack = UndoStack()
        stack._undo.append("fake_command")
        stack._redo.append("fake_command")

        stack.clear()

        assert not stack.can_undo
        assert not stack.can_redo
