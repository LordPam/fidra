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


class CloudStorageProvider(BaseModel):
    """Configuration for cloud file storage provider.

    Currently supports Supabase Storage. Future providers could include
    S3, local network storage, etc.
    """

    provider: str = Field(default="supabase", pattern="^(supabase|s3|local)$")

    # Supabase Storage settings
    project_url: Optional[str] = None  # e.g., "https://xxx.supabase.co"
    anon_key: Optional[str] = None  # Public anon key for Storage API
    bucket: str = "attachments"

    # S3 settings (for future use)
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: Optional[str] = None

    model_config = {"validate_assignment": True}


class CloudServerConfig(BaseModel):
    """Configuration for a cloud database server.

    Stores connection details for a PostgreSQL server (Supabase, self-hosted, etc.)
    along with optional cloud storage configuration for attachments.
    """

    id: str  # Unique identifier (UUID)
    name: str  # Display name (e.g., "Sub Aqua Club")
    db_connection_string: str  # PostgreSQL connection string
    storage: CloudStorageProvider = Field(default_factory=CloudStorageProvider)

    # Connection pool settings
    pool_min_size: int = Field(default=2, ge=1, le=10)
    pool_max_size: int = Field(default=10, ge=2, le=50)

    created_at: Optional[str] = None  # ISO format datetime

    model_config = {"validate_assignment": True}

    def get_display_name(self) -> str:
        """Get the display name for this server."""
        return self.name or "Cloud Server"


class StorageSettings(BaseModel):
    """Storage backend configuration."""

    backend: str = Field(default="sqlite", pattern="^(sqlite|cloud)$")
    last_file: Optional[Path] = None
    last_opened_at: Optional[str] = None  # ISO format datetime string
    always_show_file_chooser: bool = False  # Always show file chooser on startup

    # Cloud server configurations (multiple servers can be saved)
    cloud_servers: list[CloudServerConfig] = Field(default_factory=list)
    active_server_id: Optional[str] = None  # ID of currently active cloud server

    model_config = {"validate_assignment": True}

    def get_active_server(self) -> Optional[CloudServerConfig]:
        """Get the currently active cloud server configuration."""
        if not self.active_server_id:
            return None
        for server in self.cloud_servers:
            if server.id == self.active_server_id:
                return server
        return None

    def add_server(self, server: CloudServerConfig) -> None:
        """Add a new server configuration."""
        # Remove existing server with same ID if present
        self.cloud_servers = [s for s in self.cloud_servers if s.id != server.id]
        self.cloud_servers.append(server)

    def remove_server(self, server_id: str) -> None:
        """Remove a server configuration."""
        self.cloud_servers = [s for s in self.cloud_servers if s.id != server_id]
        if self.active_server_id == server_id:
            self.active_server_id = None


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


class SyncSettings(BaseModel):
    """Settings for cloud synchronization.

    Controls how data is synced between local cache and cloud server,
    including conflict resolution and retry behavior.
    """

    conflict_strategy: str = Field(
        default="last_write_wins",
        pattern="^(last_write_wins|server_wins|client_wins|ask_user)$"
    )
    health_check_interval_seconds: int = Field(default=30, ge=5, le=300)
    sync_interval_seconds: int = Field(default=30, ge=1, le=300)
    max_retry_count: int = Field(default=3, ge=1, le=10)
    retry_initial_delay_seconds: float = Field(default=1.0, ge=0.5, le=10.0)
    retry_max_delay_seconds: float = Field(default=10.0, ge=1.0, le=60.0)

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
    sync: SyncSettings = Field(default_factory=SyncSettings)

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
