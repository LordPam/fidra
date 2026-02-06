# Phase 4: Search & Filter - Implementation Complete

**Date**: 2026-01-16

## Overview

Phase 4 adds powerful boolean search capabilities with real-time filtering to the Fidra application. Users can now search transactions using AND/OR/NOT operators with parentheses for grouping, and optionally calculate balance from filtered transactions only.

---

## Features Implemented

### 1. SearchService - Boolean Query Engine ✅

**File**: `fidra/services/search.py`

Implements a full boolean query parser and matcher:

- **Supported Operators**:
  - `AND` - Both terms must match
  - `OR` - Either term must match
  - `NOT` - Exclude term
  - `()` - Grouping for complex queries

- **Query Parsing**:
  - Tokenization of input query
  - Conversion to Reverse Polish Notation (RPN) using Shunting-yard algorithm
  - Compilation to efficient matcher function

- **Search Fields**:
  - Description
  - Amount (as string)
  - Type (income/expense)
  - Status (auto/pending/approved/rejected/planned)
  - Category
  - Party
  - Notes

- **Features**:
  - Case-insensitive matching
  - Graceful error handling (malformed queries return all transactions)
  - Operator precedence: NOT > AND > OR

**Example Queries**:
```
coffee                        # Simple term
coffee AND fuel               # Both terms
coffee OR fuel                # Either term
NOT pending                   # Exclude pending
(coffee OR fuel) AND car      # Grouping
coffee AND NOT pending        # Combined
```

**Algorithm**: Uses Shunting-yard algorithm to convert infix notation to RPN, then evaluates RPN using a stack-based interpreter.

---

### 2. SearchBar Component ✅

**File**: `fidra/ui/components/search_bar.py`

A feature-rich search widget with:

- **Search Input**:
  - Debounced text input (300ms delay)
  - Clear button built-in
  - Placeholder text with example query
  - Tooltip showing syntax help

- **Result Count Display**:
  - Shows "12 of 150 transactions" when filtered
  - Shows "150 transactions" when no filter active

- **Filtered Balance Toggle**:
  - Checkbox to enable filtered balance mode
  - When ON: Balance calculated from visible transactions only
  - When OFF: Balance shows all transactions regardless of filter

- **Signals**:
  - `search_changed(str)` - Emitted after debounce when query changes
  - `filter_mode_changed(bool)` - Emitted when checkbox toggled

**UX Features**:
- Real-time search with debouncing to avoid lag
- Clear visual feedback on result count
- Tooltip explains both search syntax and filtered balance mode

---

### 3. TransactionsView Integration ✅

**File**: `fidra/ui/views/transactions_view.py`

Integrated SearchBar into main transactions view:

- **Layout**:
  - Search bar positioned between header and transaction table
  - Full width for easy visibility

- **Search Filtering**:
  - Applied after "Show Planned" toggle (searches both actual and planned transactions)
  - Filters displayed transactions in table
  - Updates result count in real-time

- **Filtered Balance Mode**:
  - When enabled: Balance calculated from filtered transactions only
  - When disabled: Balance shows all actual transactions regardless of filter
  - Useful for answering questions like "How much did I spend on coffee this month?"

- **Search Query State**:
  - Stored in `_current_search_query`
  - Persisted across state updates
  - Filters applied automatically when transactions change

**Implementation Details**:
```python
# Modified _get_display_transactions() to apply search filter:
if self._current_search_query and self._current_search_query.strip():
    filtered = self._context.search_service.search(
        base_transactions,
        self._current_search_query
    )
    return filtered
else:
    return base_transactions

# Balance calculation respects filter mode:
if self.search_bar.is_filter_mode():
    balance_transactions = [t for t in display_transactions if t.status != ApprovalStatus.PLANNED]
else:
    balance_transactions = transactions
```

---

### 4. Application Context Update ✅

**File**: `fidra/app.py`

Added SearchService to application context:

```python
from fidra.services.search import SearchService

self.search_service = SearchService()
```

Now available throughout the application via dependency injection.

---

## Test Coverage

**File**: `tests/services/test_search.py`

Comprehensive test suite with 33 tests covering:

### Simple Search Tests (10 tests)
- Empty query returns all
- Whitespace query returns all
- Single term matching
- Case-insensitive search
- Search in description, category, party, notes, status
- No matches returns empty list

### Boolean AND Tests (4 tests)
- Both terms must match
- One term missing returns no results
- Multiple AND terms
- Case-insensitive AND operator

### Boolean OR Tests (4 tests)
- Either term matches
- Both terms match
- No terms match returns empty
- Case-insensitive OR operator

### Boolean NOT Tests (3 tests)
- NOT excludes matching transactions
- NOT combined with AND
- NOT to exclude status

### Parentheses Tests (3 tests)
- Grouping with parentheses
- Nested parentheses
- Parentheses with NOT

### Complex Query Tests (3 tests)
- Combined AND/OR/NOT queries
- Operator precedence (AND > OR)
- Multiple NOT operators

