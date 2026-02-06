"""Export service for exporting transactions to various formats."""

from abc import ABC, abstractmethod
from pathlib import Path
from datetime import date
from decimal import Decimal
from typing import Optional
import csv
from io import StringIO

from fidra.domain.models import Transaction, TransactionType, ApprovalStatus
from fidra.services.balance import BalanceService


class ExportStrategy(ABC):
    """Abstract base class for export strategies."""

    @abstractmethod
    def export(
        self,
        transactions: list[Transaction],
        output_path: Path,
        include_balance: bool = False,
    ) -> None:
        """Export transactions to file.

        Args:
            transactions: List of transactions to export
            output_path: Path to output file
            include_balance: Whether to include running balance column
        """
        pass

    @abstractmethod
    def get_extension(self) -> str:
        """Get file extension for this format.

        Returns:
            File extension (e.g., "csv", "md", "pdf")
        """
        pass


class CSVExporter(ExportStrategy):
    """Export transactions to CSV format."""

    def __init__(self, balance_service: Optional[BalanceService] = None):
        """Initialize CSV exporter.

        Args:
            balance_service: Balance service for calculating running balances
        """
        self.balance_service = balance_service or BalanceService()

    def export(
        self,
        transactions: list[Transaction],
        output_path: Path,
        include_balance: bool = False,
    ) -> None:
        """Export transactions to CSV file.

        Args:
            transactions: List of transactions to export
            output_path: Path to output CSV file
            include_balance: Whether to include running balance column
        """
        # Sort transactions by date
        sorted_transactions = sorted(transactions, key=lambda t: (t.date, t.created_at))

        # Calculate running balances if needed
        balances = {}
        if include_balance:
            balances = self.balance_service.compute_running_balances(sorted_transactions)

        # Build CSV
        with output_path.open('w', newline='', encoding='utf-8') as f:
            if include_balance:
                fieldnames = [
                    'Date', 'Description', 'Amount', 'Type', 'Status',
                    'Category', 'Party', 'Notes', 'Balance'
                ]
            else:
                fieldnames = [
                    'Date', 'Description', 'Amount', 'Type', 'Status',
                    'Category', 'Party', 'Notes'
                ]

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for trans in sorted_transactions:
                row = {
                    'Date': trans.date.strftime('%Y-%m-%d'),
                    'Description': trans.description,
                    'Amount': f'£{trans.amount:.2f}',
                    'Type': trans.type.value,
                    'Status': trans.status.value,
                    'Category': trans.category or '',
                    'Party': trans.party or '',
                    'Notes': trans.notes or '',
                }

                if include_balance:
                    balance = balances.get(str(trans.id), Decimal('0'))
                    row['Balance'] = f'£{balance:.2f}'

                writer.writerow(row)

    def get_extension(self) -> str:
        """Get file extension for CSV format."""
        return "csv"


class MarkdownExporter(ExportStrategy):
    """Export transactions to Markdown format with monthly sections."""

    def __init__(self, balance_service: Optional[BalanceService] = None):
        """Initialize Markdown exporter.

        Args:
            balance_service: Balance service for calculating running balances
        """
        self.balance_service = balance_service or BalanceService()

    def export(
        self,
        transactions: list[Transaction],
        output_path: Path,
        include_balance: bool = False,
    ) -> None:
        """Export transactions to Markdown file.

        Args:
            transactions: List of transactions to export
            output_path: Path to output Markdown file
            include_balance: Whether to include running balance column
        """
        # Sort transactions by date
        sorted_transactions = sorted(transactions, key=lambda t: (t.date, t.created_at))

        # Calculate running balances if needed
        balances = {}
        if include_balance:
            balances = self.balance_service.compute_running_balances(sorted_transactions)

        # Group transactions by month
        monthly_groups = {}
        for trans in sorted_transactions:
            month_key = trans.date.strftime('%Y-%m')
            if month_key not in monthly_groups:
                monthly_groups[month_key] = []
            monthly_groups[month_key].append(trans)

        # Build Markdown
        lines = []
        lines.append("# Transaction Report\n")
        lines.append(f"**Generated**: {date.today().strftime('%Y-%m-%d')}\n")
        lines.append(f"**Total Transactions**: {len(sorted_transactions)}\n")
        lines.append("---\n")

        for month_key in sorted(monthly_groups.keys(), reverse=True):
            month_trans = monthly_groups[month_key]
            month_date = date.fromisoformat(f"{month_key}-01")
            month_name = month_date.strftime('%B %Y')

            lines.append(f"\n## {month_name}\n")

            # Month summary
            income = sum(t.amount for t in month_trans if t.type == TransactionType.INCOME)
            expenses = sum(t.amount for t in month_trans if t.type == TransactionType.EXPENSE)
            net = income - expenses

            lines.append(f"**Income**: £{income:.2f}  ")
            lines.append(f"**Expenses**: £{expenses:.2f}  ")
            lines.append(f"**Net**: £{net:.2f}\n")

            # Transaction table
            if include_balance:
                lines.append("| Date | Description | Amount | Type | Status | Category | Party | Balance |")
                lines.append("|------|-------------|--------|------|--------|----------|-------|---------|")
            else:
                lines.append("| Date | Description | Amount | Type | Status | Category | Party |")
                lines.append("|------|-------------|--------|------|--------|----------|-------|")

            for trans in month_trans:
                date_str = trans.date.strftime('%Y-%m-%d')
                amount_str = f'£{trans.amount:.2f}'
                category = trans.category or '-'
                party = trans.party or '-'

                if include_balance:
                    balance = balances.get(str(trans.id), Decimal('0'))
                    balance_str = f'£{balance:.2f}'
                    lines.append(
                        f"| {date_str} | {trans.description} | {amount_str} | "
                        f"{trans.type.value} | {trans.status.value} | {category} | {party} | {balance_str} |"
                    )
                else:
                    lines.append(
                        f"| {date_str} | {trans.description} | {amount_str} | "
                        f"{trans.type.value} | {trans.status.value} | {category} | {party} |"
                    )

            lines.append("")

        # Write to file
        output_path.write_text('\n'.join(lines), encoding='utf-8')

    def get_extension(self) -> str:
        """Get file extension for Markdown format."""
        return "md"


