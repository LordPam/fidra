# Fidra 2.0 - Application Blueprint

> A comprehensive architectural blueprint for rebuilding Fidra as a modern, maintainable financial management application using Python and Qt (PySide6).

---

## Table of Contents

1. [Overview](#1-overview)
2. [Technology Stack](#2-technology-stack)
3. [Architecture](#3-architecture)
4. [Data Models](#4-data-models)
5. [Data Layer](#5-data-layer)
6. [Core Services](#6-core-services)
7. [State Management](#7-state-management)
8. [User Interface](#8-user-interface)
9. [Theme System](#9-theme-system)
10. [Feature Specifications](#10-feature-specifications)
11. [Keyboard Shortcuts](#11-keyboard-shortcuts)
12. [File Structure](#12-file-structure)
13. [Implementation Phases](#13-implementation-phases)
14. [Testing Strategy](#14-testing-strategy)

---

## 1. Overview

### 1.1 Purpose

Fidra is a local-first financial ledger application designed for treasurers and individuals who need to track income, expenses, planned transactions, and generate financial reports. It provides:

- **Dashboard**: At-a-glance overview with balance, charts, and upcoming transactions
- **Transaction Management**: Add, edit, delete, and bulk-edit transactions
- **Planned Transactions**: Future expected transactions (one-time or recurring) with optional auto-expansion
- **Approval Workflow**: Pending → Approved/Rejected status for expenses
- **Balance Tracking**: Real-time running balance calculations
- **Search & Filter**: Boolean query search across all fields
- **Forecasting**: Project future balances based on planned transactions
- **Reports & Charts**: Visual breakdowns and exportable reports
- **Multi-Sheet Support**: Organize transactions across multiple accounts/sheets
- **Undo/Redo**: Full operation history with unlimited undo
- **Concurrent Editing**: Optimistic concurrency with conflict resolution

### 1.2 Design Principles

1. **Local-First**: All data stored locally, no cloud dependency
2. **Separation of Concerns**: Clean layered architecture
3. **Reactive UI**: State changes automatically update the interface
4. **Immutable Data**: Transaction objects are immutable; updates create new instances
5. **Command Pattern**: All mutations via commands for undo/redo
6. **Type Safety**: Full type annotations throughout
7. **Testability**: Dependency injection enables unit testing

---

## 2. Technology Stack

### 2.1 Core Technologies

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Language** | Python 3.11+ | Type hints, dataclasses, async/await |
| **UI Framework** | PySide6 (Qt 6) | Professional widgets, QSS styling, cross-platform |
| **Async** | qasync | Qt-asyncio integration |
| **Data Validation** | Pydantic v2 | Fast validation, serialization |
| **Database** | SQLite | Local, reliable, SQL queries |
| **Excel I/O** | openpyxl | Excel read/write compatibility |
| **Charts** | pyqtgraph | Native Qt charts, theme-aware, fast rendering |
| **PDF Export** | weasyprint or reportlab | Professional PDF generation |
| **Testing** | pytest + pytest-qt | Qt-aware testing |

### 2.2 Development Tools

| Tool | Purpose |
|------|---------|
| **uv** | Fast package management |
| **ruff** | Linting and formatting |
| **mypy** | Static type checking |
| **pre-commit** | Git hooks for quality |
| **PyInstaller** | Executable packaging |

---

## 3. Architecture

### 3.1 Layer Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         PRESENTATION                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Views     │  │   Widgets   │  │   Dialogs   │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                      │
│         └────────────────┼────────────────┘                      │
│                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    VIEW MODELS                             │  │
│  │  (Reactive state, UI logic, command dispatch)             │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         APPLICATION                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Commands   │  │   Queries   │  │   Events    │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                      │
│         └────────────────┼────────────────┘                      │
│                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                      SERVICES                              │  │
│  │  Balance │ Forecast │ Search │ Undo │ Export │ Settings   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                           DOMAIN                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                       MODELS                               │  │
│  │  Transaction │ PlannedTemplate │ Sheet │ Category         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        INFRASTRUCTURE                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ Repository  │  │ File Watch  │  │  Settings   │              │
│  │ (SQLite/XL) │  │  Service    │  │  Storage    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Key Patterns

| Pattern | Usage |
|---------|-------|
| **Repository** | Abstract data access (SQLite, Excel) |
| **Command** | All mutations for undo/redo |
| **Observer** | Reactive state updates |
| **Factory** | Repository creation |
| **Strategy** | Export formats |
| **Adapter** | Excel ↔ Repository interface |

---

## 4. Data Models

### 4.1 Transaction

The core entity representing a single financial transaction.

```python
# fidra/domain/models.py

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

class TransactionType(Enum):
    INCOME = "income"
    EXPENSE = "expense"

class ApprovalStatus(Enum):
    AUTO = "--"           # Auto-approved (income)
    PENDING = "pending"   # Awaiting approval
    APPROVED = "approved" # Approved
    REJECTED = "rejected" # Rejected
    PLANNED = "planned"   # Generated from template

@dataclass(frozen=True, slots=True)
class Transaction:
    """Immutable transaction record."""

    id: UUID
    date: date
    description: str
    amount: Decimal
    type: TransactionType
    status: ApprovalStatus
    sheet: str
    category: Optional[str] = None
    party: Optional[str] = None
    notes: Optional[str] = None
    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: Optional[datetime] = None
    modified_by: Optional[str] = None

    def __post_init__(self):
        # Validate amount is positive
        if self.amount <= 0:
            raise ValueError("Amount must be positive")

    def with_updates(self, **changes) -> "Transaction":
        """Create new instance with updated fields."""
        from dataclasses import asdict
        current = asdict(self)
        current.update(changes)
        current['version'] = self.version + 1
        current['modified_at'] = datetime.now()
        return Transaction(**current)

    @classmethod
    def create(
        cls,
        date: date,
        description: str,
        amount: Decimal,
        type: TransactionType,
        sheet: str,
        **kwargs
    ) -> "Transaction":
        """Factory method with sensible defaults."""
        status = kwargs.pop('status', None)
        if status is None:
            status = ApprovalStatus.AUTO if type == TransactionType.INCOME else ApprovalStatus.PENDING

        return cls(
            id=uuid4(),
            date=date,
            description=description,
            amount=amount,
            type=type,
            status=status,
            sheet=sheet,
            **kwargs
        )
```

### 4.2 Planned Template

Represents a future expected transaction. Can be either:
- **One-time**: A single expected transaction on a specific date (default)
- **Recurring**: Repeats on a schedule until an end date or occurrence count

```python
@dataclass(frozen=True, slots=True)
class Frequency(Enum):
    ONCE = "once"        # One-time, no recurrence (default)
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

@dataclass(frozen=True, slots=True)
class PlannedTemplate:
    """Template for future expected transactions (one-time or recurring)."""

    id: UUID
    start_date: date
    description: str
    amount: Decimal
    type: TransactionType
    target_sheet: str
    frequency: Frequency = Frequency.ONCE  # Default to one-time
    category: Optional[str] = None
    party: Optional[str] = None
    end_date: Optional[date] = None        # For recurring: when to stop
    occurrence_count: Optional[int] = None  # Alternative: stop after N occurrences
    skipped_dates: tuple[date, ...] = ()   # Instances to exclude from projections
    fulfilled_dates: tuple[date, ...] = () # Instances converted to actual transactions
    version: int = 1
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def is_recurring(self) -> bool:
        """Check if this is a recurring template."""
        return self.frequency != Frequency.ONCE

    def is_skipped(self, instance_date: date) -> bool:
        """Check if a specific instance is skipped."""
        return instance_date in self.skipped_dates

    def is_fulfilled(self, instance_date: date) -> bool:
        """Check if a specific instance has been converted to actual."""
        return instance_date in self.fulfilled_dates

    def with_updates(self, **changes) -> "PlannedTemplate":
        """Create new instance with updated fields."""
        from dataclasses import asdict
        current = asdict(self)
        current.update(changes)
        current['version'] = self.version + 1
        return PlannedTemplate(**current)

    def skip_instance(self, instance_date: date) -> "PlannedTemplate":
        """Mark an instance as skipped."""
        if instance_date in self.skipped_dates:
            return self
        return self.with_updates(
            skipped_dates=self.skipped_dates + (instance_date,)
        )

    def unskip_instance(self, instance_date: date) -> "PlannedTemplate":
        """Remove skip marking from an instance."""
        if instance_date not in self.skipped_dates:
            return self
        return self.with_updates(
            skipped_dates=tuple(d for d in self.skipped_dates if d != instance_date)
        )

    def mark_fulfilled(self, instance_date: date) -> "PlannedTemplate":
        """Mark an instance as converted to actual transaction."""
        if instance_date in self.fulfilled_dates:
            return self
        return self.with_updates(
            fulfilled_dates=self.fulfilled_dates + (instance_date,)
        )

    def expand(self, horizon: date) -> list[Transaction]:
        """Generate transaction instances up to horizon date.

        For one-time: returns single transaction if start_date <= horizon
        For recurring: returns all occurrences up to horizon or end_date/count
        Excludes skipped instances from the result.
        """
        # Implementation in ForecastService
        ...
```

### 4.3 Sheet

Represents an account or transaction category sheet.

```python
@dataclass(frozen=True, slots=True)
class Sheet:
    """A sheet/account for organizing transactions."""

    id: UUID
    name: str
    is_virtual: bool = False  # True for "All Transactions"
    is_planned: bool = False  # True for "Planned_Transactions"
    created_at: datetime = field(default_factory=datetime.now)
```

### 4.4 Category

```python
@dataclass(frozen=True, slots=True)
class Category:
    """Transaction category."""

    id: UUID
    name: str
    type: TransactionType  # Income or expense category
    color: Optional[str] = None
```

### 4.5 Application Settings

```python
from pydantic import BaseModel, Field
from pathlib import Path

class ProfileSettings(BaseModel):
    name: str = ""
    initials: str = ""

class ThemeSettings(BaseModel):
    mode: str = "dark"  # "dark" | "light" | "system"

class StorageSettings(BaseModel):
    backend: str = "sqlite"  # "sqlite" | "excel"
    last_file: Optional[Path] = None

class LoggingSettings(BaseModel):
    level: str = "INFO"

class ForecastSettings(BaseModel):
    horizon_days: int = 90
    include_past_planned: bool = True

class AppSettings(BaseModel):
    """Application settings with validation."""

    profile: ProfileSettings = Field(default_factory=ProfileSettings)
    theme: ThemeSettings = Field(default_factory=ThemeSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    forecast: ForecastSettings = Field(default_factory=ForecastSettings)
    income_categories: list[str] = Field(default_factory=lambda: [
        "Membership Dues", "Event Income", "Donations", "Grants", "Other Income"
    ])
    expense_categories: list[str] = Field(default_factory=lambda: [
        "Equipment", "Training", "Events", "Administration", "Travel", "Other"
    ])
    example_descriptions: list[str] = Field(default_factory=list)
    example_parties: list[str] = Field(default_factory=list)
```

---

## 5. Data Layer

### 5.1 Repository Interface

```python
# fidra/data/repository.py

from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator
from uuid import UUID
from domain.models import Transaction, PlannedTemplate, Sheet

class TransactionRepository(ABC):
    """Abstract interface for transaction storage."""

    @abstractmethod
    async def get_all(self, sheet: Optional[str] = None) -> list[Transaction]:
        """Get all transactions, optionally filtered by sheet."""
        ...

    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[Transaction]:
        """Get a single transaction by ID."""
        ...

    @abstractmethod
    async def save(self, transaction: Transaction) -> Transaction:
        """Save (insert or update) a transaction. Returns saved instance."""
        ...

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        """Delete a transaction. Returns True if deleted."""
        ...

    @abstractmethod
    async def bulk_save(self, transactions: list[Transaction]) -> list[Transaction]:
        """Save multiple transactions atomically."""
        ...

    @abstractmethod
    async def bulk_delete(self, ids: list[UUID]) -> int:
        """Delete multiple transactions. Returns count deleted."""
        ...

    @abstractmethod
    async def get_version(self, id: UUID) -> Optional[int]:
        """Get current version for optimistic concurrency."""
        ...

class PlannedRepository(ABC):
    """Abstract interface for planned template storage."""

    @abstractmethod
    async def get_all(self) -> list[PlannedTemplate]:
        ...

    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[PlannedTemplate]:
        ...

    @abstractmethod
    async def save(self, template: PlannedTemplate) -> PlannedTemplate:
        ...

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        ...

class SheetRepository(ABC):
    """Abstract interface for sheet management."""

    @abstractmethod
    async def get_all(self) -> list[Sheet]:
        ...

    @abstractmethod
    async def create(self, name: str) -> Sheet:
        ...

    @abstractmethod
    async def delete(self, id: UUID) -> bool:
        ...
```

### 5.2 SQLite Implementation

```python
# fidra/data/sqlite_repository.py

import aiosqlite
from pathlib import Path
from typing import Optional
from uuid import UUID
from domain.models import Transaction, TransactionType, ApprovalStatus

class SQLiteTransactionRepository(TransactionRepository):
    """SQLite implementation of TransactionRepository."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._ensure_schema()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    async def _ensure_schema(self) -> None:
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                sheet TEXT NOT NULL,
                category TEXT,
                party TEXT,
                notes TEXT,
                version INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                modified_at TEXT,
                modified_by TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
            CREATE INDEX IF NOT EXISTS idx_transactions_sheet ON transactions(sheet);
            CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
            CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);

            CREATE TABLE IF NOT EXISTS planned_templates (
                id TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount TEXT NOT NULL,
                type TEXT NOT NULL,
                frequency TEXT NOT NULL,
                target_sheet TEXT NOT NULL,
                category TEXT,
                party TEXT,
                end_date TEXT,
                occurrence_count INTEGER,
                version INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sheets (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                is_virtual INTEGER DEFAULT 0,
                is_planned INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
        """)
        await self._conn.commit()

    async def get_all(self, sheet: Optional[str] = None) -> list[Transaction]:
        query = "SELECT * FROM transactions"
        params = []
        if sheet and sheet != "All Transactions":
            query += " WHERE sheet = ?"
            params.append(sheet)
        query += " ORDER BY date DESC, created_at DESC"

        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_transaction(row) for row in rows]

    async def save(self, transaction: Transaction) -> Transaction:
        await self._conn.execute("""
            INSERT OR REPLACE INTO transactions
            (id, date, description, amount, type, status, sheet,
             category, party, notes, version, created_at, modified_at, modified_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(transaction.id),
            transaction.date.isoformat(),
            transaction.description,
            str(transaction.amount),
            transaction.type.value,
            transaction.status.value,
            transaction.sheet,
            transaction.category,
            transaction.party,
            transaction.notes,
            transaction.version,
            transaction.created_at.isoformat(),
            transaction.modified_at.isoformat() if transaction.modified_at else None,
            transaction.modified_by
        ))
        await self._conn.commit()
        return transaction

    def _row_to_transaction(self, row) -> Transaction:
        return Transaction(
            id=UUID(row[0]),
            date=date.fromisoformat(row[1]),
            description=row[2],
            amount=Decimal(row[3]),
            type=TransactionType(row[4]),
            status=ApprovalStatus(row[5]),
            sheet=row[6],
            category=row[7],
            party=row[8],
            notes=row[9],
            version=row[10],
            created_at=datetime.fromisoformat(row[11]),
            modified_at=datetime.fromisoformat(row[12]) if row[12] else None,
            modified_by=row[13]
        )
```

### 5.3 Excel Adapter

```python
# fidra/data/excel_adapter.py

from pathlib import Path
from openpyxl import Workbook, load_workbook
from domain.models import Transaction

class ExcelAdapter(TransactionRepository):
    """Adapts Excel files to Repository interface."""

    COLUMNS = [
        "Date", "Description", "Amount", "Type",
        "Category", "Party", "Status", "Balance", "Notes"
    ]

    def __init__(self, file_path: Path):
        self._path = file_path
        self._workbook: Optional[Workbook] = None

    async def connect(self) -> None:
        if self._path.exists():
            self._workbook = load_workbook(self._path)
        else:
            self._workbook = Workbook()
            self._initialize_sheets()
            self._workbook.save(self._path)

    def _initialize_sheets(self) -> None:
        # Remove default sheet
        if "Sheet" in self._workbook.sheetnames:
            del self._workbook["Sheet"]

        # Create default sheets
        for name in ["Main_Transactions", "Planned_Transactions"]:
            ws = self._workbook.create_sheet(name)
            ws.append(self.COLUMNS)

    # ... implement repository methods with Excel operations
```

### 5.4 Repository Factory

```python
# fidra/data/factory.py

from pathlib import Path
from data.repository import TransactionRepository
from data.sqlite_repository import SQLiteTransactionRepository
from data.excel_adapter import ExcelAdapter

async def create_repository(
    backend: str,
    file_path: Path
) -> TransactionRepository:
    """Factory function to create appropriate repository."""

    if backend == "sqlite":
        repo = SQLiteTransactionRepository(file_path)
    elif backend == "excel":
        repo = ExcelAdapter(file_path)
    else:
        raise ValueError(f"Unknown backend: {backend}")

    await repo.connect()
    return repo
```

---

## 6. Core Services

### 6.1 Balance Service

```python
# fidra/services/balance.py

from decimal import Decimal
from domain.models import Transaction, TransactionType, ApprovalStatus

class BalanceService:
    """Calculates balances from transactions."""

    # Statuses that count toward balance
    COUNTABLE_INCOME = {ApprovalStatus.AUTO, ApprovalStatus.APPROVED, ApprovalStatus.PLANNED}
    COUNTABLE_EXPENSE = {ApprovalStatus.APPROVED, ApprovalStatus.PLANNED}

    def compute_total(self, transactions: list[Transaction]) -> Decimal:
        """Compute net balance from transactions."""
        total = Decimal("0")

        for t in transactions:
            if t.type == TransactionType.INCOME and t.status in self.COUNTABLE_INCOME:
                total += t.amount
            elif t.type == TransactionType.EXPENSE and t.status in self.COUNTABLE_EXPENSE:
                total -= t.amount

        return total

    def compute_running_balances(
        self,
        transactions: list[Transaction]
    ) -> dict[str, Decimal]:
        """Compute running balance for each transaction.

        Returns dict mapping transaction ID to running balance.
        Transactions should be sorted by date ascending.
        """
        balances = {}
        running = Decimal("0")

        for t in sorted(transactions, key=lambda x: (x.date, x.created_at)):
            if t.type == TransactionType.INCOME and t.status in self.COUNTABLE_INCOME:
                running += t.amount
            elif t.type == TransactionType.EXPENSE and t.status in self.COUNTABLE_EXPENSE:
                running -= t.amount

            balances[str(t.id)] = running

        return balances

    def compute_pending_total(self, transactions: list[Transaction]) -> Decimal:
        """Compute total of pending expenses."""
        return sum(
            t.amount for t in transactions
            if t.type == TransactionType.EXPENSE and t.status == ApprovalStatus.PENDING
        )
```

### 6.2 Forecast Service

```python
# fidra/services/forecast.py

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from domain.models import (
    Transaction, PlannedTemplate, TransactionType,
    ApprovalStatus, Frequency
)

class ForecastService:
    """Expands planned templates and projects future balances."""

    def expand_template(
        self,
        template: PlannedTemplate,
        horizon: date,
        include_past: bool = False
    ) -> list[Transaction]:
        """Generate transaction instances from a template."""
        instances = []
        current = template.start_date
        today = date.today()
        count = 0

        while current <= horizon:
            # Skip past dates unless include_past
            if current >= today or include_past:
                instances.append(self._create_instance(template, current))

            # Check occurrence limit
            count += 1
            if template.occurrence_count and count >= template.occurrence_count:
                break

            # Check end date
            if template.end_date and current >= template.end_date:
                break

            # Advance to next occurrence
            current = self._next_occurrence(current, template.frequency)

        return instances

    def _next_occurrence(self, current: date, frequency: Frequency) -> date:
        """Calculate next occurrence date."""
        match frequency:
            case Frequency.ONCE:
                return date.max  # No more occurrences
            case Frequency.WEEKLY:
                return current + timedelta(weeks=1)
            case Frequency.BIWEEKLY:
                return current + timedelta(weeks=2)
            case Frequency.MONTHLY:
                return current + relativedelta(months=1)
            case Frequency.QUARTERLY:
                return current + relativedelta(months=3)
            case Frequency.YEARLY:
                return current + relativedelta(years=1)

    def _create_instance(
        self,
        template: PlannedTemplate,
        occurrence_date: date
    ) -> Transaction:
        """Create a transaction instance from template."""
        from uuid import uuid5, NAMESPACE_OID

        # Deterministic ID based on template + date
        instance_id = uuid5(
            NAMESPACE_OID,
            f"{template.id}_{occurrence_date.isoformat()}"
        )

        return Transaction(
            id=instance_id,
            date=occurrence_date,
            description=template.description,
            amount=template.amount,
            type=template.type,
            status=ApprovalStatus.PLANNED,
            sheet=template.target_sheet,
            category=template.category,
            party=template.party
        )

    def project_balance(
        self,
        current_balance: Decimal,
        planned_instances: list[Transaction],
        target_date: date
    ) -> Decimal:
        """Project balance at a future date."""
        balance = current_balance

        for t in planned_instances:
            if t.date <= target_date:
                if t.type == TransactionType.INCOME:
                    balance += t.amount
                else:
                    balance -= t.amount

        return balance
```

### 6.3 Search Service

```python
# fidra/services/search.py

import re
from typing import Callable
from domain.models import Transaction

class SearchService:
    """Boolean search with AND, OR, NOT operators."""

    OPERATORS = {'AND', 'OR', 'NOT'}
    PRECEDENCE = {'NOT': 3, 'AND': 2, 'OR': 1}

    def search(
        self,
        transactions: list[Transaction],
        query: str
    ) -> list[Transaction]:
        """Filter transactions by search query."""
        if not query.strip():
            return transactions

        tokens = self._tokenize(query)
        rpn = self._to_rpn(tokens)
        matcher = self._compile_rpn(rpn)

        return [t for t in transactions if matcher(t)]

    def _tokenize(self, query: str) -> list[str]:
        """Split query into tokens."""
        # Match parentheses, operators, and quoted/unquoted terms
        pattern = r'[()]|"[^"]*"|\'[^\']*\'|\S+'
        tokens = re.findall(pattern, query)

        # Normalize operators to uppercase
        return [
            t.upper() if t.upper() in self.OPERATORS else t.strip('"\'')
            for t in tokens
        ]

    def _to_rpn(self, tokens: list[str]) -> list[str]:
        """Convert infix to Reverse Polish Notation (Shunting-yard)."""
        output = []
        operator_stack = []

        for token in tokens:
            if token == '(':
                operator_stack.append(token)
            elif token == ')':
                while operator_stack and operator_stack[-1] != '(':
                    output.append(operator_stack.pop())
                if operator_stack:
                    operator_stack.pop()  # Remove '('
            elif token in self.OPERATORS:
                while (operator_stack and
                       operator_stack[-1] in self.OPERATORS and
                       self.PRECEDENCE[operator_stack[-1]] >= self.PRECEDENCE[token]):
                    output.append(operator_stack.pop())
                operator_stack.append(token)
            else:
                output.append(token)

        while operator_stack:
            output.append(operator_stack.pop())

        return output

    def _compile_rpn(self, rpn: list[str]) -> Callable[[Transaction], bool]:
        """Compile RPN expression to a matcher function."""
        def matcher(transaction: Transaction) -> bool:
            stack = []
            searchable = self._get_searchable_text(transaction).lower()

            for token in rpn:
                if token == 'AND':
                    b, a = stack.pop(), stack.pop()
                    stack.append(a and b)
                elif token == 'OR':
                    b, a = stack.pop(), stack.pop()
                    stack.append(a or b)
                elif token == 'NOT':
                    stack.append(not stack.pop())
                else:
                    stack.append(token.lower() in searchable)

            return stack[0] if stack else True

        return matcher

    def _get_searchable_text(self, t: Transaction) -> str:
        """Concatenate all searchable fields."""
        return " ".join(filter(None, [
            str(t.date),
            t.description,
            str(t.amount),
            t.type.value,
            t.category,
            t.party,
            t.status.value,
            t.notes,
            t.sheet
        ]))
```

### 6.4 Undo Service (Command Pattern)

```python
# fidra/services/undo.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, TypeVar, Optional
from collections import deque

T = TypeVar('T')

class Command(ABC):
    """Base class for undoable commands."""

    @abstractmethod
    async def execute(self) -> None:
        """Execute the command."""
        ...

    @abstractmethod
    async def undo(self) -> None:
        """Reverse the command."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""
        ...

@dataclass
class AddTransactionCommand(Command):
    """Command to add a transaction."""

    repository: TransactionRepository
    transaction: Transaction
    _saved: Optional[Transaction] = None

    async def execute(self) -> None:
        self._saved = await self.repository.save(self.transaction)

    async def undo(self) -> None:
        if self._saved:
            await self.repository.delete(self._saved.id)

    @property
    def description(self) -> str:
        return f"Add {self.transaction.description}"

@dataclass
class EditTransactionCommand(Command):
    """Command to edit a transaction."""

    repository: TransactionRepository
    old_state: Transaction
    new_state: Transaction

    async def execute(self) -> None:
        await self.repository.save(self.new_state)

    async def undo(self) -> None:
        await self.repository.save(self.old_state)

    @property
    def description(self) -> str:
        return f"Edit {self.old_state.description}"

@dataclass
class DeleteTransactionCommand(Command):
    """Command to delete a transaction."""

    repository: TransactionRepository
    transaction: Transaction

    async def execute(self) -> None:
        await self.repository.delete(self.transaction.id)

    async def undo(self) -> None:
        await self.repository.save(self.transaction)

    @property
    def description(self) -> str:
        return f"Delete {self.transaction.description}"

@dataclass
class BulkEditCommand(Command):
    """Command to edit multiple transactions."""

    repository: TransactionRepository
    old_states: list[Transaction]
    new_states: list[Transaction]

    async def execute(self) -> None:
        await self.repository.bulk_save(self.new_states)

    async def undo(self) -> None:
        await self.repository.bulk_save(self.old_states)

    @property
    def description(self) -> str:
        return f"Edit {len(self.old_states)} transactions"

class UndoStack:
    """Manages undo/redo history."""

    def __init__(self, max_size: int = 50):
        self._undo: deque[Command] = deque(maxlen=max_size)
        self._redo: deque[Command] = deque(maxlen=max_size)
        self._enabled = True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo) and self._enabled

    @property
    def can_redo(self) -> bool:
        return bool(self._redo) and self._enabled

    @property
    def undo_description(self) -> Optional[str]:
        return self._undo[-1].description if self._undo else None

    @property
    def redo_description(self) -> Optional[str]:
        return self._redo[-1].description if self._redo else None

    async def execute(self, command: Command) -> None:
        """Execute command and add to undo stack."""
        await command.execute()
        if self._enabled:
            self._undo.append(command)
            self._redo.clear()

    async def undo(self) -> Optional[str]:
        """Undo last command. Returns description or None."""
        if not self.can_undo:
            return None

        command = self._undo.pop()
        await command.undo()
        self._redo.append(command)
        return command.description

    async def redo(self) -> Optional[str]:
        """Redo last undone command. Returns description or None."""
        if not self.can_redo:
            return None

        command = self._redo.pop()
        await command.execute()
        self._undo.append(command)
        return command.description

    def disable(self) -> None:
        """Temporarily disable undo tracking."""
        self._enabled = False

    def enable(self) -> None:
        """Re-enable undo tracking."""
        self._enabled = True

    def clear(self) -> None:
        """Clear all history."""
        self._undo.clear()
        self._redo.clear()
```

### 6.5 Export Service

```python
# fidra/services/export.py

from abc import ABC, abstractmethod
from pathlib import Path
from domain.models import Transaction
from decimal import Decimal

class ExportStrategy(ABC):
    """Base class for export formats."""

    @abstractmethod
    def export(
        self,
        transactions: list[Transaction],
        balances: dict[str, Decimal],
        path: Path
    ) -> None:
        ...

class CSVExporter(ExportStrategy):
    """Export to CSV format."""

    def export(self, transactions, balances, path):
        import csv

        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Date", "Description", "Amount", "Type",
                "Category", "Party", "Status", "Balance", "Notes"
            ])

            for t in transactions:
                writer.writerow([
                    t.date.isoformat(),
                    t.description,
                    str(t.amount),
                    t.type.value,
                    t.category or "",
                    t.party or "",
                    t.status.value,
                    str(balances.get(str(t.id), "")),
                    t.notes or ""
                ])

class MarkdownExporter(ExportStrategy):
    """Export to Markdown with monthly groupings."""

    def export(self, transactions, balances, path):
        from itertools import groupby

        lines = ["# Financial Report\n"]

        # Group by month
        sorted_trans = sorted(transactions, key=lambda t: t.date)
        for month, group in groupby(sorted_trans, key=lambda t: t.date.strftime("%Y-%m")):
            lines.append(f"\n## {month}\n")
            lines.append("| Date | Description | Amount | Type | Status |")
            lines.append("|------|-------------|--------|------|--------|")

            for t in group:
                lines.append(
                    f"| {t.date} | {t.description} | £{t.amount:.2f} | "
                    f"{t.type.value} | {t.status.value} |"
                )

        path.write_text("\n".join(lines))

class PDFExporter(ExportStrategy):
    """Export to PDF format."""

    def export(self, transactions, balances, path):
        # Use weasyprint or reportlab
        ...

class ExportService:
    """Facade for export operations."""

    FORMATS = {
        'csv': CSVExporter,
        'markdown': MarkdownExporter,
        'pdf': PDFExporter,
    }

    def export(
        self,
        format: str,
        transactions: list[Transaction],
        balances: dict[str, Decimal],
        path: Path
    ) -> None:
        exporter_class = self.FORMATS.get(format)
        if not exporter_class:
            raise ValueError(f"Unknown format: {format}")

        exporter = exporter_class()
        exporter.export(transactions, balances, path)
```

### 6.6 File Watch Service

```python
# fidra/services/file_watch.py

from pathlib import Path
from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal, QFileSystemWatcher

class FileWatchService(QObject):
    """Monitors file for external changes."""

    file_changed = Signal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._watched_path: Optional[Path] = None
        self._last_mtime: float = 0

    def watch(self, path: Path) -> None:
        """Start watching a file."""
        if self._watched_path:
            self._watcher.removePath(str(self._watched_path))

        self._watched_path = path
        self._watcher.addPath(str(path))
        self._last_mtime = path.stat().st_mtime if path.exists() else 0

    def stop(self) -> None:
        """Stop watching."""
        if self._watched_path:
            self._watcher.removePath(str(self._watched_path))
            self._watched_path = None

    def _on_file_changed(self, path: str) -> None:
        """Handle file change notification."""
        p = Path(path)

        # Debounce by checking mtime
        if p.exists():
            mtime = p.stat().st_mtime
            if mtime > self._last_mtime:
                self._last_mtime = mtime
                self.file_changed.emit(p)

        # Re-add path (Qt removes it after change)
        if p.exists() and str(p) not in self._watcher.files():
            self._watcher.addPath(str(p))
```

---

## 7. State Management

### 7.1 Observable State

```python
# fidra/state/observable.py

from typing import TypeVar, Generic, Callable, Optional
from PySide6.QtCore import QObject, Signal

T = TypeVar('T')

class Observable(QObject, Generic[T]):
    """Reactive state container with Qt signal integration."""

    changed = Signal(object)

    def __init__(self, initial: T, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._value = initial

    @property
    def value(self) -> T:
        return self._value

    def set(self, new_value: T) -> None:
        if new_value != self._value:
            self._value = new_value
            self.changed.emit(new_value)

    def update(self, fn: Callable[[T], T]) -> None:
        self.set(fn(self._value))

    def subscribe(self, callback: Callable[[T], None]) -> None:
        self.changed.connect(callback)
```

### 7.2 Application State

```python
# fidra/state/app_state.py

from dataclasses import dataclass, field
from uuid import UUID
from domain.models import Transaction, PlannedTemplate, Sheet
from state.observable import Observable

@dataclass
class AppState:
    """Central application state."""

    # Data
    transactions: Observable[list[Transaction]] = field(
        default_factory=lambda: Observable([])
    )
    planned_templates: Observable[list[PlannedTemplate]] = field(
        default_factory=lambda: Observable([])
    )
    sheets: Observable[list[Sheet]] = field(
        default_factory=lambda: Observable([])
    )

    # UI State
    current_sheet: Observable[str] = field(
        default_factory=lambda: Observable("All Transactions")
    )
    selected_ids: Observable[set[UUID]] = field(
        default_factory=lambda: Observable(set())
    )
    search_query: Observable[str] = field(
        default_factory=lambda: Observable("")
    )
    include_planned: Observable[bool] = field(
        default_factory=lambda: Observable(True)
    )
    filtered_balance_mode: Observable[bool] = field(
        default_factory=lambda: Observable(True)
    )

    # Loading/Error state
    is_loading: Observable[bool] = field(
        default_factory=lambda: Observable(False)
    )
    error_message: Observable[Optional[str]] = field(
        default_factory=lambda: Observable(None)
    )

    # Derived state (computed from above)
    @property
    def filtered_transactions(self) -> list[Transaction]:
        """Transactions filtered by current sheet and search."""
        # Computed by UI layer
        ...

    @property
    def display_transactions(self) -> list[Transaction]:
        """Transactions to display (includes planned if enabled)."""
        # Computed by UI layer
        ...
```

### 7.3 State Persistence

```python
# fidra/state/persistence.py

from pathlib import Path
import json
from domain.settings import AppSettings

class SettingsStore:
    """Persists settings to JSON file."""

    DEFAULT_PATH = Path.home() / ".fidra_settings.json"

    def __init__(self, path: Optional[Path] = None):
        self._path = path or self.DEFAULT_PATH

    def load(self) -> AppSettings:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                return AppSettings.model_validate(data)
            except Exception:
                pass
        return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self._path.write_text(
            settings.model_dump_json(indent=2)
        )
```

---

## 8. User Interface

### 8.1 Navigation Model

The application uses a **tab-based navigation** with four primary views:

| View | Purpose | Icon |
|------|---------|------|
| **Dashboard** | Overview with balance, charts, upcoming transactions | 📊 |
| **Transactions** | Transaction list with add/edit/search | 📋 |
| **Planned** | Future expected transactions (one-time & recurring) | 📅 |
| **Reports** | Detailed breakdowns and exports | 📈 |

```
┌────────────────────────────────────────────────────────────────────┐
│ TOP BAR                                                            │
│ ┌────────┐  ┌───────────────────────────────────────┐  ┌────────┐ │
│ │ Logo   │  │ [Dashboard] [Trans] [Planned] [Reports]│  │Settings│ │
│ └────────┘  └───────────────────────────────────────┘  └────────┘ │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│                     CONTENT AREA (Stacked Widget)                  │
│                                                                    │
│   ┌────────────────────────────────────────────────────────────┐  │
│   │                                                            │  │
│   │                    [Active View Content]                   │  │
│   │                                                            │  │
│   │           Dashboard / Transactions / Planned / Reports     │  │
│   │                                                            │  │
│   └────────────────────────────────────────────────────────────┘  │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│ STATUS BAR                                                         │
│ Ready | 150 transactions | Last saved: 12:34:56                   │
└────────────────────────────────────────────────────────────────────┘
```

### 8.2 Dashboard View

The dashboard provides an at-a-glance overview of financial status with theme-aware charts.

```
┌─────────────────────────────────────────────────────────────────────┐
│  DASHBOARD                                          [Sheet ▼] [⚙]  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │    BALANCE      │  │   THIS MONTH    │  │    PENDING      │     │
│  │   £4,521.30     │  │ Income: +£1,200 │  │    3 items      │     │
│  │   ▲ +£230       │  │ Expense: -£380  │  │   £450 total    │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
│                                                                     │
│  ┌────────────────────────────────────┐  ┌────────────────────┐    │
│  │      Balance Trend (90 days)       │  │    Expenses by     │    │
│  │                                    │  │     Category       │    │
│  │     ╭─────╮                        │  │                    │    │
│  │    ╱      ╲      ╭────             │  │    ┌───┐           │    │
│  │   ╱        ╲    ╱                  │  │   ╱     ╲  Rent    │    │
│  │  ╱          ╲──╱                   │  │  │  42%  │  Food   │    │
│  │ ╱                                  │  │   ╲     ╱  Utils   │    │
│  │╱                                   │  │    └───┘           │    │
│  │ Oct    Nov    Dec    Jan           │  │                    │    │
│  └────────────────────────────────────┘  └────────────────────┘    │
│                                                                     │
│  ┌────────────────────────────────────┐  ┌────────────────────┐    │
│  │   Income vs Expenses (6 months)    │  │      UPCOMING      │    │
│  │                                    │  │                    │    │
│  │   ▓▓░░  ▓▓░░  ▓▓░░  ▓▓░░  ▓▓░░   │  │  ● Rent      (3d)  │    │
│  │   Aug   Sep   Oct   Nov   Dec     │  │  ● Insurance (7d)  │    │
│  │                                    │  │  ● Salary   (12d)  │    │
│  │   ▓ Income   ░ Expenses            │  │  ● Subs     (15d)  │    │
│  └────────────────────────────────────┘  └────────────────────┘    │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  RECENT TRANSACTIONS                              [View All →]│  │
│  │  ─────────────────────────────────────────────────────────── │  │
│  │  Today      │ Coffee Shop        │ -£4.50   │ Food          │  │
│  │  Yesterday  │ Monthly Salary     │ +£2,500  │ Income        │  │
│  │  Jan 12     │ Electric Bill      │ -£85.00  │ Utilities     │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Dashboard View Implementation:**

```python
# fidra/ui/views/dashboard_view.py

from decimal import Decimal
from datetime import date, timedelta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QScrollArea, QPushButton
)
from PySide6.QtCore import Qt, Signal
import pyqtgraph as pg


class StatCard(QFrame):
    """Reusable card widget for displaying a statistic."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("statTitle")
        layout.addWidget(self.title_label)

        self.value_label = QLabel("—")
        self.value_label.setObjectName("statValue")
        layout.addWidget(self.value_label)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("statDetail")
        layout.addWidget(self.detail_label)

    def set_value(self, value: str, detail: str = ""):
        self.value_label.setText(value)
        self.detail_label.setText(detail)


class DashboardView(QWidget):
    """Dashboard view with overview charts and statistics."""

    view_all_clicked = Signal()  # Navigate to Transactions view

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self._ctx = ctx
        self._state = ctx.state
        self.setObjectName("dashboardView")

        self._setup_ui()
        self._connect_signals()
        self._apply_theme_to_charts()

    def _setup_ui(self):
        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # === Stat Cards Row ===
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)

        self.balance_card = StatCard("Current Balance")
        self.month_card = StatCard("This Month")
        self.pending_card = StatCard("Pending")

        cards_layout.addWidget(self.balance_card)
        cards_layout.addWidget(self.month_card)
        cards_layout.addWidget(self.pending_card)
        layout.addLayout(cards_layout)

        # === Charts Row ===
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(16)

        # Balance trend chart
        self.balance_chart = pg.PlotWidget()
        self.balance_chart.setObjectName("balanceChart")
        self.balance_chart.setTitle("Balance Trend (90 days)")
        self.balance_chart.setLabel('left', 'Balance (£)')
        self.balance_chart.setLabel('bottom', 'Date')
        self.balance_chart.showGrid(x=True, y=True, alpha=0.3)
        charts_layout.addWidget(self.balance_chart, stretch=2)

        # Category pie chart (using bar chart as alternative)
        self.category_chart = pg.PlotWidget()
        self.category_chart.setObjectName("categoryChart")
        self.category_chart.setTitle("Expenses by Category")
        charts_layout.addWidget(self.category_chart, stretch=1)

        layout.addLayout(charts_layout)

        # === Income vs Expenses + Upcoming Row ===
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(16)

        # Income vs Expenses bar chart
        self.income_expense_chart = pg.PlotWidget()
        self.income_expense_chart.setObjectName("incomeExpenseChart")
        self.income_expense_chart.setTitle("Income vs Expenses (6 months)")
        bottom_layout.addWidget(self.income_expense_chart, stretch=2)

        # Upcoming transactions list
        upcoming_frame = QFrame()
        upcoming_frame.setObjectName("upcomingFrame")
        upcoming_layout = QVBoxLayout(upcoming_frame)

        upcoming_header = QLabel("Upcoming")
        upcoming_header.setObjectName("sectionHeader")
        upcoming_layout.addWidget(upcoming_header)

        self.upcoming_list = QVBoxLayout()
        upcoming_layout.addLayout(self.upcoming_list)
        upcoming_layout.addStretch()

        bottom_layout.addWidget(upcoming_frame, stretch=1)
        layout.addLayout(bottom_layout)

        # === Recent Transactions ===
        recent_frame = QFrame()
        recent_frame.setObjectName("recentFrame")
        recent_layout = QVBoxLayout(recent_frame)

        recent_header_layout = QHBoxLayout()
        recent_title = QLabel("Recent Transactions")
        recent_title.setObjectName("sectionHeader")
        recent_header_layout.addWidget(recent_title)

        view_all_btn = QPushButton("View All →")
        view_all_btn.setObjectName("linkButton")
        view_all_btn.clicked.connect(self.view_all_clicked.emit)
        recent_header_layout.addWidget(view_all_btn)
        recent_header_layout.addStretch()

        recent_layout.addLayout(recent_header_layout)

        self.recent_list = QVBoxLayout()
        recent_layout.addLayout(self.recent_list)

        layout.addWidget(recent_frame)
        layout.addStretch()

        scroll.setWidget(content)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _connect_signals(self):
        self._state.transactions.changed.connect(self._refresh_data)
        self._state.planned_templates.changed.connect(self._refresh_upcoming)

    def _apply_theme_to_charts(self):
        """Apply theme colors to pyqtgraph charts."""
        from ui.theme import ThemeEngine
        theme = ThemeEngine.instance()
        colors = theme.current_colors()

        bg_color = colors.bg_main
        text_color = colors.text_primary
        grid_color = colors.border_subtle
        accent = colors.accent_primary

        for chart in [self.balance_chart, self.category_chart, self.income_expense_chart]:
            chart.setBackground(bg_color)
            chart.getAxis('left').setTextPen(text_color)
            chart.getAxis('bottom').setTextPen(text_color)

        # Balance trend line color
        self._balance_pen = pg.mkPen(accent, width=2)
        self._income_brush = pg.mkBrush(colors.income)
        self._expense_brush = pg.mkBrush(colors.expense)

    def _refresh_data(self, transactions):
        """Refresh all dashboard data."""
        self._update_stat_cards(transactions)
        self._update_balance_chart(transactions)
        self._update_category_chart(transactions)
        self._update_income_expense_chart(transactions)
        self._update_recent_list(transactions)

    def _update_stat_cards(self, transactions):
        # Calculate current balance
        balance = sum(
            t.amount if t.type.value == 'income' else -t.amount
            for t in transactions
            if t.status.value == 'approved'
        )
        self.balance_card.set_value(f"£{balance:,.2f}")

        # This month stats
        today = date.today()
        month_start = today.replace(day=1)
        month_txns = [t for t in transactions if t.date >= month_start]
        month_income = sum(t.amount for t in month_txns if t.type.value == 'income')
        month_expense = sum(t.amount for t in month_txns if t.type.value == 'expense')
        self.month_card.set_value(
            f"+£{month_income:,.0f} / -£{month_expense:,.0f}",
            f"Net: £{month_income - month_expense:,.0f}"
        )

        # Pending count
        pending = [t for t in transactions if t.status.value == 'pending']
        pending_total = sum(t.amount for t in pending)
        self.pending_card.set_value(
            f"{len(pending)} items",
            f"£{pending_total:,.2f} total"
        )

    def _update_balance_chart(self, transactions):
        """Update the balance trend line chart."""
        # Calculate running balance over last 90 days
        end_date = date.today()
        start_date = end_date - timedelta(days=90)

        # Sort transactions by date
        sorted_txns = sorted(
            [t for t in transactions if t.status.value == 'approved'],
            key=lambda t: t.date
        )

        # Build daily balance series
        dates = []
        balances = []
        running = Decimal(0)

        for t in sorted_txns:
            if t.date >= start_date:
                running += t.amount if t.type.value == 'income' else -t.amount
                dates.append((t.date - start_date).days)
                balances.append(float(running))

        self.balance_chart.clear()
        if dates:
            self.balance_chart.plot(dates, balances, pen=self._balance_pen)

    def _refresh_upcoming(self, templates):
        """Refresh the upcoming transactions list."""
        # Clear existing items
        while self.upcoming_list.count():
            item = self.upcoming_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get next 5 upcoming planned transactions
        today = date.today()
        upcoming = sorted(
            [t for t in templates if t.start_date >= today],
            key=lambda t: t.start_date
        )[:5]

        for template in upcoming:
            days = (template.start_date - today).days
            label = QLabel(f"● {template.description} ({days}d)")
            label.setObjectName("upcomingItem")
            self.upcoming_list.addWidget(label)
```

### 8.3 Transactions View

The transactions view shows the full transaction list with add/edit capabilities. It supports an integrated view of planned transactions for holistic financial visibility.

```
┌────────────────────────────────────────────────────────────────────┐
│ TRANSACTIONS                        [Sheet ▼] [✓ Show Planned] [⚙]│
├──────────────┬─────────────────────────────────────┬───────────────┤
│ LEFT SIDEBAR │         MAIN CONTENT                │ RIGHT PANEL   │
│              │                                     │               │
│ ┌──────────┐ │ ┌─────────────────────────────────┐ │ ┌───────────┐ │
│ │ Add Form │ │ │ SEARCH BAR                      │ │ │  Balance  │ │
│ │          │ │ │ [Search...        ] [X] [Toggle]│ │ │  £4,521   │ │
│ │ Type:    │ │ └─────────────────────────────────┘ │ │ Projected │ │
│ │ [EXP|INC]│ │                                     │ │  £6,136   │ │
│ │          │ │ ┌─────────────────────────────────┐ │ └───────────┘ │
│ │ Date:    │ │ │ TRANSACTION TABLE               │ │               │
│ │ [____][📅]│ │ │                                 │ │ ┌───────────┐ │
│ │          │ │ │ Date | Desc | Amt | Stat | Bal │ │ │  Horizon  │ │
│ │ Desc:    │ │ │ ─────────────────────────────── │ │ │ [90 days] │ │
│ │ [______] │ │ │ Jan 10 | Coffee  | -£5  |  ✓   │ │ └───────────┘ │
│ │          │ │ │ Jan 14 | Salary  |+£2500|  --  │ │               │
│ │ Amount:  │ │ │┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈│ │ ┌───────────┐ │
│ │ [______] │ │ │ Jan 15 | Rent    | -£800| PLAN │ │ │  Actions  │ │
│ │          │ │ │ Feb 14 | Salary  |+£2500| PLAN │ │ │ [Undo]    │ │
│ │ Category:│ │ │                                 │ │ │ [Redo]    │ │
│ │ [_____▼] │ │ │                                 │ │ │ [Export]  │ │
│ │          │ │ └─────────────────────────────────┘ │ └───────────┘ │
│ │ Party:   │ │                                     │               │
│ │ [______] │ │ ┌─────────────────────────────────┐ │               │
│ │          │ │ │ ACTION BAR (actual selected)    │ │               │
│ │ [Submit] │ │ │ [Edit] [Approve] [Reject] [Del] │ │               │
│ └──────────┘ │ └─────────────────────────────────┘ │               │
│              │ ┌─────────────────────────────────┐ │               │
│              │ │ ACTION BAR (planned selected)   │ │               │
│              │ │ [Convert to Actual] [Skip] [Edit│ │               │
│              │ │         Template]               │ │               │
│              │ └─────────────────────────────────┘ │               │
└──────────────┴─────────────────────────────────────┴───────────────┘
```

**Show Planned Toggle Behavior:**

| State | Table Contents | Balance Display |
|-------|----------------|-----------------|
| OFF | Actual transactions only | Current balance (actuals) |
| ON | Actuals + planned instances (mixed chronologically) | Current + projected balance |

**Planned Row Visual Distinction:**
- Subtle background tint (slightly different from alternating row colors)
- "PLANNED" badge in status column instead of Approved/Pending
- Dashed left border accent
- Slightly muted text color

**Planned Row Interactions:**

| Action | Description |
|--------|-------------|
| **Convert to Actual** | Creates a real transaction pre-filled from the planned instance. Optionally marks the planned instance as "fulfilled". |
| **Skip Instance** | Marks this specific occurrence as skipped (won't appear in balance projection). Template continues normally. |
| **Edit Template** | Opens the source template in the Planned view for modification. |

**Important:** Planned rows cannot be approved, rejected, or deleted directly—they're read-only projections from templates.

### 8.4 Main Window Implementation

```python
# fidra/ui/main_window.py

from enum import IntEnum
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QStatusBar, QPushButton, QButtonGroup
)
from PySide6.QtCore import Qt, Signal
from ui.views import DashboardView, TransactionsView, PlannedView, ReportsView
from state.app_state import AppState


class ViewIndex(IntEnum):
    """Indices for the stacked widget views."""
    DASHBOARD = 0
    TRANSACTIONS = 1
    PLANNED = 2
    REPORTS = 3


class MainWindow(QMainWindow):
    """Main application window with tab-based navigation."""

    view_changed = Signal(int)  # Emitted when navigation changes

    def __init__(self, app_context):
        super().__init__()
        self._ctx = app_context
        self._state = app_context.state

        self.setWindowTitle("Fidra")
        self.setMinimumSize(1000, 700)
        self.resize(1280, 800)

        self._setup_ui()
        self._connect_signals()
        self._apply_theme()

        # Start on Dashboard
        self.navigate_to(ViewIndex.DASHBOARD)

    def _setup_ui(self):
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar with navigation
        self.top_bar = self._create_top_bar()
        layout.addWidget(self.top_bar)

        # Stacked widget for views
        self.stack = QStackedWidget()
        self.stack.setObjectName("mainStack")

        # Create views
        self.dashboard_view = DashboardView(self._ctx)
        self.transactions_view = TransactionsView(self._ctx)
        self.planned_view = PlannedView(self._ctx)
        self.reports_view = ReportsView(self._ctx)

        # Add views to stack
        self.stack.addWidget(self.dashboard_view)    # Index 0
        self.stack.addWidget(self.transactions_view) # Index 1
        self.stack.addWidget(self.planned_view)      # Index 2
        self.stack.addWidget(self.reports_view)      # Index 3

        layout.addWidget(self.stack, 1)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _create_top_bar(self) -> QWidget:
        """Create top bar with logo and navigation tabs."""
        bar = QWidget()
        bar.setObjectName("topBar")
        bar.setFixedHeight(56)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # Logo/Title
        from PySide6.QtWidgets import QLabel
        logo = QLabel("Fidra")
        logo.setObjectName("appLogo")
        layout.addWidget(logo)

        layout.addSpacing(24)

        # Navigation buttons
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        nav_items = [
            ("📊 Dashboard", ViewIndex.DASHBOARD),
            ("📋 Transactions", ViewIndex.TRANSACTIONS),
            ("📅 Planned", ViewIndex.PLANNED),
            ("📈 Reports", ViewIndex.REPORTS),
        ]

        for label, index in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setProperty("viewIndex", index)
            self.nav_group.addButton(btn, index)
            layout.addWidget(btn)

        layout.addStretch()

        # Settings button
        settings_btn = QPushButton("⚙")
        settings_btn.setObjectName("settingsButton")
        settings_btn.clicked.connect(self._show_settings)
        layout.addWidget(settings_btn)

        return bar

    def _connect_signals(self):
        # Navigation
        self.nav_group.idClicked.connect(self.navigate_to)

        # State changes
        self._state.transactions.changed.connect(self._on_transactions_changed)
        self._state.current_sheet.changed.connect(self._on_sheet_changed)
        self._state.error_message.changed.connect(self._show_error)

        # Dashboard quick actions
        self.dashboard_view.view_all_clicked.connect(
            lambda: self.navigate_to(ViewIndex.TRANSACTIONS)
        )

    def navigate_to(self, view_index: int):
        """Switch to a specific view."""
        self.stack.setCurrentIndex(view_index)

        # Update nav button state
        btn = self.nav_group.button(view_index)
        if btn:
            btn.setChecked(True)

        self.view_changed.emit(view_index)

    def _on_transactions_changed(self, transactions):
        count = len(transactions)
        self.status_bar.showMessage(f"{count} transaction{'s' if count != 1 else ''}")

    def _on_sheet_changed(self, sheet):
        self.setWindowTitle(f"Fidra - {sheet}")

    def _show_error(self, message):
        if message:
            self.status_bar.showMessage(f"Error: {message}", 5000)

    def _show_settings(self):
        from ui.dialogs import SettingsDialog
        dialog = SettingsDialog(self._ctx, self)
        dialog.exec()

    def _apply_theme(self):
        from ui.theme import ThemeEngine
        ThemeEngine.instance().apply_to(self)
```

### 8.5 Transaction Table

```python
# fidra/ui/components/transaction_table.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableView, QHeaderView,
    QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal
from PySide6.QtGui import QAction
from ui.models import TransactionTableModel

class TransactionTable(QWidget):
    """Transaction list with search and actions."""

    row_selected = Signal(list)  # List of selected transaction IDs
    edit_requested = Signal(object)  # Transaction to edit
    context_menu_requested = Signal(object, object)  # Transaction, QPoint

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self._ctx = ctx
        self._state = ctx.state
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search bar
        from ui.components import SearchBar
        self.search_bar = SearchBar()
        layout.addWidget(self.search_bar)

        # Table view
        self.table = QTableView()
        self.table.setObjectName("transactionTable")
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.setSortingEnabled(True)

        # Header configuration
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.table.verticalHeader().hide()

        # Model with filtering
        self.model = TransactionTableModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)  # Search all columns
        self.table.setModel(self.proxy)

        layout.addWidget(self.table, 1)

        # Action bar (shown when selection exists)
        from ui.components import ActionBar
        self.action_bar = ActionBar(self._ctx)
        self.action_bar.hide()
        layout.addWidget(self.action_bar)

    def _connect_signals(self):
        # Search
        self.search_bar.search_changed.connect(
            lambda q: self.proxy.setFilterFixedString(q)
        )

        # Selection
        self.table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        # Double-click to edit
        self.table.doubleClicked.connect(self._on_double_click)

        # Context menu
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        # State changes
        self._state.transactions.changed.connect(self._update_data)

    def _update_data(self, transactions):
        self.model.set_transactions(transactions)
        self.search_bar.set_result_count(len(transactions))

    def _on_selection_changed(self, selected, deselected):
        indexes = self.table.selectionModel().selectedRows()
        ids = [self.model.get_transaction_id(i.row()) for i in indexes]
        self._state.selected_ids.set(set(ids))

        # Show/hide action bar
        if ids:
            self.action_bar.show()
        else:
            self.action_bar.hide()

    def _on_double_click(self, index):
        trans = self.model.get_transaction(index.row())
        if trans:
            self.edit_requested.emit(trans)

    def _show_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if index.isValid():
            trans = self.model.get_transaction(index.row())
            if trans:
                menu = self._create_context_menu(trans)
                menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _create_context_menu(self, transaction):
        menu = QMenu(self)

        edit_action = QAction("Edit", self)
        edit_action.triggered.connect(lambda: self.edit_requested.emit(transaction))
        menu.addAction(edit_action)

        menu.addSeparator()

        if transaction.status.value == "pending":
            approve = QAction("Approve", self)
            approve.triggered.connect(
                lambda: self._ctx.commands.approve(transaction.id)
            )
            menu.addAction(approve)

            reject = QAction("Reject", self)
            reject.triggered.connect(
                lambda: self._ctx.commands.reject(transaction.id)
            )
            menu.addAction(reject)

        menu.addSeparator()

        delete = QAction("Delete", self)
        delete.triggered.connect(
            lambda: self._ctx.commands.delete(transaction.id)
        )
        menu.addAction(delete)

        return menu
```

### 8.6 Add Transaction Form

```python
# fidra/ui/components/add_form.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QTextEdit,
    QPushButton, QDateEdit, QDoubleSpinBox,
    QButtonGroup
)
from PySide6.QtCore import Qt, QDate, Signal
from decimal import Decimal

class AddTransactionForm(QWidget):
    """Form for adding new transactions."""

    submitted = Signal(dict)  # Emits form data

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self._ctx = ctx
        self._transaction_type = "expense"
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # Header
        header = QLabel("Add Transaction")
        header.setObjectName("formHeader")
        layout.addWidget(header)

        # Type selector
        type_layout = QHBoxLayout()

        self.expense_btn = QPushButton("EXPENSE")
        self.expense_btn.setObjectName("expenseButton")
        self.expense_btn.setCheckable(True)
        self.expense_btn.setChecked(True)

        self.income_btn = QPushButton("INCOME")
        self.income_btn.setObjectName("incomeButton")
        self.income_btn.setCheckable(True)

        self.type_group = QButtonGroup(self)
        self.type_group.addButton(self.expense_btn, 0)
        self.type_group.addButton(self.income_btn, 1)
        self.type_group.setExclusive(True)

        type_layout.addWidget(self.expense_btn)
        type_layout.addWidget(self.income_btn)
        layout.addLayout(type_layout)

        # Form fields
        form = QFormLayout()
        form.setSpacing(8)

        # Date
        date_layout = QHBoxLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(self.date_edit)
        form.addRow("Date:", date_layout)

        # Description
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("e.g., Fuel for trip")
        form.addRow("Description:", self.desc_edit)

        # Amount
        self.amount_edit = QDoubleSpinBox()
        self.amount_edit.setPrefix("£ ")
        self.amount_edit.setDecimals(2)
        self.amount_edit.setMaximum(999999.99)
        self.amount_edit.setMinimum(0.01)
        form.addRow("Amount:", self.amount_edit)

        # Category
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self._update_categories()
        form.addRow("Category:", self.category_combo)

        # Party
        self.party_edit = QLineEdit()
        self.party_edit.setPlaceholderText("e.g., Fuel Station")
        form.addRow("Party:", self.party_edit)

        # Notes
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(60)
        self.notes_edit.setPlaceholderText("Optional notes...")
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        # Submit button
        self.submit_btn = QPushButton("Add Transaction")
        self.submit_btn.setObjectName("submitButton")
        layout.addWidget(self.submit_btn)

        layout.addStretch()

    def _connect_signals(self):
        self.type_group.buttonClicked.connect(self._on_type_changed)
        self.submit_btn.clicked.connect(self._on_submit)

    def _on_type_changed(self, button):
        self._transaction_type = "expense" if button == self.expense_btn else "income"
        self._update_categories()

    def _update_categories(self):
        settings = self._ctx.settings
        if self._transaction_type == "expense":
            categories = settings.expense_categories
        else:
            categories = settings.income_categories

        self.category_combo.clear()
        self.category_combo.addItems(categories)

    def _on_submit(self):
        data = {
            'date': self.date_edit.date().toPython(),
            'description': self.desc_edit.text().strip(),
            'amount': Decimal(str(self.amount_edit.value())),
            'type': self._transaction_type,
            'category': self.category_combo.currentText(),
            'party': self.party_edit.text().strip(),
            'notes': self.notes_edit.toPlainText().strip() or None,
        }

        if self._validate(data):
            self.submitted.emit(data)
            self._clear_form()

    def _validate(self, data) -> bool:
        if not data['description']:
            self._show_error("Description is required")
            return False
        if data['amount'] <= 0:
            self._show_error("Amount must be positive")
            return False
        return True

    def _clear_form(self):
        self.date_edit.setDate(QDate.currentDate())
        self.desc_edit.clear()
        self.amount_edit.setValue(0)
        self.party_edit.clear()
        self.notes_edit.clear()

    def _show_error(self, message):
        from ui.dialogs import MessageDialog
        MessageDialog.error(self, "Validation Error", message)
```

### 8.7 Edit Dialog

```python
# fidra/ui/dialogs/edit_dialog.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QTextEdit,
    QPushButton, QDateEdit, QDoubleSpinBox,
    QDialogButtonBox
)
from PySide6.QtCore import Qt, QDate
from domain.models import Transaction, ApprovalStatus

class EditTransactionDialog(QDialog):
    """Dialog for editing a transaction."""

    def __init__(self, transaction: Transaction, ctx, parent=None):
        super().__init__(parent)
        self._transaction = transaction
        self._ctx = ctx
        self._result = None

        self.setWindowTitle("Edit Transaction")
        self.setMinimumWidth(400)
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Form
        form = QFormLayout()

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        form.addRow("Date:", self.date_edit)

        self.desc_edit = QLineEdit()
        form.addRow("Description:", self.desc_edit)

        self.amount_edit = QDoubleSpinBox()
        self.amount_edit.setPrefix("£ ")
        self.amount_edit.setMaximum(999999.99)
        form.addRow("Amount:", self.amount_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["expense", "income"])
        form.addRow("Type:", self.type_combo)

        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        form.addRow("Category:", self.category_combo)

        self.party_edit = QLineEdit()
        form.addRow("Party:", self.party_edit)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["pending", "approved", "rejected"])
        form.addRow("Status:", self.status_combo)

        self.sheet_combo = QComboBox()
        form.addRow("Sheet:", self.sheet_combo)

        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(80)
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate(self):
        t = self._transaction

        self.date_edit.setDate(QDate(t.date.year, t.date.month, t.date.day))
        self.desc_edit.setText(t.description)
        self.amount_edit.setValue(float(t.amount))
        self.type_combo.setCurrentText(t.type.value)
        self.category_combo.setCurrentText(t.category or "")
        self.party_edit.setText(t.party or "")
        self.notes_edit.setText(t.notes or "")

        # Status (disable for income)
        if t.type.value == "income":
            self.status_combo.setEnabled(False)
            self.status_combo.setCurrentText("--")
        else:
            self.status_combo.setCurrentText(t.status.value)

        # Populate sheets
        sheets = [s.name for s in self._ctx.state.sheets.value
                  if not s.is_virtual and not s.is_planned]
        self.sheet_combo.addItems(sheets)
        self.sheet_combo.setCurrentText(t.sheet)

    def _on_save(self):
        from decimal import Decimal

        self._result = self._transaction.with_updates(
            date=self.date_edit.date().toPython(),
            description=self.desc_edit.text().strip(),
            amount=Decimal(str(self.amount_edit.value())),
            type=self.type_combo.currentText(),
            category=self.category_combo.currentText() or None,
            party=self.party_edit.text().strip() or None,
            status=ApprovalStatus(self.status_combo.currentText()),
            sheet=self.sheet_combo.currentText(),
            notes=self.notes_edit.toPlainText().strip() or None,
        )
        self.accept()

    def get_result(self) -> Transaction:
        return self._result
```

### 8.8 Planned View

The Planned view provides dedicated management of planned transaction templates with inline instance expansion.

```
┌─────────────────────────────────────────────────────────────────────┐
│ PLANNED                                              [+ Add]  [⚙]  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  TEMPLATES                                                          │
│  ──────────────────────────────────────────────────────────────────│
│    │ Description      │ Amount  │ Type    │ Freq    │ Next Due    │
│  ──┼──────────────────┼─────────┼─────────┼─────────┼─────────────│
│  ▸ │ Monthly Rent     │ £800    │ Expense │ Monthly │ Jan 15      │
│  ▾ │ Salary           │ £2,500  │ Income  │ Monthly │ Jan 15      │
│    │  ├─ Jan 15, 2025 │ £2,500  │         │         │ ✓ fulfilled │
│    │  ├─ Feb 15, 2025 │ £2,500  │         │         │             │
│    │  ├─ Mar 15, 2025 │ £2,500  │         │         │             │
│    │  └─ Apr 15, 2025 │ £2,500  │         │         │             │
│  ▸ │ Insurance        │ £150    │ Expense │ Yearly  │ Mar 1       │
│  ▸ │ New Equipment    │ £500    │ Expense │ Once    │ Feb 1       │
│                                                                     │
│  ──────────────────────────────────────────────────────────────────│
│  ACTIONS (when template selected)                                   │
│  [Edit] [Delete] [Duplicate]                                        │
│                                                                     │
│  ACTIONS (when instance selected within expansion)                  │
│  [Convert to Actual] [Skip] [Un-skip]                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**View Features:**

| Feature | Description |
|---------|-------------|
| **Collapsible rows** | Click ▸/▾ to expand template and see upcoming instances |
| **Instance horizon** | Shows instances up to configured forecast horizon (default 90 days) |
| **Frequency badge** | Visual indicator: `Once`, `Monthly`, `Yearly`, etc. |
| **Next Due column** | Shows next upcoming instance date |
| **Fulfilled marking** | Instances that have been converted to actuals shown as fulfilled |
| **Skipped marking** | Skipped instances shown with strikethrough |

**Template Actions:**

| Action | Behavior |
|--------|----------|
| **Add** | Opens form to create new planned template |
| **Edit** | Opens edit dialog for selected template |
| **Delete** | Removes template (confirmation required, shows affected instances) |
| **Duplicate** | Creates copy of template for quick variations |

**Instance Actions (within expanded template):**

| Action | Behavior |
|--------|----------|
| **Convert to Actual** | Creates transaction, marks instance as fulfilled |
| **Skip** | Excludes instance from balance projection |
| **Un-skip** | Restores previously skipped instance |

**Planned View Implementation:**

```python
# fidra/ui/views/planned_view.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeView,
    QPushButton, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from ui.models import PlannedTreeModel


class PlannedView(QWidget):
    """View for managing planned transaction templates."""

    template_selected = Signal(object)  # PlannedTemplate
    instance_selected = Signal(object, object)  # PlannedTemplate, date

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self._ctx = ctx
        self._state = ctx.state
        self.setObjectName("plannedView")

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header with Add button
        header = QHBoxLayout()
        from PySide6.QtWidgets import QLabel
        title = QLabel("Planned Transactions")
        title.setObjectName("viewTitle")
        header.addWidget(title)
        header.addStretch()

        self.add_btn = QPushButton("+ Add")
        self.add_btn.setObjectName("primaryButton")
        self.add_btn.clicked.connect(self._on_add_clicked)
        header.addWidget(self.add_btn)

        layout.addLayout(header)

        # Tree view for templates with expandable instances
        self.tree = QTreeView()
        self.tree.setObjectName("plannedTree")
        self.tree.setAlternatingRowColors(True)
        self.tree.setAnimated(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setRootIsDecorated(True)

        # Configure header
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(QHeaderView.Interactive)

        # Model
        self.model = PlannedTreeModel(self._ctx)
        self.tree.setModel(self.model)

        layout.addWidget(self.tree, 1)

        # Action bar
        self.action_bar = QHBoxLayout()
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.duplicate_btn = QPushButton("Duplicate")
        self.convert_btn = QPushButton("Convert to Actual")
        self.skip_btn = QPushButton("Skip")

        for btn in [self.edit_btn, self.delete_btn, self.duplicate_btn]:
            btn.setObjectName("secondaryButton")
            self.action_bar.addWidget(btn)

        self.action_bar.addSpacing(20)

        for btn in [self.convert_btn, self.skip_btn]:
            btn.setObjectName("secondaryButton")
            self.action_bar.addWidget(btn)

        self.action_bar.addStretch()
        layout.addLayout(self.action_bar)

        # Initially disable instance actions
        self.convert_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)

    def _connect_signals(self):
        self._state.planned_templates.changed.connect(self.model.refresh)
        self.tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.tree.clicked.connect(self._on_item_clicked)

        self.edit_btn.clicked.connect(self._on_edit_clicked)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.duplicate_btn.clicked.connect(self._on_duplicate_clicked)
        self.convert_btn.clicked.connect(self._on_convert_clicked)
        self.skip_btn.clicked.connect(self._on_skip_clicked)

    def _on_selection_changed(self, selected, deselected):
        """Update action button states based on selection."""
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes:
            return

        item = self.model.item_at(indexes[0])
        is_template = item.get('is_template', False)
        is_instance = item.get('is_instance', False)

        # Template actions
        self.edit_btn.setEnabled(is_template)
        self.delete_btn.setEnabled(is_template)
        self.duplicate_btn.setEnabled(is_template)

        # Instance actions
        self.convert_btn.setEnabled(is_instance)
        self.skip_btn.setEnabled(is_instance)

    def _on_item_clicked(self, index):
        """Handle click to expand/collapse."""
        if self.tree.isExpanded(index):
            self.tree.collapse(index)
        else:
            self.tree.expand(index)
```

---

## 9. Theme System

### 9.1 QSS Theme Files

```css
/* fidra/ui/theme/dark.qss */

/* ===== GLOBAL ===== */
* {
    font-family: "Inter", "SF Pro Display", -apple-system, system-ui, sans-serif;
    font-size: 13px;
}

QMainWindow, QWidget {
    background-color: #1a1d1b;
    color: #e5e7eb;
}

/* ===== TOP BAR ===== */
#topBar {
    background-color: #272a28;
    border-bottom: 1px solid #3f4240;
    min-height: 48px;
}

#topBar QLabel#logo {
    font-size: 18px;
    font-weight: bold;
    color: #ffffff;
}

/* ===== SIDEBAR ===== */
#sidebar {
    background-color: #272a28;
    border-right: 1px solid #3f4240;
    min-width: 260px;
    max-width: 320px;
}

#formHeader {
    font-size: 16px;
    font-weight: bold;
    color: #ffffff;
    padding: 8px 0;
}

/* ===== BUTTONS ===== */
QPushButton {
    background-color: #49564a;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    min-height: 32px;
}

QPushButton:hover {
    background-color: #5a6b5c;
}

QPushButton:pressed {
    background-color: #3f4c41;
}

QPushButton:disabled {
    background-color: #3f4240;
    color: #6b7280;
}

/* Type selector buttons */
#expenseButton {
    background-color: #92400e;
}

#expenseButton:hover {
    background-color: #a3510f;
}

#expenseButton:checked {
    background-color: #b45309;
    border: 2px solid #fbbf24;
}

#incomeButton {
    background-color: #065f46;
}

#incomeButton:hover {
    background-color: #047857;
}

#incomeButton:checked {
    background-color: #059669;
    border: 2px solid #34d399;
}

#submitButton {
    background-color: #92400e;
    font-size: 14px;
    min-height: 40px;
}

#submitButton:hover {
    background-color: #a3510f;
}

/* ===== INPUTS ===== */
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit {
    background-color: #1f2220;
    border: 1px solid #3f4240;
    border-radius: 4px;
    padding: 6px 10px;
    color: #e5e7eb;
    selection-background-color: #49564a;
}

QLineEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus {
    border-color: #49564a;
    border-width: 2px;
}

QLineEdit:disabled, QTextEdit:disabled {
    background-color: #272a28;
    color: #6b7280;
}

/* Placeholder text */
QLineEdit[placeholderText] {
    color: #6b7280;
}

/* ===== COMBOBOX ===== */
QComboBox {
    background-color: #1f2220;
    border: 1px solid #3f4240;
    border-radius: 4px;
    padding: 6px 10px;
    color: #e5e7eb;
    min-height: 28px;
}

QComboBox:hover {
    border-color: #49564a;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: url(:/icons/chevron-down.svg);
    width: 12px;
    height: 12px;
}

QComboBox QAbstractItemView {
    background-color: #2d302e;
    border: 1px solid #3f4240;
    selection-background-color: #49564a;
    color: #e5e7eb;
}

/* ===== TABLE ===== */
#transactionTable {
    background-color: transparent;
    alternate-background-color: #1f2220;
    gridline-color: #3f4240;
    border: none;
}

#transactionTable::item {
    padding: 8px 12px;
    border-bottom: 1px solid #3f4240;
}

#transactionTable::item:selected {
    background-color: #49564a;
    color: #ffffff;
}

#transactionTable::item:selected:!active {
    background-color: #3f4240;
}

/* Planned transaction rows (applied via setProperty or delegate) */
#transactionTable::item[planned="true"] {
    background-color: #1a2520;  /* Subtle teal tint */
    color: #9ca3af;             /* Muted text */
    border-left: 3px dashed #4a7c6f;
}

#transactionTable::item[planned="true"]:selected {
    background-color: #2a4540;
}

/* PLANNED status badge styling */
#plannedBadge {
    background-color: #2d4a44;
    color: #6ee7b7;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: bold;
}

QHeaderView::section {
    background-color: #272a28;
    color: #9ca3af;
    font-weight: bold;
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid #3f4240;
}

/* ===== SCROLLBARS ===== */
QScrollBar:vertical {
    background-color: #1a1d1b;
    width: 12px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #3f4240;
    border-radius: 6px;
    min-height: 30px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #4b5563;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* ===== STATUS BAR ===== */
QStatusBar {
    background-color: #272a28;
    border-top: 1px solid #3f4240;
    color: #9ca3af;
}

/* ===== DIALOGS ===== */
QDialog {
    background-color: #2d302e;
}

QDialogButtonBox QPushButton {
    min-width: 80px;
}

/* ===== MENUS ===== */
QMenu {
    background-color: #2d302e;
    border: 1px solid #3f4240;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #49564a;
}

QMenu::separator {
    height: 1px;
    background-color: #3f4240;
    margin: 4px 8px;
}

/* ===== TOOLTIPS ===== */
QToolTip {
    background-color: #2d302e;
    color: #e5e7eb;
    border: 1px solid #3f4240;
    border-radius: 4px;
    padding: 6px 10px;
}

/* ===== SPECIAL STATES ===== */
.income-row {
    background-color: rgba(16, 185, 129, 0.1);
}

.expense-row {
    background-color: rgba(239, 68, 68, 0.05);
}

.pending-row {
    color: #f59e0b;
}

.planned-row {
    color: #6b7280;
    font-style: italic;
}
```

```css
/* fidra/ui/theme/light.qss */

/* ===== GLOBAL ===== */
* {
    font-family: "Inter", "SF Pro Display", -apple-system, system-ui, sans-serif;
    font-size: 13px;
}

QMainWindow, QWidget {
    background-color: #f5f6f4;
    color: #111827;
}

/* ===== TOP BAR ===== */
#topBar {
    background-color: #ffffff;
    border-bottom: 1px solid #d1d5db;
    min-height: 48px;
}

#topBar QLabel#logo {
    font-size: 18px;
    font-weight: bold;
    color: #111827;
}

/* ===== SIDEBAR ===== */
#sidebar {
    background-color: #ffffff;
    border-right: 1px solid #d1d5db;
    min-width: 260px;
    max-width: 320px;
}

#formHeader {
    font-size: 16px;
    font-weight: bold;
    color: #111827;
    padding: 8px 0;
}

/* ===== BUTTONS ===== */
QPushButton {
    background-color: #6b8e6b;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    min-height: 32px;
}

QPushButton:hover {
    background-color: #5a7d5a;
}

QPushButton:pressed {
    background-color: #4a6d4a;
}

QPushButton:disabled {
    background-color: #d1d5db;
    color: #9ca3af;
}

/* Type selector buttons */
#expenseButton {
    background-color: #dc2626;
}

#expenseButton:hover {
    background-color: #b91c1c;
}

#expenseButton:checked {
    background-color: #ef4444;
    border: 2px solid #fca5a5;
}

#incomeButton {
    background-color: #059669;
}

#incomeButton:hover {
    background-color: #047857;
}

#incomeButton:checked {
    background-color: #10b981;
    border: 2px solid #6ee7b7;
}

#submitButton {
    background-color: #dc2626;
    font-size: 14px;
    min-height: 40px;
}

#submitButton:hover {
    background-color: #b91c1c;
}

/* ===== INPUTS ===== */
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 6px 10px;
    color: #111827;
    selection-background-color: #6b8e6b;
    selection-color: #ffffff;
}

QLineEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus {
    border-color: #6b8e6b;
    border-width: 2px;
}

/* ===== COMBOBOX ===== */
QComboBox {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 6px 10px;
    color: #111827;
    min-height: 28px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    selection-background-color: #6b8e6b;
    selection-color: #ffffff;
    color: #111827;
}

/* ===== TABLE ===== */
#transactionTable {
    background-color: #ffffff;
    alternate-background-color: #f9fafb;
    gridline-color: #e5e7eb;
    border: none;
}

#transactionTable::item {
    padding: 8px 12px;
    border-bottom: 1px solid #e5e7eb;
}

#transactionTable::item:selected {
    background-color: #6b8e6b;
    color: #ffffff;
}

#transactionTable::item:selected:!active {
    background-color: #d1d5db;
    color: #111827;
}

/* Planned transaction rows (light mode) */
#transactionTable::item[planned="true"] {
    background-color: #f0fdf4;  /* Subtle green tint */
    color: #6b7280;             /* Muted text */
    border-left: 3px dashed #86efac;
}

#transactionTable::item[planned="true"]:selected {
    background-color: #bbf7d0;
    color: #166534;
}

/* PLANNED status badge styling (light mode) */
#plannedBadge {
    background-color: #dcfce7;
    color: #166534;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: bold;
}

QHeaderView::section {
    background-color: #f3f4f6;
    color: #4b5563;
    font-weight: bold;
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid #d1d5db;
}

/* ===== SCROLLBARS ===== */
QScrollBar:vertical {
    background-color: #f5f6f4;
    width: 12px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #d1d5db;
    border-radius: 6px;
    min-height: 30px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #9ca3af;
}

/* ===== STATUS BAR ===== */
QStatusBar {
    background-color: #ffffff;
    border-top: 1px solid #d1d5db;
    color: #6b7280;
}

/* ===== DIALOGS ===== */
QDialog {
    background-color: #ffffff;
}

/* ===== MENUS ===== */
QMenu {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
    color: #111827;
}

QMenu::item:selected {
    background-color: #6b8e6b;
    color: #ffffff;
}
```

### 9.2 Theme Engine

```python
# fidra/ui/theme/engine.py

from pathlib import Path
from enum import Enum
from typing import Optional
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QObject, Signal

class ThemeMode(Enum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"

class ThemeEngine(QObject):
    """Manages application theming."""

    theme_changed = Signal(ThemeMode)

    _instance: Optional["ThemeEngine"] = None

    def __init__(self):
        super().__init__()
        self._current = ThemeMode.DARK
        self._themes_dir = Path(__file__).parent
        self._app: Optional[QApplication] = None

    @classmethod
    def instance(cls) -> "ThemeEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self, app: QApplication) -> None:
        """Initialize with QApplication reference."""
        self._app = app
        self.set_theme(self._current)

    @property
    def current(self) -> ThemeMode:
        return self._current

    def set_theme(self, mode: ThemeMode) -> None:
        """Apply a theme to the application."""
        if mode == ThemeMode.SYSTEM:
            mode = self._detect_system_theme()

        qss_path = self._themes_dir / f"{mode.value}.qss"
        if qss_path.exists() and self._app:
            stylesheet = qss_path.read_text()
            self._app.setStyleSheet(stylesheet)
            self._current = mode
            self.theme_changed.emit(mode)

    def toggle(self) -> ThemeMode:
        """Toggle between dark and light themes."""
        new_mode = ThemeMode.LIGHT if self._current == ThemeMode.DARK else ThemeMode.DARK
        self.set_theme(new_mode)
        return new_mode

    def apply_to(self, widget: QWidget) -> None:
        """Ensure widget uses current theme (for dynamically created widgets)."""
        # Qt automatically applies app stylesheet to new widgets
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _detect_system_theme(self) -> ThemeMode:
        """Detect system color scheme preference."""
        try:
            # macOS
            import subprocess
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True
            )
            if result.returncode == 0 and "Dark" in result.stdout:
                return ThemeMode.DARK
            return ThemeMode.LIGHT
        except Exception:
            return ThemeMode.DARK
```

---

## 10. Feature Specifications

### 10.1 Dashboard

The dashboard is the home view, providing an at-a-glance overview of financial health.

#### Stat Cards
| Card | Content | Update Trigger |
|------|---------|----------------|
| **Balance** | Current total balance (approved transactions) | Transaction change |
| **This Month** | Income and expense totals for current month | Transaction change |
| **Pending** | Count and total of pending transactions | Transaction change |

#### Charts
| Chart | Type | Data Range | Theme Integration |
|-------|------|------------|-------------------|
| **Balance Trend** | Line chart | Last 90 days | Line color = accent_primary |
| **Expenses by Category** | Horizontal bar | Current month | Bar colors from palette |
| **Income vs Expenses** | Grouped bar | Last 6 months | Income = green, Expense = red |

#### Upcoming Transactions
- Shows next 5 planned transactions (one-time or recurring)
- Displays days until due
- Clicking navigates to Planned view

#### Recent Transactions
- Shows last 5-10 transactions
- "View All →" button navigates to Transactions view
- Quick preview without leaving dashboard

### 10.2 Transaction Management

#### Add Transaction
| Field | Type | Required | Validation | Default |
|-------|------|----------|------------|---------|
| Date | date | Yes | Valid date | Today |
| Description | string | Yes | Non-empty, max 500 chars | - |
| Amount | Decimal | Yes | > 0, max 999999.99 | - |
| Type | enum | Yes | "income" or "expense" | "expense" |
| Category | string | No | From list or custom | First in list |
| Party | string | No | Max 200 chars | - |
| Notes | string | No | Max 2000 chars | - |
| Sheet | string | Yes | Existing sheet | Current sheet |

**Behavior:**
- Income transactions auto-approved (status = "--")
- Expense transactions start as "pending"
- Form clears after successful submission
- Confirmation toast shown
- Table scrolls to new transaction
- Undo operation recorded

#### Edit Transaction
- Single click to select, double-click or Enter to edit
- Opens edit dialog with all fields
- Validates changes before saving
- Records undo operation with old and new state
- Supports changing sheet (moves transaction)
- Version check for optimistic concurrency

#### Bulk Edit
- Shift+Click or Ctrl+Click to multi-select
- Opens bulk edit dialog
- Only shows fields with identical values
- Changed fields apply to all selected
- Single undo operation for entire bulk edit

#### Delete Transaction
- Confirmation dialog required
- Soft delete option (mark as rejected) vs hard delete
- Undo operation recorded with full transaction data
- Bulk delete supported

### 10.3 Planned Transactions

Planned transactions represent **future expected** transactions. They can be:
- **One-time**: A single expected transaction on a specific date (default)
- **Recurring**: Repeats on a schedule until end date or occurrence limit

#### Create Planned Template
| Field | Type | Required | Validation | Default |
|-------|------|----------|------------|---------|
| Start Date | date | Yes | >= today | Today |
| Description | string | Yes | Non-empty | - |
| Amount | Decimal | Yes | > 0 | - |
| Type | enum | Yes | "income" or "expense" | "expense" |
| Frequency | enum | No | once/weekly/biweekly/monthly/quarterly/yearly | **once** |
| Target Sheet | string | Yes | Existing non-virtual sheet | Current |
| Category | string | No | - | - |
| Party | string | No | - | - |
| End Date | date | No | > start date (only for recurring) | - |
| Occurrence Count | int | No | > 0 (only for recurring) | - |

**Behavior:**
- Templates stored in "Planned_Transactions" sheet
- One-time templates expand to single instance on start_date
- Recurring templates expand to multiple instances up to horizon/end
- Instances generated on-the-fly (not persisted)
- Instances have deterministic IDs based on template + date
- Display with "PLANNED" status
- Cannot approve/reject planned instances
- Affects balance when "Include Planned" enabled
- Shows in Dashboard's "Upcoming" list

#### Frequency Expansion Rules
| Frequency | Behavior |
|-----------|----------|
| **Once** | Single occurrence on start date only |
| Weekly | +7 days from previous occurrence |
| Biweekly | +14 days from previous occurrence |
| Monthly | Same day next month (clamped to month end) |
| Quarterly | +3 months from previous occurrence |
| Yearly | +1 year from previous occurrence |

#### Planned Instance Interactions (in Transactions View)

When viewing planned instances mixed with actuals (Show Planned = ON):

| Action | Behavior | Data Changes |
|--------|----------|--------------|
| **Convert to Actual** | Creates a real transaction pre-filled from the planned instance | New transaction added to target sheet; instance optionally marked as "fulfilled" in template metadata |
| **Skip Instance** | Hides this specific occurrence from projections | Adds skip date to template's `skipped_dates` list; template continues generating other instances |
| **Edit Template** | Opens source template for modification | Navigates to Planned view with template selected |

**Skip Instance Details:**
- Skipping is reversible (can un-skip from Planned view)
- Skipped instances don't appear in balance projections
- Useful for "I won't pay rent this month because..." scenarios
- Stored as: `template.skipped_dates: list[date]`

**Convert to Actual Details:**
- Pre-fills all fields from planned instance (date, amount, description, etc.)
- User can modify before saving (e.g., actual amount differed)
- Option to auto-skip the planned instance after conversion
- Undo operation recorded

### 10.4 Approval Workflow

```
                    ┌─────────────┐
                    │   INCOME    │
                    │  (auto --)  │
                    └─────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   PENDING   │────▶│  APPROVED   │     │  REJECTED   │
│  (expense)  │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   ▲                   ▲
       │                   │                   │
       └───────────────────┴───────────────────┘
              (via context menu or action bar)
```

**Rules:**
- Income: Always "--" (auto-approved), cannot change
- Expense: Starts "pending", can become "approved" or "rejected"
- Only approved/planned expenses count toward balance
- Rejected expenses remain in data but don't affect balance
- Status changes are undoable

### 10.5 Search & Filter

**Query Syntax:**
```
term                    # Simple substring search
term1 AND term2         # Both must match
term1 OR term2          # Either matches
NOT term                # Excludes matches
(term1 OR term2) AND term3  # Grouping with parentheses
"exact phrase"          # Quoted exact match
```

**Searchable Fields:**
- Date (YYYY-MM-DD format)
- Description
- Amount (as string)
- Type (income/expense)
- Category
- Party
- Status
- Notes
- Sheet

**Filtered Balance Mode:**
- Toggle in search bar
- When ON: Balance shows sum of filtered transactions only
- When OFF: Balance shows all transactions regardless of filter

### 10.6 Balance Calculation

**Two Balance Modes:**

| Mode | Formula | Display Location |
|------|---------|------------------|
| **Current Balance** | Actuals only | Balance card (always shown) |
| **Projected Balance** | Actuals + Planned | Balance card (when Show Planned = ON) |

**Current Balance Formula:**
```
Current = Σ(approved_income) - Σ(approved_expense)
```

**Projected Balance Formula:**
```
Projected = Current
          + Σ(planned_income within horizon, not skipped)
          - Σ(planned_expense within horizon, not skipped)
```

**Included in Balance:**
| Type | Status | Current Balance | Projected Balance |
|------|--------|-----------------|-------------------|
| Income | -- | Yes | Yes |
| Income | approved | Yes | Yes |
| Income | PLANNED | No | Yes (if not skipped) |
| Expense | pending | No | No |
| Expense | approved | Yes | Yes |
| Expense | PLANNED | No | Yes (if not skipped) |
| Expense | rejected | No | No |

**Running Balance in Table:**
- Calculated per row in chronological order
- When Show Planned = OFF: Only actuals contribute to running balance
- When Show Planned = ON: Running balance includes planned instances up to horizon
- Skipped planned instances excluded from running balance

**Balance Display Panel:**
```
┌─────────────────┐
│ Current Balance │
│    £4,521.30    │  ← Actuals only (always accurate)
│                 │
│ Projected (90d) │  ← Only shown when Show Planned = ON
│    £6,136.80    │
│    ▲ +£1,615    │  ← Net change from planned
└─────────────────┘
```

### 10.7 Forecasting

**Parameters:**
- Horizon: Number of days to project (default 90)
- Include Past Planned: Show missed planned transactions

**Projection:**
1. Start with current actual balance
2. Expand all planned templates within horizon
3. Add/subtract planned instances by date
4. Display projected balance at horizon date

**Display:**
- Current balance prominent
- Projected balance with date
- Optional chart showing balance trajectory

### 10.8 Reports & Charts

#### Balance Over Time (Line Chart)
- X-axis: Date
- Y-axis: Running balance
- Data: Approved transactions only
- Interactive: Hover for details

#### Monthly Summary (Bar Chart)
- X-axis: Month (YYYY-MM)
- Y-axis: Amount
- Bars: Income (green), Expense (red)
- Line overlay: Net (blue)

#### Expense Breakdown (Pie Chart)
- Segments: Categories
- Values: Sum of approved expenses per category
- Interactive: Click segment to filter table

### 10.9 Export Formats

| Format | Extension | Contents |
|--------|-----------|----------|
| CSV | .csv | All fields, UTF-8, comma-separated |
| Excel | .xlsx | Formatted workbook with sheets |
| Markdown | .md | Monthly sections, tables |
| PDF | .pdf | Formatted report with summary |
| LaTeX | .tex | Table format for academic use |
| Clipboard | - | TSV for pasting into spreadsheets |

---

## 11. Keyboard Shortcuts

### 11.1 Global Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd+Z` / `Ctrl+Z` | Undo |
| `Cmd+Shift+Z` / `Ctrl+Y` | Redo |
| `Cmd+N` / `Ctrl+N` | Focus add form |
| `Cmd+F` / `Ctrl+F` | Focus search |
| `Cmd+,` / `Ctrl+,` | Open settings |
| `Escape` | Cancel edit / Clear selection / Close dialog |

### 11.2 Table Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Edit selected transaction |
| `Delete` / `Backspace` | Delete selected (with confirmation) |
| `A` | Approve selected (if pending expense) |
| `R` | Reject selected (if pending expense) |
| `Up` / `Down` | Navigate rows |
| `Shift+Click` | Extend selection |
| `Cmd+Click` / `Ctrl+Click` | Toggle selection |
| `Cmd+A` / `Ctrl+A` | Select all |

### 11.3 Form Shortcuts

| Shortcut | Action |
|----------|--------|
| `Tab` | Next field / Autocomplete |
| `Shift+Tab` | Previous field |
| `Enter` | Submit form (when in last field) |
| `Escape` | Clear form |

### 11.4 Export Shortcuts

| Shortcut | Action |
|----------|--------|
| `C` | Copy table to clipboard |
| `L` | Copy as LaTeX |
| `E` | Export CSV |
| `P` | Export PDF |
| `M` | Export Markdown |

---

## 12. File Structure

```
fidra/
├── pyproject.toml              # Project configuration
├── README.md                   # Documentation
├── main.py                     # Entry point
│
├── fidra/
│   ├── __init__.py
│   ├── app.py                  # Application context & orchestration
│   │
│   ├── domain/                 # Core business logic (no dependencies)
│   │   ├── __init__.py
│   │   ├── models.py           # Transaction, PlannedTemplate, Sheet, Category
│   │   └── settings.py         # AppSettings (Pydantic model)
│   │
│   ├── data/                   # Data access layer
│   │   ├── __init__.py
│   │   ├── repository.py       # Abstract interfaces
│   │   ├── sqlite_repo.py      # SQLite implementation
│   │   ├── excel_adapter.py    # Excel implementation
│   │   └── factory.py          # Repository factory
│   │
│   ├── services/               # Business services
│   │   ├── __init__.py
│   │   ├── balance.py          # Balance calculations
│   │   ├── forecast.py         # Planned expansion & projection
│   │   ├── search.py           # Query parsing & filtering
│   │   ├── undo.py             # Command pattern & undo stack
│   │   ├── export.py           # Export strategies
│   │   └── file_watch.py       # File change monitoring
│   │
│   ├── state/                  # State management
│   │   ├── __init__.py
│   │   ├── observable.py       # Reactive state primitives
│   │   ├── app_state.py        # Application state container
│   │   └── persistence.py      # Settings storage
│   │
│   └── ui/                     # User interface
│       ├── __init__.py
│       ├── main_window.py      # Main window
│       │
│       ├── components/         # Reusable widgets
│       │   ├── __init__.py
│       │   ├── top_bar.py
│       │   ├── sidebar.py
│       │   ├── add_form.py
│       │   ├── add_planned_form.py
│       │   ├── transaction_table.py
│       │   ├── search_bar.py
│       │   ├── action_bar.py
│       │   ├── right_panel.py
│       │   ├── balance_display.py
│       │   └── forecast_controls.py
│       │
│       ├── dialogs/            # Modal dialogs
│       │   ├── __init__.py
│       │   ├── message.py
│       │   ├── edit_dialog.py
│       │   ├── bulk_edit_dialog.py
│       │   ├── settings_dialog.py
│       │   └── conflict_dialog.py
│       │
│       ├── views/              # Main navigation views
│       │   ├── __init__.py
│       │   ├── dashboard_view.py    # Dashboard with stats & charts
│       │   ├── transactions_view.py # Transaction list & forms
│       │   ├── planned_view.py      # Planned transactions list
│       │   └── reports_view.py      # Reports & exports
│       │
│       ├── models/             # Qt models
│       │   ├── __init__.py
│       │   └── transaction_model.py
│       │
│       └── theme/              # Theming
│           ├── __init__.py
│           ├── engine.py
│           ├── dark.qss
│           └── light.qss
│
├── resources/                  # Static assets
│   ├── icons/
│   │   ├── app.icns
│   │   ├── app.ico
│   │   └── *.svg
│   └── fonts/
│
├── tests/                      # Test suite
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures
│   ├── domain/
│   │   └── test_models.py
│   ├── services/
│   │   ├── test_balance.py
│   │   ├── test_forecast.py
│   │   ├── test_search.py
│   │   └── test_undo.py
│   ├── data/
│   │   └── test_repository.py
│   └── ui/
│       └── test_components.py
│
└── scripts/                    # Build & deployment
    ├── build_macos.sh
    ├── build_windows.bat
    └── package.py
```

---

## 13. Implementation Phases

### Phase 1: Foundation (Week 1-2)

**Goals:** Core infrastructure, basic data flow

**Tasks:**
1. Project setup (pyproject.toml, dependencies)
2. Domain models (Transaction, PlannedTemplate)
3. SQLite repository implementation
4. Basic state management (Observable, AppState)
5. Main window shell with layout

**Deliverable:** App opens, connects to database, shows empty window

### Phase 2: Transaction CRUD (Week 3-4)

**Goals:** Full transaction management

**Tasks:**
1. Transaction table with model/view
2. Add transaction form
3. Edit transaction dialog
4. Delete with confirmation
5. Undo/redo for all operations
6. Balance calculation

**Deliverable:** Can add, edit, delete transactions with undo

### Phase 3: Planned & Approval (Week 5-6)

**Goals:** Planned transactions, approval workflow

**Tasks:**
1. Add planned form
2. Frequency expansion service
3. Planned instance display
4. Approval status workflow
5. Context menu actions
6. Include planned toggle

**Deliverable:** Full planned transaction support

### Phase 4: Search & Filter (Week 7)

**Goals:** Advanced search capabilities

**Tasks:**
1. Search bar UI
2. Query parser (AND/OR/NOT)
3. Real-time filtering
4. Filtered balance mode
5. Result counter

**Deliverable:** Boolean search working

### Phase 5: Reports & Export (Week 8-9)

**Goals:** Visualization and export

**Tasks:**
1. Balance chart (Plotly + WebEngine)
2. Monthly summary chart
3. Expense breakdown chart
4. CSV/Markdown/PDF export
5. Clipboard copy

**Deliverable:** All reports and exports functional

### Phase 6: Polish & Themes (Week 10)

**Goals:** Visual polish, theming

**Tasks:**
1. Dark theme QSS
2. Light theme QSS
3. Theme switching
4. Settings dialog
5. Keyboard shortcuts
6. Status bar

**Deliverable:** Polished, themeable interface

### Phase 7: Testing & Packaging (Week 11-12)

**Goals:** Quality assurance, distribution

**Tasks:**
1. Unit tests for services
2. Integration tests for repository
3. UI tests with pytest-qt
4. macOS app bundle
5. Windows installer
6. Documentation

**Deliverable:** Tested, packaged application

---

## 14. Testing Strategy

### 14.1 Unit Tests

**Domain Models:**
```python
# tests/domain/test_models.py

def test_transaction_creation():
    t = Transaction.create(
        date=date(2024, 1, 15),
        description="Test",
        amount=Decimal("100.00"),
        type=TransactionType.EXPENSE,
        sheet="Main"
    )
    assert t.status == ApprovalStatus.PENDING
    assert t.amount == Decimal("100.00")

def test_transaction_immutability():
    t = Transaction.create(...)
    t2 = t.with_updates(amount=Decimal("200.00"))
    assert t.amount == Decimal("100.00")  # Original unchanged
    assert t2.amount == Decimal("200.00")
    assert t2.version == t.version + 1

def test_income_auto_approved():
    t = Transaction.create(
        ...,
        type=TransactionType.INCOME
    )
    assert t.status == ApprovalStatus.AUTO
```

**Services:**
```python
# tests/services/test_balance.py

def test_compute_total():
    service = BalanceService()
    transactions = [
        make_transaction(type="income", amount=100, status="--"),
        make_transaction(type="expense", amount=50, status="approved"),
        make_transaction(type="expense", amount=30, status="pending"),
    ]
    assert service.compute_total(transactions) == Decimal("50.00")

# tests/services/test_search.py

def test_and_query():
    service = SearchService()
    transactions = [
        make_transaction(description="Fuel for car"),
        make_transaction(description="Fuel for boat"),
        make_transaction(description="Car repair"),
    ]
    results = service.search(transactions, "fuel AND car")
    assert len(results) == 1
    assert results[0].description == "Fuel for car"

def test_not_query():
    service = SearchService()
    transactions = [...]
    results = service.search(transactions, "fuel NOT boat")
    assert len(results) == 1
```

### 14.2 Integration Tests

```python
# tests/data/test_repository.py

@pytest.fixture
async def repo(tmp_path):
    db_path = tmp_path / "test.db"
    repo = SQLiteTransactionRepository(db_path)
    await repo.connect()
    yield repo
    await repo.close()

async def test_save_and_retrieve(repo):
    t = Transaction.create(...)
    saved = await repo.save(t)

    retrieved = await repo.get_by_id(saved.id)
    assert retrieved.description == t.description

async def test_optimistic_concurrency(repo):
    t = Transaction.create(...)
    await repo.save(t)

    # Simulate concurrent edit
    t2 = t.with_updates(description="Updated")
    t3 = t.with_updates(description="Conflict")

    await repo.save(t2)

    with pytest.raises(ConcurrencyError):
        await repo.save(t3)
```

### 14.3 UI Tests

```python
# tests/ui/test_components.py

@pytest.fixture
def app(qtbot):
    ctx = create_test_context()
    window = MainWindow(ctx)
    qtbot.addWidget(window)
    return window

def test_add_transaction(app, qtbot):
    # Fill form
    form = app.sidebar.add_form
    form.desc_edit.setText("Test Transaction")
    form.amount_edit.setValue(50.00)

    # Submit
    qtbot.mouseClick(form.submit_btn, Qt.LeftButton)

    # Verify
    assert len(app._ctx.state.transactions.value) == 1
    assert app._ctx.state.transactions.value[0].description == "Test Transaction"

def test_search_filters_table(app, qtbot):
    # Add test data
    app._ctx.state.transactions.set([
        make_transaction(description="Fuel"),
        make_transaction(description="Food"),
    ])

    # Search
    app.table.search_bar.search_edit.setText("fuel")

    # Verify filtering
    assert app.table.proxy.rowCount() == 1
```

### 14.4 Test Fixtures

```python
# tests/conftest.py

import pytest
from decimal import Decimal
from datetime import date
from domain.models import Transaction, TransactionType, ApprovalStatus

@pytest.fixture
def make_transaction():
    def _make(**kwargs):
        defaults = {
            'date': date.today(),
            'description': 'Test',
            'amount': Decimal('100.00'),
            'type': TransactionType.EXPENSE,
            'sheet': 'Main',
        }
        defaults.update(kwargs)
        return Transaction.create(**defaults)
    return _make

@pytest.fixture
def sample_transactions(make_transaction):
    return [
        make_transaction(description="Fuel", amount=Decimal("50.00")),
        make_transaction(description="Food", amount=Decimal("30.00"), type=TransactionType.INCOME),
        make_transaction(description="Rent", amount=Decimal("800.00"), status=ApprovalStatus.APPROVED),
    ]
```

---

## Appendix A: Color Palette Reference

### Dark Theme
| Token | Hex | Usage |
|-------|-----|-------|
| `bg-app` | #1a1d1b | Main background |
| `bg-panel` | #272a28 | Sidebar, cards |
| `bg-input` | #1f2220 | Input fields |
| `border` | #3f4240 | Borders, dividers |
| `text-primary` | #e5e7eb | Main text |
| `text-secondary` | #9ca3af | Labels, hints |
| `accent-primary` | #49564a | Primary buttons |
| `accent-success` | #10b981 | Income, success |
| `accent-warning` | #f59e0b | Pending |
| `accent-error` | #ef4444 | Expense, error |

### Light Theme
| Token | Hex | Usage |
|-------|-----|-------|
| `bg-app` | #f5f6f4 | Main background |
| `bg-panel` | #ffffff | Sidebar, cards |
| `bg-input` | #ffffff | Input fields |
| `border` | #d1d5db | Borders, dividers |
| `text-primary` | #111827 | Main text |
| `text-secondary` | #6b7280 | Labels, hints |
| `accent-primary` | #6b8e6b | Primary buttons |
| `accent-success` | #059669 | Income, success |
| `accent-warning` | #d97706 | Pending |
| `accent-error` | #dc2626 | Expense, error |

---

## Appendix B: Database Schema

```sql
-- Core tables
CREATE TABLE transactions (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    status TEXT NOT NULL CHECK (status IN ('--', 'pending', 'approved', 'rejected', 'planned')),
    sheet TEXT NOT NULL,
    category TEXT,
    party TEXT,
    notes TEXT,
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    modified_at TEXT,
    modified_by TEXT
);

CREATE TABLE planned_templates (
    id TEXT PRIMARY KEY,
    start_date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    frequency TEXT NOT NULL CHECK (frequency IN ('once', 'weekly', 'biweekly', 'monthly', 'quarterly', 'yearly')),
    target_sheet TEXT NOT NULL,
    category TEXT,
    party TEXT,
    end_date TEXT,
    occurrence_count INTEGER,
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE sheets (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    is_virtual INTEGER DEFAULT 0,
    is_planned INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX idx_transactions_date ON transactions(date);
CREATE INDEX idx_transactions_sheet ON transactions(sheet);
CREATE INDEX idx_transactions_type ON transactions(type);
CREATE INDEX idx_transactions_status ON transactions(status);
CREATE INDEX idx_planned_target ON planned_templates(target_sheet);

-- Triggers for audit
CREATE TRIGGER update_modified_at
AFTER UPDATE ON transactions
BEGIN
    UPDATE transactions SET modified_at = datetime('now') WHERE id = NEW.id;
END;
```

---

## Appendix C: Settings Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "profile": {
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "initials": { "type": "string", "maxLength": 3 }
      }
    },
    "theme": {
      "type": "object",
      "properties": {
        "mode": { "enum": ["dark", "light", "system"] }
      }
    },
    "storage": {
      "type": "object",
      "properties": {
        "backend": { "enum": ["sqlite", "excel"] },
        "last_file": { "type": "string" }
      }
    },
    "forecast": {
      "type": "object",
      "properties": {
        "horizon_days": { "type": "integer", "minimum": 1, "maximum": 365 },
        "include_past_planned": { "type": "boolean" }
      }
    },
    "logging": {
      "type": "object",
      "properties": {
        "level": { "enum": ["DEBUG", "INFO", "WARNING", "ERROR"] }
      }
    },
    "income_categories": {
      "type": "array",
      "items": { "type": "string" }
    },
    "expense_categories": {
      "type": "array",
      "items": { "type": "string" }
    },
    "example_descriptions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "example_parties": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

---

*Document Version: 1.0*
*Last Updated: January 2025*
*Author: Claude (Anthropic)*
