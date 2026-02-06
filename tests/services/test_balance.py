"""Tests for Balance Service."""

import pytest
from datetime import date
from decimal import Decimal

from fidra.services.balance import BalanceService
from fidra.domain.models import Transaction, TransactionType, ApprovalStatus


class TestBalanceService:
    """Tests for BalanceService."""

    def test_compute_total_empty_list(self):
        """Empty transaction list returns zero balance."""
        service = BalanceService()
        total = service.compute_total([])
        assert total == Decimal("0")

    def test_compute_total_single_income(self, make_transaction):
        """Single income transaction."""
        service = BalanceService()
        trans = make_transaction(
            type=TransactionType.INCOME,
            amount=Decimal("1000.00"),
            status=ApprovalStatus.AUTO,
        )
        total = service.compute_total([trans])
        assert total == Decimal("1000.00")

    def test_compute_total_single_expense(self, make_transaction):
        """Single expense transaction."""
        service = BalanceService()
        trans = make_transaction(
            type=TransactionType.EXPENSE,
            amount=Decimal("500.00"),
            status=ApprovalStatus.APPROVED,
        )
        total = service.compute_total([trans])
        assert total == Decimal("-500.00")

    def test_compute_total_mixed_transactions(self, make_transaction):
        """Mixed income and expense transactions."""
        service = BalanceService()
        transactions = [
            make_transaction(
                type=TransactionType.INCOME,
                amount=Decimal("2500.00"),
                status=ApprovalStatus.AUTO,
            ),
            make_transaction(
                type=TransactionType.EXPENSE,
                amount=Decimal("800.00"),
                status=ApprovalStatus.APPROVED,
            ),
            make_transaction(
                type=TransactionType.EXPENSE,
                amount=Decimal("50.00"),
                status=ApprovalStatus.APPROVED,
            ),
        ]
        total = service.compute_total(transactions)
        assert total == Decimal("1650.00")  # 2500 - 800 - 50

    def test_compute_total_excludes_pending(self, make_transaction):
        """Pending expenses are excluded from balance."""
        service = BalanceService()
        transactions = [
            make_transaction(
                type=TransactionType.INCOME,
                amount=Decimal("1000.00"),
                status=ApprovalStatus.AUTO,
            ),
            make_transaction(
                type=TransactionType.EXPENSE,
                amount=Decimal("200.00"),
                status=ApprovalStatus.PENDING,  # Not counted
            ),
        ]
        total = service.compute_total(transactions)
        assert total == Decimal("1000.00")  # Pending not counted

    def test_compute_total_excludes_rejected(self, make_transaction):
        """Rejected expenses are excluded from balance."""
        service = BalanceService()
        transactions = [
            make_transaction(
                type=TransactionType.INCOME,
                amount=Decimal("1000.00"),
                status=ApprovalStatus.AUTO,
            ),
            make_transaction(
                type=TransactionType.EXPENSE,
                amount=Decimal("200.00"),
                status=ApprovalStatus.REJECTED,  # Not counted
            ),
        ]
        total = service.compute_total(transactions)
        assert total == Decimal("1000.00")

    def test_compute_total_excludes_planned(self, make_transaction):
        """Planned transactions are excluded from balance (used for forecasting only)."""
        service = BalanceService()
        transactions = [
            make_transaction(
                type=TransactionType.INCOME,
                amount=Decimal("1000.00"),
                status=ApprovalStatus.AUTO,
            ),
            make_transaction(
                type=TransactionType.INCOME,
                amount=Decimal("500.00"),
                status=ApprovalStatus.PLANNED,  # Should NOT count
            ),
            make_transaction(
                type=TransactionType.EXPENSE,
                amount=Decimal("200.00"),
                status=ApprovalStatus.APPROVED,
            ),
            make_transaction(
                type=TransactionType.EXPENSE,
                amount=Decimal("100.00"),
                status=ApprovalStatus.PLANNED,  # Should NOT count
            ),
        ]
        total = service.compute_total(transactions)
        assert total == Decimal("800.00")  # 1000 - 200 (planned excluded)

    def test_compute_running_balances(self, make_transaction):
        """Compute running balance for each transaction."""
        service = BalanceService()
        trans1 = make_transaction(
            date=date(2024, 1, 1),
            type=TransactionType.INCOME,
            amount=Decimal("1000.00"),
            status=ApprovalStatus.AUTO,
        )
        trans2 = make_transaction(
            date=date(2024, 1, 2),
            type=TransactionType.EXPENSE,
            amount=Decimal("200.00"),
            status=ApprovalStatus.APPROVED,
        )
        trans3 = make_transaction(
            date=date(2024, 1, 3),
            type=TransactionType.EXPENSE,
            amount=Decimal("300.00"),
            status=ApprovalStatus.APPROVED,
        )

        balances = service.compute_running_balances([trans1, trans2, trans3])

        assert balances[str(trans1.id)] == Decimal("1000.00")
        assert balances[str(trans2.id)] == Decimal("800.00")  # 1000 - 200
        assert balances[str(trans3.id)] == Decimal("500.00")  # 800 - 300

    def test_compute_running_balances_handles_unordered(self, make_transaction):
        """Running balances handle unordered input (sorts by date)."""
        service = BalanceService()
        trans1 = make_transaction(
            date=date(2024, 1, 3),  # Latest
            type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            status=ApprovalStatus.APPROVED,
        )
        trans2 = make_transaction(
            date=date(2024, 1, 1),  # Earliest
            type=TransactionType.INCOME,
            amount=Decimal("500.00"),
            status=ApprovalStatus.AUTO,
        )
        trans3 = make_transaction(
            date=date(2024, 1, 2),  # Middle
            type=TransactionType.EXPENSE,
            amount=Decimal("200.00"),
            status=ApprovalStatus.APPROVED,
        )

        # Pass unordered
        balances = service.compute_running_balances([trans1, trans2, trans3])

        # Should still calculate correctly (sorted by date)
        assert balances[str(trans2.id)] == Decimal("500.00")  # First (Jan 1)
        assert balances[str(trans3.id)] == Decimal("300.00")  # Second (Jan 2)
        assert balances[str(trans1.id)] == Decimal("200.00")  # Third (Jan 3)

    def test_compute_pending_total(self, make_transaction):
        """Compute total of pending expenses."""
        service = BalanceService()
        transactions = [
            make_transaction(
                type=TransactionType.EXPENSE,
                amount=Decimal("100.00"),
                status=ApprovalStatus.PENDING,
            ),
            make_transaction(
                type=TransactionType.EXPENSE,
                amount=Decimal("200.00"),
                status=ApprovalStatus.PENDING,
            ),
            make_transaction(
                type=TransactionType.EXPENSE,
                amount=Decimal("50.00"),
                status=ApprovalStatus.APPROVED,  # Not pending
            ),
        ]

        pending_total = service.compute_pending_total(transactions)
        assert pending_total == Decimal("300.00")  # 100 + 200
