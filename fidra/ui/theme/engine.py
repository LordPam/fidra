"""Theme engine for loading and applying QSS stylesheets."""

from pathlib import Path
from typing import Optional
from enum import Enum

from PySide6.QtWidgets import QApplication


class Theme(Enum):
    """Available themes."""
    LIGHT = "light"
    DARK = "dark"


class ThemeEngine:
    """Engine for loading and applying themes.

    Usage:
        engine = ThemeEngine()
        engine.apply_theme(Theme.LIGHT)
    """

    def __init__(self):
        """Initialize theme engine."""
        self._current_theme: Optional[Theme] = None
        self._theme_dir = Path(__file__).parent

    @property
    def current_theme(self) -> Optional[Theme]:
        """Get currently applied theme."""
        return self._current_theme

    def apply_theme(self, theme: Theme) -> None:
        """Apply a theme to the application.

        Args:
            theme: Theme to apply
        """
        qss_path = self._theme_dir / f"{theme.value}.qss"

        if not qss_path.exists():
            raise FileNotFoundError(f"Theme file not found: {qss_path}")

        stylesheet = qss_path.read_text(encoding='utf-8')

        # Replace relative icon paths with absolute paths
        icons_dir = self._theme_dir / "icons"
        stylesheet = stylesheet.replace(
            'url("icons/',
            f'url("{icons_dir.as_posix()}/'
        )

        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
            self._current_theme = theme

    def get_available_themes(self) -> list[Theme]:
        """Get list of available themes.

        Returns:
            List of Theme enum values for available themes
        """
        available = []
        for theme in Theme:
            qss_path = self._theme_dir / f"{theme.value}.qss"
            if qss_path.exists():
                available.append(theme)
        return available

    def get_color(self, name: str) -> str:
        """Get a color value from the current theme.

        This is useful for pyqtgraph and other components that
        need programmatic color access.

        Args:
            name: Color name (e.g., 'accent', 'success', 'danger')

        Returns:
            Hex color string
        """
        # Color definitions for programmatic access
        # Brand colors: #23395B (dark blue), #BFA159 (gold), #0D1F2F (navy)
        colors = {
            Theme.LIGHT: {
                'bg_primary': '#ffffff',
                'bg_secondary': '#f9fafb',
                'bg_tertiary': '#f3f4f6',
                'text_primary': '#111827',
                'text_secondary': '#6b7280',
                'text_tertiary': '#9ca3af',
                'border': '#e2e8f0',
                'accent': '#23395B',
                'accent_light': '#eff6ff',
                'success': '#10b981',
                'success_light': '#ecfdf5',
                'danger': '#ef4444',
                'danger_light': '#fef2f2',
                'warning': '#f59e0b',
                'warning_light': '#fffbeb',
                # Chart colors using brand palette
                'chart_income': '#BFA159',      # Gold for income
                'chart_expense': '#23395B',     # Dark blue for expenses
                'chart_accent': '#23395B',      # Primary brand color
                'chart_secondary': '#BFA159',   # Secondary brand color
            },
            Theme.DARK: {
                'bg_primary': '#1a1a1a',        # Main background (dark gray)
                'bg_secondary': '#242424',      # Card/panel background (slightly lighter)
                'bg_tertiary': '#2a2a2a',       # Elevated surfaces
                'text_primary': '#e2e8f0',
                'text_secondary': '#888888',
                'text_tertiary': '#666666',
                'border': '#333333',
                'accent': '#4a6fa5',            # Blue accent
                'accent_light': '#3a5f95',
                'success': '#10b981',
                'success_light': '#064e3b',
                'danger': '#ef4444',
                'danger_light': '#7f1d1d',
                'warning': '#f59e0b',
                'warning_light': '#78350f',
                # Chart colors - keep dark-mode blue, but use brand gold consistently
                'chart_income': '#BFA159',      # Gold for income
                'chart_expense': '#4a6fa5',     # Blue for expenses
                'chart_accent': '#4a6fa5',      # Blue accent
                'chart_secondary': '#BFA159',   # Gold for secondary
            },
        }

        theme = self._current_theme or Theme.LIGHT
        return colors.get(theme, colors[Theme.LIGHT]).get(name, '#000000')


# Global instance
_theme_engine: Optional[ThemeEngine] = None


def get_theme_engine() -> ThemeEngine:
    """Get the global theme engine instance.

    Returns:
        ThemeEngine singleton
    """
    global _theme_engine
    if _theme_engine is None:
        _theme_engine = ThemeEngine()
    return _theme_engine
