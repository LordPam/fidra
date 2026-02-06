"""Tests for report/export balance values in table outputs."""

from datetime import date
from decimal import Decimal

from fidra.domain.models import ApprovalStatus, TransactionType
from fidra.services.balance import BalanceService
from fidra.services.export import CSVExporter, ExportService, MarkdownExporter
from fidra.services.report_builder import ReportBuilder


def _sample_transactions(make_transaction):
    """Create a deterministic transaction sequence for running balance tests."""
    t1 = make_transaction(
        date=date(2024, 1, 1),
        type=TransactionType.INCOME,
        amount=Decimal("1000.00"),
        status=ApprovalStatus.AUTO,
        description="Income",
    )
    t2 = make_transaction(
        date=date(2024, 1, 2),
        type=TransactionType.EXPENSE,
        amount=Decimal("200.00"),
        status=ApprovalStatus.APPROVED,
        description="Expense 1",
    )
    t3 = make_transaction(
        date=date(2024, 1, 3),
        type=TransactionType.EXPENSE,
        amount=Decimal("300.00"),
        status=ApprovalStatus.APPROVED,
        description="Expense 2",
    )
    return [t1, t2, t3]


def test_report_builder_transaction_table_shows_running_balances(make_transaction):
    """Report builder transaction table should show computed running balances."""
    builder = ReportBuilder(BalanceService())
    table = builder._generate_transaction_table(_sample_transactions(make_transaction))

    assert "£1,000.00" in table
    assert "£800.00" in table
    assert "£500.00" in table


def test_csv_exporter_running_balance_column(make_transaction, tmp_path):
    """CSV export should include correct running balance values."""
    exporter = CSVExporter(BalanceService())
    output = tmp_path / "report.csv"

    exporter.export(_sample_transactions(make_transaction), output, include_balance=True)
    content = output.read_text(encoding="utf-8")

    assert "Balance" in content
    assert "£1000.00" in content
    assert "£800.00" in content
    assert "£500.00" in content


def test_markdown_and_tsv_exports_running_balance_column(make_transaction, tmp_path):
    """Markdown and TSV export paths should include correct running balances."""
    transactions = _sample_transactions(make_transaction)
    markdown_exporter = MarkdownExporter(BalanceService())
    md_output = tmp_path / "report.md"

    markdown_exporter.export(transactions, md_output, include_balance=True)
    markdown_content = md_output.read_text(encoding="utf-8")

    assert "£1000.00" in markdown_content
    assert "£800.00" in markdown_content
    assert "£500.00" in markdown_content

    tsv = ExportService(BalanceService()).export_to_tsv(transactions, include_balance=True)
    assert "1000.00" in tsv
    assert "800.00" in tsv
    assert "500.00" in tsv
