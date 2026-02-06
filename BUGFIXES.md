# Bug Fixes - Phase 3 Updates

**Date**: 2026-01-16

## Issues Fixed

### 1. PLANNED Status in Edit Dialog ✅

**Problem**: Users could manually set transactions to PLANNED status through the edit dialog, which caused:
- AttributeError when forecast service tried to process them (expected Transaction instances, got wrong data)
- Confusion between actual database transactions and template-generated instances

**Solution**:
- Removed "Planned" from status dropdown in edit dialog
- Income: Only AUTO status (dropdown disabled)
- Expense: Only Pending, Approved, or Rejected
- Added comments explaining PLANNED is only for template-generated instances

**Files Modified**:
- `fidra/ui/dialogs/edit_dialog.py`

---

### 2. AttributeError: 'PlannedTemplate' has no attribute 'date' ✅

**Problem**: `project_balance()` was being called with wrong arguments in TransactionsView:
```python
# WRONG:
project_balance(transactions, templates, horizon)

# Expected:
project_balance(current_balance, planned_instances, horizon)
```

**Solution**:
- Fixed `_on_transactions_changed()` to properly expand templates to instances first
- Pass correct arguments: current balance (Decimal), planned instances (list), horizon (date)

**Files Modified**:
- `fidra/ui/views/transactions_view.py`

---

### 3. One-Time Templates Not Deleted After Conversion ✅

**Problem**: When converting a one-time (non-recurring) planned transaction to actual, the template remained in the database even though it would never generate more instances.

**Solution**:
- Check template frequency during conversion
- If `Frequency.ONCE`: Delete template entirely
- If recurring: Mark as fulfilled (keeps generating future instances)

**Files Modified**:
- `fidra/ui/views/planned_view.py`
- `fidra/ui/views/transactions_view.py`

---

### 4. TransactionsView Not Auto-Refreshing ✅

**Problem**: When deleting or modifying a planned template from PlannedView, the TransactionsView didn't update automatically when "Show Planned" was ON. User had to toggle the checkbox to refresh.

**Solution**:
- Added signal listener: `planned_templates.changed.connect(_on_planned_templates_changed)`
- Automatically refreshes display when templates change (only if Show Planned is ON)

**Files Modified**:
- `fidra/ui/views/transactions_view.py`

---

### 5. No Way to Delete Templates from TransactionsView ✅

**Problem**: Users could only delete planned templates from the Planned tab. When viewing planned instances in the Transactions view (with Show Planned ON), there was no way to delete the source template.

**Solution**:
- Added "Delete Template" action to context menu for planned transactions
- Shows confirmation dialog warning that all future instances will be removed
- Automatically updates both views after deletion (via state signals)

**Context Menu for Planned Transactions**:
- Convert to Actual (income → AUTO, expense → PENDING)
- Skip Instance (marks date as skipped)
- **Delete Template** (NEW - removes entire template)

**Files Modified**:
- `fidra/ui/components/transaction_table.py` (added signal)
- `fidra/ui/views/transactions_view.py` (added handler)

---

## Utility Script Created

**File**: `cleanup_planned_transactions.py`

Utility to clean up any existing PLANNED transactions in the database from before the fix:

```bash
# Convert PLANNED to actual (PENDING/AUTO)
python cleanup_planned_transactions.py

# Or delete them permanently
python cleanup_planned_transactions.py --delete
```

---

## Summary of Changes

### Files Modified:
1. `fidra/ui/dialogs/edit_dialog.py` - Removed PLANNED from status options
2. `fidra/ui/views/transactions_view.py` - Fixed project_balance args, added auto-refresh, delete template
3. `fidra/ui/views/planned_view.py` - Delete one-time templates after conversion
4. `fidra/ui/components/transaction_table.py` - Added Delete Template context menu action

### Files Created:
1. `cleanup_planned_transactions.py` - Database cleanup utility
2. `BUGFIXES.md` - This file

---

## Test Status

**All 106 tests passing** ✅

No regressions introduced. All existing functionality working as expected.

---

## User Experience Improvements

### Before:
- ❌ Could manually set transactions to PLANNED (caused errors)
- ❌ One-time templates remained after conversion
- ❌ Had to toggle Show Planned to refresh after template changes
- ❌ Could only delete templates from Planned tab

### After:
- ✅ PLANNED status only for template-generated instances
- ✅ One-time templates automatically deleted after conversion
- ✅ TransactionsView auto-refreshes when templates change
- ✅ Can delete templates from both Planned and Transactions views
- ✅ Clear confirmation dialog warns about removing future instances

---

## Known Limitations

1. **Template Matching**: Uses description + amount + type to find source template. If multiple templates match, first is selected.
2. **No Undo for Template Deletion**: Delete template doesn't go through undo stack (could be added in future).

---

## Next Steps

If you still have old PLANNED transactions in your database:
1. Run `python cleanup_planned_transactions.py`
2. Choose convert (safer) or delete
3. Restart the application

All fixed issues tested and verified working correctly.
