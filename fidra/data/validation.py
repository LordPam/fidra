"""Database validation utilities for Fidra."""

import sqlite3
from pathlib import Path
from typing import Optional


class DatabaseValidationError(Exception):
    """Raised when database validation fails."""

    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message)
        self.details = details


# Required tables for a valid Fidra database
REQUIRED_TABLES = {"transactions"}

# Tables that will be created if missing (optional but expected)
OPTIONAL_TABLES = {"planned_templates", "sheets", "attachments", "audit_log"}

# Required columns in the transactions table
REQUIRED_TRANSACTION_COLUMNS = {
    "id", "date", "description", "amount", "type", "status", "sheet"
}


def validate_database(db_path: Path) -> None:
    """Validate that a database file is a compatible Fidra database.

    Args:
        db_path: Path to the database file

    Raises:
        DatabaseValidationError: If the database is not compatible
    """
    if not db_path.exists():
        # New database - will be created with correct schema
        return

    # Check if it's a valid SQLite file
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        raise DatabaseValidationError(
            "Not a valid database file",
            f"Could not open as SQLite database: {e}"
        )

    try:
        # Get list of tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}

        # Check for required tables
        missing_required = REQUIRED_TABLES - existing_tables
        if missing_required:
            # Check if this is an empty database (no tables at all)
            if not existing_tables:
                # Empty database - will be initialized with schema
                return

            # Has tables but not the required ones - incompatible
            raise DatabaseValidationError(
                "Incompatible database format",
                f"This database is missing required tables: {', '.join(missing_required)}. "
                "It may not be a Fidra database file."
            )

        # Validate transactions table schema
        cursor = conn.execute("PRAGMA table_info(transactions)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        missing_columns = REQUIRED_TRANSACTION_COLUMNS - existing_columns
        if missing_columns:
            raise DatabaseValidationError(
                "Incompatible database schema",
                f"The transactions table is missing required columns: {', '.join(missing_columns)}. "
                "This database may be from an older or different application."
            )

    except sqlite3.Error as e:
        raise DatabaseValidationError(
            "Database error during validation",
            f"Could not read database structure: {e}"
        )
    finally:
        conn.close()


def is_valid_fidra_database(db_path: Path) -> tuple[bool, Optional[str]]:
    """Check if a database file is a valid Fidra database.

    Args:
        db_path: Path to the database file

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        validate_database(db_path)
        return True, None
    except DatabaseValidationError as e:
        return False, f"{e}\n\n{e.details}" if e.details else str(e)
