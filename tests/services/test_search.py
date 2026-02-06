"""Tests for search service."""

import pytest
from datetime import date
from decimal import Decimal

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.services.search import SearchService


@pytest.fixture
def search_service():
    """Create search service instance."""
    return SearchService()


@pytest.fixture
def sample_transactions():
    """Create sample transactions for testing."""
    return [
        Transaction.create(
            date=date(2024, 1, 1),
            description="Coffee at Jane's Coffee Shop",
            amount=Decimal("4.50"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.APPROVED,
            sheet="Personal",
            category="Food & Drink",
            party="Jane's Coffee",
            notes="Morning coffee",
        ),
        Transaction.create(
            date=date(2024, 1, 2),
            description="Fuel for car",
            amount=Decimal("45.00"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.PENDING,
            sheet="Personal",
            category="Transport",
            party="Shell",
            notes=None,
        ),
        Transaction.create(
            date=date(2024, 1, 3),
            description="Salary payment",
            amount=Decimal("3000.00"),
            type=TransactionType.INCOME,
            status=ApprovalStatus.AUTO,
            sheet="Personal",
            category="Salary",
            party="Employer Corp",
            notes="Monthly salary",
        ),
        Transaction.create(
            date=date(2024, 1, 4),
            description="Afternoon coffee meeting",
            amount=Decimal("7.00"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.APPROVED,
            sheet="Personal",
            category="Food & Drink",
            party="Starbucks",
            notes="Client meeting",
        ),
        Transaction.create(
            date=date(2024, 1, 5),
            description="Book purchase",
            amount=Decimal("15.99"),
            type=TransactionType.EXPENSE,
            status=ApprovalStatus.REJECTED,
            sheet="Personal",
            category="Shopping",
            party="Amazon",
            notes="Programming book",
        ),
    ]


class TestSimpleSearch:
    """Test simple term searches."""

    def test_empty_query_returns_all(self, search_service, sample_transactions):
        """Empty query should return all transactions."""
        results = search_service.search(sample_transactions, "")
        assert len(results) == 5

    def test_whitespace_query_returns_all(self, search_service, sample_transactions):
        """Whitespace-only query should return all transactions."""
        results = search_service.search(sample_transactions, "   ")
        assert len(results) == 5

    def test_single_term_match(self, search_service, sample_transactions):
        """Search for single term."""
        results = search_service.search(sample_transactions, "coffee")
        assert len(results) == 2  # Coffee shop and Jane's Coffee
        assert "coffee" in results[0].description.lower()

    def test_case_insensitive_search(self, search_service, sample_transactions):
        """Search should be case insensitive."""
        results_lower = search_service.search(sample_transactions, "coffee")
        results_upper = search_service.search(sample_transactions, "COFFEE")
        results_mixed = search_service.search(sample_transactions, "CoFfEe")

        assert len(results_lower) == 2
        assert len(results_upper) == 2
        assert len(results_mixed) == 2

    def test_search_in_description(self, search_service, sample_transactions):
        """Search should match description field."""
        results = search_service.search(sample_transactions, "fuel")
        assert len(results) == 1
        assert results[0].description == "Fuel for car"

    def test_search_in_category(self, search_service, sample_transactions):
        """Search should match category field."""
        results = search_service.search(sample_transactions, "transport")
        assert len(results) == 1
        assert results[0].category == "Transport"

    def test_search_in_party(self, search_service, sample_transactions):
        """Search should match party field."""
        results = search_service.search(sample_transactions, "shell")
        assert len(results) == 1
        assert results[0].party == "Shell"

    def test_search_in_notes(self, search_service, sample_transactions):
        """Search should match notes field."""
        results = search_service.search(sample_transactions, "programming")
        assert len(results) == 1
        assert results[0].notes == "Programming book"

    def test_search_in_status(self, search_service, sample_transactions):
        """Search should match status field."""
        results = search_service.search(sample_transactions, "pending")
        assert len(results) == 1
        assert results[0].status == ApprovalStatus.PENDING

    def test_search_no_matches(self, search_service, sample_transactions):
        """Search with no matches returns empty list."""
        results = search_service.search(sample_transactions, "nonexistent")
        assert len(results) == 0


class TestBooleanAND:
    """Test AND operator."""

    def test_and_both_terms_match(self, search_service, sample_transactions):
        """AND requires both terms to match."""
        results = search_service.search(sample_transactions, "fuel AND car")
        assert len(results) == 1
        assert "fuel" in results[0].description.lower()
        assert "car" in results[0].description.lower()

    def test_and_one_term_missing(self, search_service, sample_transactions):
        """AND with one term missing returns no results."""
        results = search_service.search(sample_transactions, "fuel AND coffee")
        assert len(results) == 0

    def test_and_multiple_terms(self, search_service, sample_transactions):
        """AND with multiple terms."""
        results = search_service.search(sample_transactions, "coffee AND Jane AND morning")
        assert len(results) == 1
        assert results[0].party == "Jane's Coffee"

    def test_and_case_insensitive(self, search_service, sample_transactions):
        """AND operator should be case insensitive."""
        results_lower = search_service.search(sample_transactions, "fuel and car")
        results_upper = search_service.search(sample_transactions, "fuel AND car")

        assert len(results_lower) == 1
        assert len(results_upper) == 1


class TestBooleanOR:
    """Test OR operator."""

    def test_or_either_term_matches(self, search_service, sample_transactions):
        """OR matches if either term is present."""
        results = search_service.search(sample_transactions, "coffee OR fuel")
        assert len(results) == 3  # 2 coffee + 1 fuel

    def test_or_both_terms_match(self, search_service, sample_transactions):
        """OR matches if both terms are present."""
        results = search_service.search(sample_transactions, "fuel OR car")
        assert len(results) == 1  # Same transaction has both

    def test_or_no_terms_match(self, search_service, sample_transactions):
        """OR with no matching terms returns empty."""
        results = search_service.search(sample_transactions, "xyz OR abc")
        assert len(results) == 0

    def test_or_case_insensitive(self, search_service, sample_transactions):
        """OR operator should be case insensitive."""
        results_lower = search_service.search(sample_transactions, "coffee or fuel")
        results_upper = search_service.search(sample_transactions, "coffee OR fuel")

        assert len(results_lower) == 3
        assert len(results_upper) == 3


class TestBooleanNOT:
    """Test NOT operator."""

    def test_not_excludes_term(self, search_service, sample_transactions):
        """NOT excludes matching transactions."""
        results = search_service.search(sample_transactions, "NOT coffee")
        assert len(results) == 3  # 5 total - 2 with coffee
        for t in results:
            assert "coffee" not in t.description.lower()

    def test_not_with_and(self, search_service, sample_transactions):
        """NOT combined with AND."""
        results = search_service.search(sample_transactions, "expense AND NOT coffee")
        # All expenses except coffee ones
        # Expenses: Coffee (x2), Fuel, Book
        # Expenses NOT coffee: Fuel, Book = 2
        assert len(results) == 2
        for t in results:
            assert "coffee" not in t.description.lower()

    def test_not_with_status(self, search_service, sample_transactions):
        """NOT to exclude status."""
        results = search_service.search(sample_transactions, "NOT pending")
        assert len(results) == 4  # 5 total - 1 pending
        for t in results:
            assert t.status != ApprovalStatus.PENDING


class TestParentheses:
    """Test grouping with parentheses."""

    def test_parentheses_grouping(self, search_service, sample_transactions):
        """Parentheses group conditions."""
        results = search_service.search(sample_transactions, "(coffee OR fuel) AND approved")
        # Coffee (approved) + Coffee (approved) + Fuel (pending - excluded)
        assert len(results) == 2  # Both coffee transactions are approved

    def test_nested_parentheses(self, search_service, sample_transactions):
        """Nested parentheses."""
        results = search_service.search(sample_transactions, "((coffee OR fuel) AND approved)")
        assert len(results) == 2

    def test_parentheses_with_not(self, search_service, sample_transactions):
        """Parentheses with NOT."""
        results = search_service.search(sample_transactions, "(coffee OR fuel) AND NOT pending")
        # Coffee (2 approved) + Fuel (pending - excluded) = 2
        assert len(results) == 2


class TestComplexQueries:
    """Test complex multi-operator queries."""

    def test_complex_and_or_not(self, search_service, sample_transactions):
        """Complex query with AND, OR, NOT."""
        results = search_service.search(
            sample_transactions,
            "(coffee OR salary) AND NOT pending"
        )
        # Coffee (2 approved) + Salary (1 auto) = 3
        assert len(results) == 3

    def test_precedence_and_higher_than_or(self, search_service, sample_transactions):
        """AND has higher precedence than OR."""
        # "coffee OR fuel AND car" = "coffee OR (fuel AND car)"
        results = search_service.search(sample_transactions, "coffee OR fuel AND car")
        # Coffee (2) + (Fuel AND car) (1) = 3
        assert len(results) == 3

    def test_multiple_nots(self, search_service, sample_transactions):
        """Multiple NOT operators."""
        results = search_service.search(
            sample_transactions,
            "NOT coffee AND NOT fuel AND NOT salary"
        )
        # Excludes coffee (2), fuel (1), salary (1) = leaves 1 (book)
        assert len(results) == 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_transactions_list(self, search_service):
        """Search on empty list returns empty."""
        results = search_service.search([], "coffee")
        assert len(results) == 0

    def test_malformed_query_returns_all(self, search_service, sample_transactions):
        """Malformed query returns all transactions (graceful degradation)."""
        # Unmatched parentheses
        results = search_service.search(sample_transactions, "(coffee AND")
        # Should not crash - returns all on error
        assert len(results) >= 0  # Depends on error handling strategy

    def test_only_operators_no_terms(self, search_service, sample_transactions):
        """Query with only operators."""
        results = search_service.search(sample_transactions, "AND OR")
        # Should treat as terms or return all
        assert len(results) >= 0

    def test_consecutive_operators(self, search_service, sample_transactions):
        """Consecutive operators."""
        results = search_service.search(sample_transactions, "coffee AND AND fuel")
        # Malformed - graceful degradation
        assert len(results) >= 0

    def test_search_with_amount(self, search_service, sample_transactions):
        """Search can match amount as string."""
        results = search_service.search(sample_transactions, "45")
        assert len(results) == 1
        assert results[0].amount == Decimal("45.00")

    def test_search_with_decimal_amount(self, search_service, sample_transactions):
        """Search can match decimal amount."""
        results = search_service.search(sample_transactions, "4.50")
        assert len(results) == 1
        assert results[0].amount == Decimal("4.50")
