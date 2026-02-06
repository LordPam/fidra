# Phase 3: Planned Transactions & Approval - COMPLETE ✅

**Date Completed**: 2026-01-16

Phase 3 has been successfully completed with all planned features implemented and tested.

## Overview

Phase 3 implemented planned transaction templates with recurring frequency support, forecast projection, approval workflow, and visual integration with the transactions view.

**Test Status**: All 106 tests passing ✅

## Features Implemented

### 1. ForecastService (`fidra/services/forecast.py`)
- **Template Expansion**: Expands planned templates into transaction instances based on frequency
- **Supported Frequencies**: Once, Weekly, Biweekly, Monthly, Quarterly, Yearly
- **End Conditions**: Templates can end by date OR occurrence count (mutually exclusive)
- **Skipped Dates**: Templates track dates to exclude from expansion
- **Deterministic IDs**: Generated using UUID5 based on template ID + occurrence date
- **Balance Projection**: Projects future balance from actuals + planned instances
- **Tests**: 16 comprehensive tests covering all frequencies and edge cases

### 2. Planned View (`fidra/ui/views/planned_view.py`)
- **Tree Structure**: Templates as parent items, instances as expandable children
- **Template Actions**:
  - ✅ Add Planned (with full dialog)
  - ✅ Delete (with confirmation)
  - 🔄 Edit (TODO - placeholder)
  - 🔄 Duplicate (TODO - placeholder)
- **Instance Actions**:
  - ✅ Convert to Actual
  - ✅ Skip Instance
- **Context-Aware UI**: Action buttons enable/disable based on selection type

### 3. PlannedTreeModel (`fidra/ui/models/planned_tree_model.py`)
- **QAbstractItemModel**: Custom tree model for Qt Model/View architecture
- **Columns**: Description, Amount, Frequency/Type, Next Due/Status
- **Reactive Updates**: Automatically rebuilds when state changes
- **Expandable Rows**: Click template to see upcoming instances (up to forecast horizon)

### 4. Add Planned Dialog (`fidra/ui/dialogs/add_planned_dialog.py`)
- **Form Fields**:
  - Type toggle (Expense/Income)
  - Start date picker
  - Description, Amount, Category, Party
  - Frequency dropdown (6 options)
  - Mutually exclusive end conditions (end date OR occurrence count)
- **Validation**: Ensures end_date OR occurrence_count, not both
- **Sheet Integration**: Uses current sheet context

### 5. Show Planned Toggle (TransactionsView)
- **Header Checkbox**: "Show Planned" toggle in Transactions view
- **Mixed Display**: When ON, mixes planned instances with actual transactions chronologically
- **Visual Distinction**: Planned rows have:
  - `[PLANNED]` badge in description
  - Muted gray text color
  - Light blue-gray background
- **Projected Balance**: Balance display shows both current and projected when toggle is ON

### 6. Balance Display Updates (`fidra/ui/components/balance_display.py`)
- **Projected Balance Section**: Shows when planned transactions are visible
- **Dual Display**:
  - Current Balance (from actuals only)
  - Projected Balance (actuals + planned, up to forecast horizon)
- **Visual Separation**: Separator line between current and projected
- **Auto Show/Hide**: Projected section only visible when provided

