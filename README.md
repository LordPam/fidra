# Fidra 2.0

A local-first financial ledger application for treasurers and individuals who need to track income, expenses, planned transactions, and generate financial reports. Supports optional cloud sync via PostgreSQL (Supabase or self-hosted).

## Features

- **Transaction Management**: Add, edit, delete, and bulk-edit transactions with undo/redo
- **Planned Transactions**: Recurring templates (weekly, monthly, quarterly, yearly) with auto-expansion
- **Approval Workflow**: Pending/Approved/Rejected status for expenses
- **Cloud Sync**: Optional PostgreSQL backend with offline-first caching and background sync
- **Real-Time Updates**: PostgreSQL LISTEN/NOTIFY for instant cross-device sync
- **Attachments**: Receipt/document uploads via Supabase Storage
- **Dashboard**: Balance overview, charts, and upcoming transactions
- **Search & Filter**: Boolean query search across all fields
- **Reports & Export**: CSV, Markdown, and PDF export with customisable reports
- **Multi-Sheet Support**: Organise transactions across multiple accounts/sheets
- **Themes**: Light and dark mode

## Installation

### Prerequisites
- Python 3.11 or higher
- uv (recommended) or pip

### Setup

```bash
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
```

## Architecture

```
Domain Layer (models: Transaction, PlannedTemplate, Sheet, Category)
    ↓
Data Layer (SQLite local + PostgreSQL cloud, abstract repository interface)
    ↓
Sync Layer (SyncQueue, CachingRepository, SyncService, ChangeListener)
    ↓
State Layer (reactive observables, centralised AppState)
    ↓
UI Layer (PySide6 with tab navigation, dark/light themes)
```

### Cloud Sync Architecture

When connected to a cloud server:

- **CachingRepository**: Reads from local SQLite cache, writes locally then queues for sync
- **SyncQueue**: Persistent SQLite queue of pending changes (survives app restarts)
- **SyncService**: Background service that pushes queued changes to PostgreSQL
  - Event-driven: changes sync within ~1s via debounced queue callbacks
  - Safety-net: 30s polling timer catches any missed events
- **ChangeListener**: PostgreSQL LISTEN/NOTIFY for real-time remote change detection
- **ConnectionStateService**: Health monitoring with automatic reconnection
  - 5s recovery checks when offline, 30s health checks when connected
  - Auto-recovery when network returns (no restart needed)

## Cloud Setup

See [docs/cloud-setup-guide.md](docs/cloud-setup-guide.md) for Supabase configuration instructions.

## Design Principles

1. **Local-First**: Works fully offline; cloud sync is optional
2. **Immutable Data**: Transaction objects are immutable; updates create new instances
3. **Reactive UI**: State changes automatically update the interface
4. **Type Safety**: Full type annotations throughout
5. **Testability**: Dependency injection and abstract repositories enable unit testing

## License

Private project - All rights reserved

## Contributing

This is currently a private project. Please contact the maintainer for contribution guidelines.
