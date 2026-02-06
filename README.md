# Fidra 2.0

A local-first financial ledger application for treasurers and individuals who need to track income, expenses, planned transactions, and generate financial reports.

## Features (Phase 1 - Foundation)

- ✅ Immutable domain models (Transaction, PlannedTemplate, Sheet)
- ✅ SQLite data layer with async support
- ✅ Reactive state management
- ✅ Basic Qt UI shell
- ✅ Settings persistence
- ✅ Comprehensive test coverage

## Installation

### Prerequisites
- Python 3.11 or higher
- uv (recommended) or pip

### Setup

```bash
# Clone the repository
cd Fidra

# Install dependencies with uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Or with pip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
# Run the application
python main.py

# Run tests
pytest

# Run linting
ruff check fidra

# Run type checking
mypy fidra
```

## Architecture

```
Domain Layer (models: Transaction, PlannedTemplate, Sheet, Category)
    ↓
Data Layer (SQLite repositories with abstract interface)
    ↓
State Layer (reactive observables, centralized AppState)
    ↓
UI Layer (PySide6 with tab navigation)
```

## Development Status

**Current Phase**: Phase 1 - Foundation ✅ COMPLETE

### Phase 1 Completed
- ✅ Project structure and configuration
- ✅ Domain models (Transaction, PlannedTemplate, Sheet, Category)
- ✅ AppSettings with Pydantic validation
- ✅ Data layer (SQLite repositories with async support)
- ✅ State management (Observable, AppState, persistence)
- ✅ ApplicationContext for dependency injection
- ✅ Main window shell with navigation
- ✅ Entry point with qasync integration
- ✅ **57 passing tests** (100% coverage of implemented features)

### Verification Results
```
✅ Application initializes successfully
✅ Database connects and creates schema
✅ Transactions save and retrieve correctly
✅ Optimistic concurrency control works
✅ Settings persist to ~/.fidra_settings.json
✅ State management reactive updates work
✅ Main window displays with navigation
```

### Future Phases
- Phase 2: Transaction CRUD & Balance
- Phase 3: Planned Transactions & Approval
- Phase 4: Search & Filter
- Phase 5: Reports & Export
- Phase 6: Themes & Polish
- Phase 7: Testing & Packaging

## Design Principles

1. **Local-First**: All data stored locally, no cloud dependency
2. **Immutable Data**: Transaction objects are immutable; updates create new instances
3. **Reactive UI**: State changes automatically update the interface
4. **Command Pattern**: All mutations via commands for undo/redo
5. **Type Safety**: Full type annotations throughout
6. **Testability**: Dependency injection enables unit testing

## License

Private project - All rights reserved

## Contributing

This is currently a private project. Please contact the maintainer for contribution guidelines.
