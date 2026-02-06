"""Unit tests for AppSettings."""

import pytest
from pydantic import ValidationError
from fidra.domain.settings import AppSettings, ThemeSettings, ForecastSettings


class TestAppSettings:
    """Tests for AppSettings model."""

    def test_default_settings(self):
        """Default settings are created correctly."""
        settings = AppSettings()

        assert settings.theme.mode == "dark"
        assert settings.storage.backend == "sqlite"
        assert settings.forecast.horizon_days == 180
        assert settings.forecast.include_past_planned is True
        assert len(settings.income_categories) == 5
        assert len(settings.expense_categories) == 6

    def test_valid_theme_modes(self):
        """Theme mode accepts valid values."""
        settings = AppSettings()

        settings.theme.mode = "dark"
        assert settings.theme.mode == "dark"

        settings.theme.mode = "light"
        assert settings.theme.mode == "light"

        settings.theme.mode = "system"
        assert settings.theme.mode == "system"

    def test_invalid_theme_mode_raises_error(self):
        """Invalid theme mode raises validation error."""
        settings = AppSettings()

        with pytest.raises(ValidationError):
            settings.theme.mode = "invalid"

    def test_valid_storage_backends(self):
        """Storage backend accepts valid values."""
        settings = AppSettings()

        settings.storage.backend = "sqlite"
        assert settings.storage.backend == "sqlite"

        settings.storage.backend = "excel"
        assert settings.storage.backend == "excel"

    def test_invalid_storage_backend_raises_error(self):
        """Invalid storage backend raises validation error."""
        settings = AppSettings()

        with pytest.raises(ValidationError):
            settings.storage.backend = "invalid"

    def test_forecast_horizon_validation(self):
        """Forecast horizon must be between 7 and 730 days."""
        settings = AppSettings()

        settings.forecast.horizon_days = 7  # Min valid
        assert settings.forecast.horizon_days == 7

        settings.forecast.horizon_days = 730  # Max valid
        assert settings.forecast.horizon_days == 730

        with pytest.raises(ValidationError):
            settings.forecast.horizon_days = 6  # Too low

        with pytest.raises(ValidationError):
            settings.forecast.horizon_days = 1000  # Too high

    def test_custom_categories(self):
        """Custom income and expense categories can be set."""
        settings = AppSettings()

        settings.income_categories = ["Salary", "Bonus", "Other"]
        assert len(settings.income_categories) == 3

        settings.expense_categories = ["Food", "Rent"]
        assert len(settings.expense_categories) == 2

    def test_profile_initials_max_length(self):
        """Profile initials limited to 3 characters."""
        settings = AppSettings()

        settings.profile.initials = "ABC"  # Valid: 3 chars
        assert settings.profile.initials == "ABC"

        with pytest.raises(ValidationError):
            settings.profile.initials = "ABCD"  # Invalid: 4 chars

    def test_json_serialization(self):
        """Settings can be serialized to JSON."""
        settings = AppSettings()
        settings.profile.name = "John Doe"
        settings.theme.mode = "light"

        json_str = settings.model_dump_json()
        assert "John Doe" in json_str
        assert "light" in json_str

    def test_json_deserialization(self):
        """Settings can be loaded from JSON."""
        json_data = {
            "profile": {"name": "Jane Smith", "initials": "JS"},
            "theme": {"mode": "dark"},
            "storage": {"backend": "sqlite", "last_file": None},
            "logging": {"level": "DEBUG"},
            "forecast": {"horizon_days": 60, "include_past_planned": False},
            "income_categories": ["Salary"],
            "expense_categories": ["Food"],
            "example_descriptions": [],
            "example_parties": [],
        }

        settings = AppSettings.model_validate(json_data)

        assert settings.profile.name == "Jane Smith"
        assert settings.profile.initials == "JS"
        assert settings.logging.level == "DEBUG"
        assert settings.forecast.horizon_days == 60

    def test_extra_fields_forbidden(self):
        """Extra fields are not allowed."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            AppSettings.model_validate(
                {"profile": {}, "theme": {}, "storage": {}, "logging": {}, "forecast": {}, "income_categories": [], "expense_categories": [], "example_descriptions": [], "example_parties": [], "extra_field": "not allowed"}
            )