### Edge Cases (6 tests)
- Empty transactions list
- Malformed queries (graceful degradation)
- Only operators, no terms
- Consecutive operators
- Search with numeric amount
- Search with decimal amount

**Result**: All 33 search tests passing ✅
**Total Tests**: 139/139 passing ✅

---

## User Guide

### How to Search

1. **Simple Search**:
   - Type a term in the search bar
   - Transactions containing that term (anywhere) will be shown
   - Example: `coffee` shows all coffee-related transactions

2. **AND Search**:
   - Type `term1 AND term2`
   - Only transactions containing both terms
   - Example: `coffee AND morning` shows morning coffee purchases

3. **OR Search**:
   - Type `term1 OR term2`
   - Transactions containing either term
   - Example: `coffee OR tea` shows all coffee and tea purchases

4. **NOT Search**:
   - Type `NOT term`
   - Excludes transactions with that term
   - Example: `NOT pending` shows all non-pending transactions

5. **Complex Search**:
   - Combine operators with parentheses
   - Example: `(coffee OR tea) AND NOT pending`
   - Example: `expense AND (food OR transport) AND NOT rejected`

6. **Filtered Balance**:
   - Check "Filtered Balance" to calculate balance from visible transactions only
   - Useful for answering "How much did I spend on X?"
   - Uncheck to see total balance regardless of filter

### Search Tips

- **Case doesn't matter**: `COFFEE`, `coffee`, and `Coffee` all work the same
- **Search everything**: Searches across description, amount, category, party, notes, status
- **Operator precedence**: NOT binds tightest, then AND, then OR
  - `coffee OR fuel AND car` = `coffee OR (fuel AND car)`
  - Use parentheses to override: `(coffee OR fuel) AND car`
- **Malformed queries**: If query is invalid, all transactions are shown (no error)

---

## Technical Implementation Details

### Boolean Query Parsing

The search engine uses a three-step process:

1. **Tokenization**: Break query string into tokens (terms, operators, parentheses)
2. **RPN Conversion**: Convert infix notation to Reverse Polish Notation using Shunting-yard algorithm
3. **Compilation**: Build a matcher function from RPN using stack-based evaluation

**Why RPN?**
- Easier to evaluate (no need to handle precedence during execution)
- Efficient stack-based algorithm
- Natural way to represent complex boolean expressions

**Example**:
```
Input:  "coffee AND (fuel OR car)"
Tokens: [coffee, AND, (, fuel, OR, car, )]
RPN:    [coffee, fuel, car, OR, AND]
Eval:   Push(coffee), Push(fuel), Push(car), OR(pop, pop), AND(pop, pop)
```

### Debouncing

Search input is debounced with 300ms delay to avoid excessive filtering during typing:

```python
def _on_text_changed(self, text: str) -> None:
    self._debounce_timer.stop()
    self._debounce_timer.start(300)  # 300ms delay
```

This provides smooth UX while minimizing CPU usage.

### Filter Mode vs Normal Mode

**Normal Mode** (default):
- Search filters what you **see**
- Balance shows **all** transactions
- Use case: "Find specific transactions but show total balance"

**Filter Mode** (checkbox enabled):
- Search filters what you **see**
- Balance shows **filtered** transactions only
- Use case: "How much did I spend on coffee?"

---

## Files Modified

1. **New Files**:
   - `fidra/services/search.py` - SearchService implementation
   - `fidra/ui/components/search_bar.py` - SearchBar widget
   - `tests/services/test_search.py` - Search tests

2. **Modified Files**:
   - `fidra/app.py` - Added SearchService to context
   - `fidra/ui/views/transactions_view.py` - Integrated SearchBar

---

## Performance Considerations

- **Debouncing**: 300ms delay avoids re-filtering on every keystroke
- **Linear Search**: O(n) complexity - acceptable for expected dataset size (< 10,000 transactions)
- **Lazy Compilation**: Matcher function compiled once per query change, not per transaction
- **Early Exit**: Boolean operators short-circuit when possible

For very large datasets (100,000+ transactions), could add optimizations:
- Index-based search for common terms
- Caching of compiled matchers
- Background thread for search execution

Not needed for current scope.

---

## Known Limitations

1. **No Regex**: Terms are simple substring matches, not regular expressions
2. **No Wildcards**: Cannot search for `cof*` to match `coffee`, `coffeehouse`, etc.
3. **No Field-Specific Search**: Cannot search just description with `description:coffee`
4. **Error Handling**: Malformed queries silently return all transactions (could show error message instead)

These are intentional scope limitations for Phase 4. Can be added in future phases if needed.

---

## What's Next?

Phase 4 is complete! Next steps according to the plan:

**Phase 5: Reports & Export**
- Dashboard with charts (balance trend, expense breakdown)
- Export to CSV, Markdown, PDF
- Clipboard export (TSV, LaTeX)

**Phase 6: Themes & Polish**
- Dark/light theme system
- Settings dialog
- Keyboard shortcuts
- Visual polish

**Phase 7: Testing & Packaging**
- Comprehensive test coverage
- Distributable packages

---

**Status**: ✅ Phase 4 Complete - 139/139 tests passing

