"""Tests for Transaction Table Model."""

import pytest
from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt

from fidra.ui.models.transaction_model import TransactionTableModel
from fidra.domain.models import Transaction, TransactionType, ApprovalStatus


class TestTransactionTableModel:
    """Tests for TransactionTableModel."""

    def test_empty_model(self):
        """Empty model has zero rows."""
        model = TransactionTableModel()
        assert model.rowCount() == 0
        assert model.columnCount() == 12  # Includes Sheet, Activity columns

    def test_column_names(self):
        """Model has correct column headers."""
        model = TransactionTableModel()
        expected_columns = [
            "Date",
            "Description",
            "Amount",
            "Type",
            "Category",
            "Party",
            "Reference",
            "Activity",
            "Sheet",
            "Status",
            "Balance",
            "Notes",
        ]
        for i, name in enumerate(expected_columns):
            assert model.headerData(i, Qt.Horizontal, Qt.DisplayRole) == name

    def test_single_transaction(self, make_transaction):
        """Model with single transaction displays correctly."""
        trans = make_transaction(
            date=date(2024, 1, 15),
            description="Test Transaction",
            amount=Decimal("100.00"),
            type=TransactionType.EXPENSE,
            category="Food",
            party="Store",
            status=ApprovalStatus.APPROVED,
            notes="Test note",
        )
        model = TransactionTableModel([trans])

        assert model.rowCount() == 1

        # Check date
        assert model.data(model.index(0, model.COL_DATE), Qt.DisplayRole) == "2024-01-15"

        # Check description
        assert model.data(model.index(0, model.COL_DESCRIPTION), Qt.DisplayRole) == "Test Transaction"

        # Check amount
        assert model.data(model.index(0, model.COL_AMOUNT), Qt.DisplayRole) == "£100.00"

        # Check type
        assert model.data(model.index(0, model.COL_TYPE), Qt.DisplayRole) == "Expense"

        # Check category
        assert model.data(model.index(0, model.COL_CATEGORY), Qt.DisplayRole) == "Food"

        # Check party
        assert model.data(model.index(0, model.COL_PARTY), Qt.DisplayRole) == "Store"

        # Check status
        assert model.data(model.index(0, model.COL_STATUS), Qt.DisplayRole) == "Approved"

        # Check notes
        assert model.data(model.index(0, model.COL_NOTES), Qt.DisplayRole) == "Test note"

    def test_multiple_transactions(self, make_transaction):
        """Model with multiple transactions."""
        trans1 = make_transaction(
            date=date(2024, 1, 1),
            description="Trans 1",
            amount=Decimal("100.00"),
            type=TransactionType.INCOME,
            status=ApprovalStatus.AUTO,
        )
        trans2 = make_transaction(
            date=date(2024, 1, 2),
            description="Trans 2",
            amount=Decimal("50.00"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.APPROVED,
        )
        trans3 = make_transaction(
            date=date(2024, 1, 3),
            description="Trans 3",
            amount=Decimal("25.00"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.APPROVED,
        )

        model = TransactionTableModel([trans1, trans2, trans3])
        assert model.rowCount() == 3

    def test_running_balance_calculation(self, make_transaction):
        """Model calculates running balances correctly."""
        trans1 = make_transaction(
            date=date(2024, 1, 1),
            description="Income",
            amount=Decimal("1000.00"),
            type=TransactionType.INCOME,
            status=ApprovalStatus.AUTO,
        )
        trans2 = make_transaction(
            date=date(2024, 1, 2),
            description="Expense 1",
            amount=Decimal("200.00"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.APPROVED,
        )
        trans3 = make_transaction(
            date=date(2024, 1, 3),
            description="Expense 2",
            amount=Decimal("300.00"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.APPROVED,
        )

        model = TransactionTableModel([trans1, trans2, trans3])

        # Check balances
        balance1 = model.data(model.index(0, model.COL_BALANCE), Qt.DisplayRole)
        balance2 = model.data(model.index(1, model.COL_BALANCE), Qt.DisplayRole)
        balance3 = model.data(model.index(2, model.COL_BALANCE), Qt.DisplayRole)

        assert balance1 == "£1000.00"
        assert balance2 == "£800.00"  # 1000 - 200
        assert balance3 == "£500.00"  # 800 - 300

    def test_set_transactions(self, make_transaction):
        """set_transactions updates the model."""
        model = TransactionTableModel()
        assert model.rowCount() == 0

        trans1 = make_transaction(description="Trans 1")
        trans2 = make_transaction(description="Trans 2")

        model.set_transactions([trans1, trans2])
        assert model.rowCount() == 2
        assert model.data(model.index(0, model.COL_DESCRIPTION), Qt.DisplayRole) == "Trans 1"
        assert model.data(model.index(1, model.COL_DESCRIPTION), Qt.DisplayRole) == "Trans 2"

    def test_get_transaction_at(self, make_transaction):
        """get_transaction_at returns correct transaction."""
        trans1 = make_transaction(description="Trans 1")
        trans2 = make_transaction(description="Trans 2")

        model = TransactionTableModel([trans1, trans2])

        retrieved1 = model.get_transaction_at(0)
        retrieved2 = model.get_transaction_at(1)

        assert retrieved1 == trans1
        assert retrieved2 == trans2

    def test_get_transaction_at_invalid_index(self, make_transaction):
        """get_transaction_at returns None for invalid index."""
        trans = make_transaction()
        model = TransactionTableModel([trans])

        assert model.get_transaction_at(-1) is None
        assert model.get_transaction_at(1) is None
        assert model.get_transaction_at(100) is None

    def test_user_role_returns_transaction(self, make_transaction):
        """UserRole returns the full transaction object."""
        trans = make_transaction(description="Test")
        model = TransactionTableModel([trans])

        retrieved = model.data(model.index(0, 0), Qt.UserRole)
        assert retrieved == trans

    def test_alignment(self, make_transaction):
        """Amount and Balance columns are right-aligned."""
        trans = make_transaction()
        model = TransactionTableModel([trans])

        # Amount column should be right-aligned
        amount_alignment = model.data(model.index(0, model.COL_AMOUNT), Qt.TextAlignmentRole)
        assert amount_alignment == (Qt.AlignRight | Qt.AlignVCenter)

        # Balance column should be right-aligned
        balance_alignment = model.data(model.index(0, model.COL_BALANCE), Qt.TextAlignmentRole)
        assert balance_alignment == (Qt.AlignRight | Qt.AlignVCenter)

        # Other columns should be left-aligned
        desc_alignment = model.data(model.index(0, model.COL_DESCRIPTION), Qt.TextAlignmentRole)
        assert desc_alignment == (Qt.AlignLeft | Qt.AlignVCenter)

    def test_get_all_transactions(self, make_transaction):
        """get_all_transactions returns copy of transaction list."""
        trans1 = make_transaction(description="Trans 1")
        trans2 = make_transaction(description="Trans 2")

        model = TransactionTableModel([trans1, trans2])
        all_trans = model.get_all_transactions()

        assert len(all_trans) == 2
        assert all_trans[0] == trans1
        assert all_trans[1] == trans2

        # Verify it's a copy (modifying shouldn't affect model)
        all_trans.clear()
        assert model.rowCount() == 2
