# Fidra - Quick Start Guide

## Installation

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Run tests (should see 90 passing)
pytest -v

# 3. Run the application
python main.py
```

## What Works Now

### Phase 1 - Foundation ✅ COMPLETE
✅ **Application launches** with main window
✅ **Database connectivity** (SQLite with async support)
✅ **Data persistence** (transactions save/load correctly)
✅ **Settings management** (persists to ~/.fidra_settings.json)
✅ **Reactive state** (Observable pattern with Qt signals)
✅ **Navigation** (4 tabs: Dashboard, Transactions, Planned, Reports)

### Phase 2 - Transaction CRUD & Balance ✅ COMPLETE
✅ **Balance Service** - Computes total, running balances, pending total (10 tests)
✅ **Undo/Redo Service** - Command pattern with undo stack (12 tests)
✅ **Transaction Table** - Sortable, multi-select, context menus (11 tests)
✅ **Add Transaction Form** - Left sidebar form with validation
✅ **Edit Transaction Dialog** - Modal dialog for editing
✅ **Balance Display** - Prominent balance with change indicator
✅ **Transactions View** - Full layout with all components wired
✅ **Commands integrated** - All mutations through undo/redo system
✅ **Keyboard shortcuts** - Cmd+Z (undo), Cmd+N (new), Delete, Enter, A (approve), R (reject)
✅ **End-to-end tested** - All features working

### Test Coverage
✅ **All 90 tests pass** (57 Phase 1 + 33 Phase 2)
✅ **100% coverage** on all components

### Try It Out!

```bash
python main.py
```

**What you can do:**
1. Click "Transactions" tab to see the full UI
2. Add transactions using the left sidebar form (Shift+Enter to submit)
3. Double-click or press E to edit
4. Right-click for context menu (Approve/Reject/Delete)
   - Note: Approve/Reject only works on expenses (income is auto-approved)
5. Press A to approve, R to reject selected **expense** transactions
6. Press Cmd+Z to undo any operation
7. See balance update in real-time on the right

**Balance calculation:**
- **Counts**: Income (AUTO, APPROVED), Expenses (APPROVED only)
- **Excludes**: PENDING, REJECTED, and PLANNED statuses
- PLANNED transactions are for forecasting (Phase 3)

## What's Coming Next (Phase 3)

Phase 3 will add:
- Planned transactions with frequency expansion (weekly, monthly, etc.)
- Show planned toggle - mix planned with actual transactions
- Convert planned to actual
- Template management

## Project Structure

```
fidra/
├── domain/          # Business logic & models
│   ├── models.py       # Transaction, PlannedTemplate, Sheet, Category
│   └── settings.py     # AppSettings with Pydantic
├── data/            # Data access layer
│   ├── repository.py   # Abstract interfaces
│   ├── sqlite_repo.py  # SQLite implementation
│   └── factory.py      # Repository factory
├── state/           # State management
│   ├── observable.py   # Observable<T> container
│   ├── app_state.py    # Central app state
│   └── persistence.py  # Settings storage
├── ui/              # User interface
│   └── main_window.py  # Main window with navigation
└── app.py           # ApplicationContext (DI container)
```

## Testing

```bash
# Run all tests
pytest -v

# Run specific test file
pytest tests/domain/test_models.py -v

# Run with coverage
pytest --cov=fidra

# Type checking
mypy fidra

# Linting
ruff check fidra
```

## Development Workflow

1. **Make changes** to code
2. **Run tests** to ensure nothing broke: `pytest`
3. **Check types** with mypy: `mypy fidra`
4. **Format code** with ruff: `ruff check fidra`
5. **Run app** to test manually: `python main.py`

## Database Location

The SQLite database is created at:
```
./fidra.db
```

Settings are stored at:
```
~/.fidra_settings.json
```

## Example: Adding a Transaction Programmatically

```python
import asyncio
from datetime import date
from decimal import Decimal
from fidra.app import ApplicationContext
from fidra.domain.models import Transaction, TransactionType

async def example():
    # Initialize app
    ctx = ApplicationContext()
    await ctx.initialize()
    
    # Create a transaction
    trans = Transaction.create(
        date=date(2024, 1, 15),
        description="Coffee",
        amount=Decimal("4.50"),
        type=TransactionType.EXPENSE,
        sheet="Main",
        category="Food"
    )
    
    # Save it
    await ctx.transaction_repo.save(trans)
    
    # Load all transactions
    all_trans = await ctx.transaction_repo.get_all()
    print(f"Total transactions: {len(all_trans)}")
    
    await ctx.close()

asyncio.run(example())
```

## Architecture

Fidra follows a clean layered architecture:

```
┌─────────────────────────────────────┐
│      UI Layer (PySide6)             │
│  (Main Window, Views, Dialogs)      │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│      State Layer                    │
│  (Observable, AppState)             │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│      Data Layer                     │
│  (Repositories, SQLite)             │
└─────────────────┬───────────────────┘
                  │
┌─────────────────▼───────────────────┐
│      Domain Layer                   │
│  (Models, Business Logic)           │
└─────────────────────────────────────┘
```

## Key Design Principles

1. **Immutability**: Domain models are frozen dataclasses
2. **Reactive UI**: State changes trigger UI updates via Qt signals
3. **Type Safety**: Full type annotations throughout
4. **Clean Architecture**: Clear separation of concerns
5. **Testability**: Dependency injection enables easy testing
6. **Async/Await**: Non-blocking I/O operations

## Need Help?

- Check `FIDRA_BLUEPRINT.md` for complete specification
- Check `PHASE1_COMPLETE.md` for Phase 1 summary
- Check `README.md` for project overview
- Run tests to see examples: `pytest -v`

---

**Phase 1 Complete** ✅ | Ready for Phase 2 Implementation