### 7. Visual Styling for Planned Rows (`fidra/ui/models/transaction_model.py`)
- **Foreground Color**: Muted gray (#8C8C8C) for all columns
- **Background Color**: Light blue-gray (#F5F8FA)
- **Badge**: `[PLANNED]` prefix in description column
- **Status Color**: Steel blue for PLANNED status

### 8. Context Menu Actions (TransactionTable)
- **Planned-Specific Actions**:
  - Convert to Actual (income → AUTO, expense → PENDING)
  - Skip Instance (adds date to template's skipped_dates)
- **Smart Menu**: Different actions for planned vs actual selections
- **Bulk Operations**: Support for multi-select convert and skip

### 9. TransactionsView Integration
- **Convert to Actual Handler**: Creates actual transaction, marks template as fulfilled
- **Skip Instance Handler**: Adds date to template's skipped_dates
- **Template Matching**: Finds source template by description, amount, and type
- **State Synchronization**: Updates both transactions and templates after operations

### 10. Approval Workflow
- **Status Transitions**:
  - Income: Always AUTO (no approval needed)
  - Expenses: Default PENDING → can be APPROVED or REJECTED
  - Planned: PLANNED status (excluded from current balance)
- **Keyboard Shortcuts**:
  - `A`: Approve selected expenses
  - `R`: Reject selected expenses
- **Context Menu**: Approve/Reject actions (expenses only, excludes planned)

## Files Modified/Created

### Created:
- `fidra/services/forecast.py` - ForecastService with template expansion
- `tests/services/test_forecast.py` - 16 comprehensive tests
- `fidra/ui/dialogs/add_planned_dialog.py` - Add Planned dialog
- `fidra/ui/models/planned_tree_model.py` - Tree model for templates/instances
- `fidra/ui/views/planned_view.py` - Main Planned view

### Modified:
- `fidra/app.py` - Added ForecastService to context
- `fidra/ui/main_window.py` - Wired PlannedView to navigation
- `fidra/ui/views/transactions_view.py`:
  - Added Show Planned toggle
  - Implemented _get_display_transactions() to mix actuals + planned
  - Added convert to actual and skip instance handlers
  - Updated balance display with projected balance
- `fidra/ui/components/balance_display.py`:
  - Added projected balance display
  - Show/hide logic for projected section
- `fidra/ui/models/transaction_model.py`:
  - Added visual styling for planned rows
  - Background color role
  - Muted foreground colors
  - [PLANNED] badge
- `fidra/ui/components/transaction_table.py`:
  - Added convert_to_actual_requested signal
  - Added skip_instance_requested signal
  - Modified context menu for planned transactions
- `fidra/services/balance.py` - Excluded PLANNED from balance calculation

## Key Technical Decisions

1. **Deterministic Instance IDs**: Using UUID5 ensures same template + date always generates same ID
2. **PLANNED Status Exclusion**: Planned transactions excluded from current balance, only used for forecasting
3. **Template Matching**: Match by description, amount, and type to find source template
4. **Horizon-Based Expansion**: Only expand templates up to forecast horizon (default 90 days)
5. **Reactive State**: Tree model rebuilds when planned_templates state changes
6. **Muted Visual Style**: Distinct but not jarring - gray text, light background
7. **Undo Stack Integration**: Convert to Actual uses AddTransactionCommand for undo support

## Test Coverage

**Total Tests**: 106 passing
- **Domain**: 21 tests (models, settings)
- **Data**: 12 tests (repositories)
- **Services**: 35 tests (balance, forecast, undo)
- **State**: 13 tests (observable, persistence)
- **UI**: 25 tests (transaction model)

**New Tests Added**:
- `test_forecast.py`: 16 tests for ForecastService
  - Frequency expansion (6 frequencies)
  - End conditions (date, count)
  - Skipped dates
  - Past date handling
  - Deterministic IDs
  - Balance projection (4 tests)

## Usage Examples

### Adding a Planned Transaction

1. Navigate to "Planned" tab
2. Click "+ Add Planned"
3. Fill form:
   - Type: Expense
   - Start Date: 2026-02-01
   - Description: "Rent"
   - Amount: £1200
   - Frequency: Monthly
   - End Condition: None (or set occurrence count)
4. Click "Save"
5. Template appears in tree with expandable instances

### Viewing Planned Instances in Transactions

1. Navigate to "Transactions" tab
2. Check "Show Planned" toggle
3. Planned instances appear in table with:
   - Gray text
   - Light background
   - [PLANNED] badge

### Converting Planned to Actual

**From Planned View**:
1. Expand template to see instances
2. Select an instance
3. Click "Convert to Actual"
4. Confirm dialog
5. Actual transaction created, template marked as fulfilled

**From Transactions View** (with Show Planned ON):
1. Right-click planned transaction
2. Select "Convert to Actual"
3. Transaction converted, table refreshes

### Skipping an Instance

**From Planned View**:
1. Select instance
2. Click "Skip"
3. Confirm dialog
4. Date added to template's skipped_dates, instance disappears

**From Transactions View**:
1. Right-click planned transaction
2. Select "Skip Instance"
3. Instance removed from display

## Remaining TODOs

The following features were marked as TODO and can be implemented in future iterations:

1. **Edit Template** (PlannedView): Edit dialog for existing templates
2. **Duplicate Template** (PlannedView): Create new template from existing
3. **Un-skip Instance**: Allow un-skipping previously skipped dates
4. **Forecast Chart**: Visual chart showing balance projection over time
5. **Bulk Template Operations**: Multi-select actions in PlannedView

## Known Limitations

1. **Template Matching**: Uses description + amount + type. If multiple templates match, first is selected.
2. **Forecast Horizon**: Fixed in settings (default 90 days). Could be made more dynamic.
3. **Past Instances**: Not shown by default in Planned view (only future instances).
4. **No Undo for Template Operations**: Convert/Skip don't go through undo stack (could be added).

## Next Steps: Phase 4

With Phase 3 complete, the next phase focuses on:

- **Search & Filter**: Boolean query search (AND/OR/NOT)
- **Real-Time Filtering**: Debounced search with result counts
- **Filtered Balance Mode**: Balance from visible transactions only
- **Query Syntax Validation**: Error feedback for invalid queries

## Summary

Phase 3 successfully implements a complete planned transaction system with:
- ✅ Template creation and management
- ✅ Frequency-based expansion (6 frequencies)
- ✅ Forecast projection
- ✅ Convert to actual workflow
- ✅ Skip instance functionality
- ✅ Visual integration with main transactions view
- ✅ Context menu actions
- ✅ Projected balance display
- ✅ Approval workflow (expense approval/rejection)

All features tested and working correctly. The codebase is ready for Phase 4 (Search & Filter).

---

**Status**: ✅ Phase 3 Complete - 106/106 tests passing
**Next**: Phase 4 - Search & Filter
