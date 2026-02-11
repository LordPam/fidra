"""Application settings with Pydantic validation.

Settings are stored as JSON and validated using Pydantic models.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class ProfileSettings(BaseModel):
    """User profile settings."""

    name: str = ""
    initials: str = Field(default="", max_length=4)
    first_run_complete: bool = False

    model_config = {"validate_assignment": True}


class ThemeSettings(BaseModel):
    """Theme configuration."""

    mode: str = Field(default="dark", pattern="^(dark|light|system)$")

    model_config = {"validate_assignment": True}


class SupabaseSettings(BaseModel):
    """Supabase/PostgreSQL connection settings."""

    project_name: Optional[str] = None  # Display name (e.g., "Sub Aqua Club")
    project_url: Optional[str] = None  # e.g., "https://xxx.supabase.co"
    anon_key: Optional[str] = None  # Public anon key for Storage API
    db_connection_string: Optional[str] = None  # Direct PostgreSQL connection
    storage_bucket: str = "attachments"

    # Connection pool settings
    pool_min_size: int = Field(default=2, ge=1, le=10)
    pool_max_size: int = Field(default=10, ge=2, le=50)

    model_config = {"validate_assignment": True}

    def get_display_name(self) -> str:
        """Get a display name for the Supabase project."""
        if self.project_name:
            return self.project_name
        # Try to extract from project URL (e.g., "https://abc123.supabase.co" -> "abc123")
        if self.project_url:
            import re
            match = re.search(r'https?://([^.]+)\.supabase\.co', self.project_url)
            if match:
                return match.group(1)
        return "Supabase"


class StorageSettings(BaseModel):
    """Storage backend configuration."""

    backend: str = Field(default="sqlite", pattern="^(sqlite|excel|supabase)$")
    last_file: Optional[Path] = None
    last_opened_at: Optional[str] = None  # ISO format datetime string
    supabase: SupabaseSettings = Field(default_factory=SupabaseSettings)

    model_config = {"validate_assignment": True}


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")


class ForecastSettings(BaseModel):
    """Forecasting configuration."""

    horizon_days: int = Field(default=180, ge=7, le=730)  # 1 week to 2 years
    include_past_planned: bool = True

    model_config = {"validate_assignment": True}


class UIStateSettings(BaseModel):
    """UI state to persist across sessions."""

    show_planned: bool = False
    filtered_balance_mode: bool = False
    current_sheet: str = "All Sheets"
    theme: str = Field(default="light", pattern="^(light|dark)$")

    model_config = {"validate_assignment": True}


class BackupSettings(BaseModel):
    """Backup configuration settings."""

    backup_dir: Optional[Path] = None  # None = default (next to DB)
    retention_count: int = Field(default=10, ge=1, le=100)
    auto_backup_on_close: bool = True

    model_config = {"validate_assignment": True}


class TransactionSettings(BaseModel):
    """Transaction behavior settings."""

    # When approving a transaction, set its date to today
    date_on_approve: bool = False

    # When converting a planned transaction to actual, set its date to today
    date_on_planned_conversion: bool = True

    model_config = {"validate_assignment": True}


class FinancialYearSettings(BaseModel):
    """Financial year configuration.

    The financial year start month determines how annual periods are calculated.
    For example, UK clubs typically run April-March (start_month=4).
    """

    start_month: int = Field(default=1, ge=1, le=12)  # 1=January, 4=April, etc.

    model_config = {"validate_assignment": True}


class AppSettings(BaseModel):
    """Application settings with validation.

    All settings are validated using Pydantic. Invalid values will raise
    validation errors when loading from JSON.

    Example:
        >>> settings = AppSettings()
        >>> settings.theme.mode = "dark"
        >>> settings.forecast.horizon_days = 90
    """

    profile: ProfileSettings = Field(default_factory=ProfileSettings)
    theme: ThemeSettings = Field(default_factory=ThemeSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    forecast: ForecastSettings = Field(default_factory=ForecastSettings)
    financial_year: FinancialYearSettings = Field(default_factory=FinancialYearSettings)
    ui_state: UIStateSettings = Field(default_factory=UIStateSettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)
    transactions: TransactionSettings = Field(default_factory=TransactionSettings)

    income_categories: list[str] = Field(
        default_factory=lambda: [
            "Membership Dues",
            "Event Income",
            "Donations",
            "Grants",
            "Other Income",
        ]
    )

    expense_categories: list[str] = Field(
        default_factory=lambda: [
            "Equipment",
            "Training",
            "Events",
            "Administration",
            "Travel",
            "Other",
        ]
    )

    example_descriptions: list[str] = Field(default_factory=list)
    example_parties: list[str] = Field(default_factory=list)

    # Sheet display order (list of sheet names in desired order)
    sheet_order: list[str] = Field(default_factory=list)

    model_config = {
        "validate_assignment": True,  # Validate on attribute assignment
        "extra": "forbid",  # Forbid extra fields
    }