class PDFExporter(ExportStrategy):
    """Export transactions to professional branded PDF using ReportLab."""

    def __init__(self, balance_service: Optional[BalanceService] = None):
        """Initialize PDF exporter.

        Args:
            balance_service: Balance service for calculating running balances
        """
        self.balance_service = balance_service or BalanceService()

    def export(
        self,
        transactions: list[Transaction],
        output_path: Path,
        include_balance: bool = False,
    ) -> None:
        """Export transactions to PDF file.

        Args:
            transactions: List of transactions to export
            output_path: Path to output PDF file
            include_balance: Whether to include running balance column
        """
        from fidra.services.pdf_generator import FidraPDFGenerator

        # Calculate balances if requested
        balances = None
        if include_balance:
            balances = self.balance_service.compute_running_balances(transactions)

        # Generate professional PDF
        generator = FidraPDFGenerator()
        generator.generate_transaction_report(
            transactions,
            output_path,
            title="Transaction Report",
            include_summary=True,
            balances=balances,
        )

    def get_extension(self) -> str:
        """Get file extension for PDF format."""
        return "pdf"


class ExportService:
    """Service for exporting transactions to various formats.

    Provides a facade over different export strategies.
    """

    def __init__(self, balance_service: Optional[BalanceService] = None):
        """Initialize export service.

        Args:
            balance_service: Balance service for calculating running balances
        """
        self.balance_service = balance_service or BalanceService()

        # Available exporters
        self.exporters = {
            'csv': CSVExporter(self.balance_service),
            'markdown': MarkdownExporter(self.balance_service),
            'pdf': PDFExporter(self.balance_service),
        }

    def export(
        self,
        transactions: list[Transaction],
        output_path: Path,
        format: str,
        include_balance: bool = False,
    ) -> None:
        """Export transactions to file.

        Args:
            transactions: List of transactions to export
            output_path: Path to output file
            format: Export format ('csv', 'markdown', 'pdf')
            include_balance: Whether to include running balance column

        Raises:
            ValueError: If format is not supported
        """
        if format not in self.exporters:
            raise ValueError(f"Unsupported format: {format}")

        exporter = self.exporters[format]
        exporter.export(transactions, output_path, include_balance)

    def get_supported_formats(self) -> list[str]:
        """Get list of supported export formats.

        Returns:
            List of format names
        """
        return list(self.exporters.keys())

    def export_to_string(
        self,
        transactions: list[Transaction],
        format: str,
        include_balance: bool = False,
    ) -> str:
        """Export transactions to string (for clipboard).

        Args:
            transactions: List of transactions to export
            format: Export format ('csv', 'markdown')
            include_balance: Whether to include running balance column

        Returns:
            Exported data as string

        Raises:
            ValueError: If format is not supported or cannot export to string
        """
        if format == 'pdf':
            raise ValueError("PDF format cannot be exported to string")

        # Use StringIO for in-memory export
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(mode='w', suffix=f'.{format}', delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            self.export(transactions, tmp_path, format, include_balance)
            content = tmp_path.read_text(encoding='utf-8')
            return content
        finally:
            tmp_path.unlink()

    def export_to_tsv(
        self,
        transactions: list[Transaction],
        include_balance: bool = False,
    ) -> str:
        """Export transactions to TSV format (for Excel paste).

        Args:
            transactions: List of transactions to export
            include_balance: Whether to include running balance column

        Returns:
            TSV-formatted string
        """
        # Sort transactions by date
        sorted_transactions = sorted(transactions, key=lambda t: (t.date, t.created_at))

        # Calculate running balances if needed
        balances = {}
        if include_balance:
            balances = self.balance_service.compute_running_balances(sorted_transactions)

        # Build TSV
        output = StringIO()
        if include_balance:
            output.write("Date\tDescription\tAmount\tType\tStatus\tCategory\tParty\tNotes\tBalance\n")
        else:
            output.write("Date\tDescription\tAmount\tType\tStatus\tCategory\tParty\tNotes\n")

        for trans in sorted_transactions:
            row = [
                trans.date.strftime('%Y-%m-%d'),
                trans.description,
                f'{trans.amount:.2f}',
                trans.type.value,
                trans.status.value,
                trans.category or '',
                trans.party or '',
                trans.notes or '',
            ]

            if include_balance:
                balance = balances.get(str(trans.id), Decimal('0'))
                row.append(f'{balance:.2f}')

            output.write('\t'.join(row) + '\n')

        return output.getvalue()
