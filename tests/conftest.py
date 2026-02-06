"""Pytest fixtures and configuration."""

import pytest
from datetime import date
from decimal import Decimal
from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.data.factory import create_repositories


@pytest.fixture
def make_transaction():
    """Factory fixture for creating test transactions."""

    def _make(**kwargs):
        defaults = {
            "date": date.today(),
            "description": "Test Transaction",
            "amount": Decimal("100.00"),
            "type": TransactionType.EXPENSE,
            "sheet": "Main",
        }
        defaults.update(kwargs)
        return Transaction.create(**defaults)

    return _make


@pytest.fixture
def sample_transactions(make_transaction):
    """Fixture providing a list of sample transactions."""
    return [
        make_transaction(
            description="Fuel",
            amount=Decimal("50.00"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.APPROVED,
        ),
        make_transaction(
            description="Salary",
            amount=Decimal("2500.00"),
            type=TransactionType.INCOME,
            status=ApprovalStatus.AUTO,
        ),
        make_transaction(
            description="Rent",
            amount=Decimal("800.00"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.PENDING,
        ),
    ]


@pytest.fixture
async def repos(tmp_path):
    """Create repositories with temporary database."""
    db_path = tmp_path / "test.db"
    trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo = (
        await create_repositories("sqlite", db_path)
    )
    yield trans_repo, planned_repo, sheet_repo, audit_repo, attachment_repo
    await trans_repo.close()
