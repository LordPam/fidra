# Recurring Instances Fix - Phase 3 Updates

**Date**: 2026-01-16

## Issues Fixed

### 1. Converted Instances Still Showing ✅

**Problem**: When you convert a recurring planned instance to actual, it was still appearing in the tree view and transactions view. This allowed converting the same instance multiple times, causing version conflicts.

**Root Cause**: `ForecastService.expand_template()` was only checking `skipped_dates` but not `fulfilled_dates` when generating instances.

**Solution**: Updated `expand_template()` to also exclude dates in `fulfilled_dates`:

```python
# Before:
if current not in template.skipped_dates:
    instances.append(self._create_instance(template, current))

# After:
if current not in template.skipped_dates and current not in template.fulfilled_dates:
    instances.append(self._create_instance(template, current))
```

**Result**:
- ✅ Converted instances immediately disappear from both tree view and transactions view
- ✅ Prevents duplicate conversions and version conflicts
- ✅ Only unconverted future instances remain visible

**Files Modified**:
- `fidra/services/forecast.py`

---

### 2. Unclear Individual vs Template Deletion ✅

**Problem**: The UI wasn't clear about the difference between:
- Deleting a single occurrence (individual)
- Deleting the entire template (all future instances)

The old "Skip Instance" label sounded temporary, when it's actually permanent.

**Solution**: Updated all context menus and buttons with clearer labels:

#### TransactionsView Context Menu (for planned transactions):
- ✅ **Convert to Actual** - Creates actual transaction, marks as fulfilled
- ✅ **Delete This Instance** - Permanently removes just this occurrence
- ✅ **Delete Entire Template** - Removes all future instances

#### PlannedView Action Buttons:
- ✅ **Convert to Actual** - Convert instance to actual transaction
- ✅ **Delete This Instance** - Permanently remove this occurrence only

**Confirmation Dialogs** now clearly explain:
- "Delete This Instance": "Permanently delete this occurrence on [date]? This will remove only this single occurrence. Other future instances will remain."
- "Delete Entire Template": "Are you sure you want to delete [N] planned template(s)? This will remove all future instances of this planned transaction."

**Files Modified**:
- `fidra/ui/components/transaction_table.py`
- `fidra/ui/views/planned_view.py`
- `fidra/ui/views/transactions_view.py`

---

## Summary of Changes

### What Changed:

1. **ForecastService** now filters out both skipped AND fulfilled dates
2. **Context menu labels** clarified:
   - "Skip Instance" → "Delete This Instance"
   - Added clearer explanations in confirmation dialogs
3. **PlannedView button** renamed from "Skip" to "Delete This Instance"

### User Experience Improvements:

#### Before:
- ❌ Converted instances still showed in tree (could convert twice)
- ❌ "Skip Instance" sounded temporary
- ❌ Unclear difference between individual and template deletion

#### After:
- ✅ Converted instances automatically disappear
- ✅ "Delete This Instance" clearly indicates permanence
- ✅ "Delete Entire Template" clearly indicates scope
- ✅ Confirmation dialogs explain exactly what will happen
- ✅ No more version conflicts from duplicate conversions

---

## Context Menu Structure

### Planned Transactions (TransactionsView & PlannedView):

When you right-click a planned transaction:

```
┌─────────────────────────────────┐
│ Convert to Actual (1)           │
├─────────────────────────────────┤
│ Delete This Instance (1)        │  ← Single occurrence only
│ Delete Entire Template (1)      │  ← All future instances
├─────────────────────────────────┤
│ (other options...)              │
└─────────────────────────────────┘
```

### Behavior:

- **Convert to Actual**:
  - Creates actual transaction (AUTO for income, PENDING for expense)
  - Marks date as fulfilled in template
  - Instance disappears from view (filtered by fulfilled_dates)
  - One-time templates: Template deleted entirely
  - Recurring templates: Only that date marked as fulfilled

- **Delete This Instance**:
  - Adds date to `skipped_dates` (permanent)
  - Instance disappears from view
  - Other instances remain
  - Template persists

- **Delete Entire Template**:
  - Deletes template entirely
  - All future instances disappear
  - Cannot be undone (confirmation required)

---

## Technical Details

### fulfilled_dates vs skipped_dates

**fulfilled_dates**:
- Set when instance is converted to actual
- Prevents regeneration of that specific date
- Indicates "already happened"

**skipped_dates**:
- Set when user deletes individual instance
- Prevents regeneration of that specific date
- Indicates "don't want this occurrence"

Both are checked during `expand_template()` to exclude instances.

### One-Time vs Recurring Templates

**One-Time Templates** (Frequency.ONCE):
- When converted to actual → Template deleted entirely
- No future instances possible anyway

**Recurring Templates**:
- When converted to actual → Date added to fulfilled_dates, template persists
- When instance deleted → Date added to skipped_dates, template persists
- Template keeps generating future instances

---

## Test Status

**All 106 tests passing** ✅

No regressions. All existing functionality working correctly.

---

## Files Modified

1. `fidra/services/forecast.py` - Added fulfilled_dates check
2. `fidra/ui/components/transaction_table.py` - Updated context menu labels
3. `fidra/ui/views/planned_view.py` - Renamed button, updated dialog
4. `fidra/ui/views/transactions_view.py` - Updated confirmation dialog

---

## Migration Notes

No database migration needed. The `fulfilled_dates` and `skipped_dates` fields already exist in the `PlannedTemplate` model.

---

## User Guide

### To Convert a Planned Instance to Actual:
1. In Transactions view with "Show Planned" ON, or in Planned view
2. Right-click the planned instance
3. Select "Convert to Actual"
4. Instance disappears (now fulfilled)
5. Actual transaction created

### To Delete a Single Occurrence:
1. Right-click the planned instance
2. Select "Delete This Instance"
3. Confirm deletion
4. Instance disappears permanently
5. Other future instances remain

### To Delete All Future Instances:
1. Right-click any planned instance (or template in Planned view)
2. Select "Delete Entire Template"
3. Confirm deletion
4. All future instances disappear
5. Template deleted from database

---

**Status**: ✅ All issues resolved - 106/106 tests passing
