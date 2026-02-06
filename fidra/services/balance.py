"""Balance calculation service.

Computes balances from transactions based on type and status.
"""

from decimal import Decimal

from fidra.domain.models import ApprovalStatus, Transaction, TransactionType


class BalanceService:
    """Calculates balances from transactions.

    The service respects transaction status:
    - Income: Counts AUTO, APPROVED (PLANNED is for forecasting, not current balance)
    - Expenses: Counts APPROVED only (PENDING, REJECTED, PLANNED excluded)
    """

    # Statuses that count toward balance
    COUNTABLE_INCOME = {ApprovalStatus.AUTO, ApprovalStatus.APPROVED}
    COUNTABLE_EXPENSE = {ApprovalStatus.APPROVED}

    def compute_total(self, transactions: list[Transaction]) -> Decimal:
        """Compute net balance from transactions.

        Args:
            transactions: List of transactions

        Returns:
            Net balance (income - expenses)

        Example:
            >>> service = BalanceService()
            >>> transactions = [
            ...     Transaction(..., type=INCOME, amount=1000, status=AUTO),
            ...     Transaction(..., type=EXPENSE, amount=200, status=APPROVED)
            ... ]
            >>> service.compute_total(transactions)
            Decimal('800.00')
        """
        total = Decimal("0")

        for t in transactions:
            if t.type == TransactionType.INCOME and t.status in self.COUNTABLE_INCOME:
                total += t.amount
            elif t.type == TransactionType.EXPENSE and t.status in self.COUNTABLE_EXPENSE:
                total -= t.amount

        return total

    def compute_running_balances(
        self, transactions: list[Transaction]
    ) -> dict[str, Decimal]:
        """Compute running balance for each transaction.

        Transactions are sorted by date (ascending) and created_at for
        chronological balance calculation.

        Args:
            transactions: List of transactions (can be unordered)

        Returns:
            Dictionary mapping transaction ID (as string) to running balance

        Example:
            >>> balances = service.compute_running_balances(transactions)
            >>> balances['trans-uuid-1']
            Decimal('1000.00')
        """
        balances = {}
        running = Decimal("0")

        # Sort by date (ascending), then by created_at
        sorted_trans = sorted(transactions, key=lambda x: (x.date, x.created_at))

        for t in sorted_trans:
            if t.type == TransactionType.INCOME and t.status in self.COUNTABLE_INCOME:
                running += t.amount
            elif t.type == TransactionType.EXPENSE and t.status in self.COUNTABLE_EXPENSE:
                running -= t.amount

            balances[str(t.id)] = running

        return balances

    def compute_pending_total(self, transactions: list[Transaction]) -> Decimal:
        """Compute total of pending expenses.

        Args:
            transactions: List of transactions

        Returns:
            Sum of all pending expense amounts

        Example:
            >>> service.compute_pending_total(transactions)
            Decimal('450.00')
        """
        return sum(
            t.amount
            for t in transactions
            if t.type == TransactionType.EXPENSE and t.status == ApprovalStatus.PENDING
        )
