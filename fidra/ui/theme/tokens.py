"""Semantic design tokens for theming.

This module defines all semantic tokens used across the application.
Components reference tokens (e.g., canvas, text.primary) and never hardcode colors.

Palette (only):
    - #23395B Navy
    - #0D1F2F Deep Navy
    - #BFA159 Gold
    - #D3D3D3 Light Gray
    - #A9A9A9 Mid Gray
"""

from dataclasses import dataclass
from typing import Dict


# Raw palette - the only colors allowed
NAVY = "#23395B"
DEEP_NAVY = "#0D1F2F"
GOLD = "#BFA159"
LIGHT_GRAY = "#D3D3D3"
MID_GRAY = "#A9A9A9"


@dataclass(frozen=True)
class SemanticTokens:
    """Semantic token definitions for a theme."""

    # Core surfaces
    canvas: str              # App background
    surface: str             # Cards, raised panels
    surface_alt: str         # Secondary panels, drawers
    sidebar: str             # Sidebar background
    header: str              # Header background

    # Text
    text_primary: str        # Primary text
    text_secondary: str      # Secondary text
    text_muted: str          # Muted/helper text
    text_on_primary: str     # Text on filled primary buttons

    # Lines / structure
    border: str              # Borders
    divider: str             # Dividers
    gridline: str            # Chart gridlines

    # Accent and focus
    accent: str              # Gold signal
    focus_ring: str          # Focus ring
    link: str                # Link color

    # States (no red/green - use gold and labels)
    positive: str            # Surplus / good
    negative: str            # Deficit / caution
    warning: str             # Needs action

    # Component-specific
    button_primary_bg: str   # Primary button background
    button_primary_text: str # Primary button text
    input_bg: str            # Input background
    table_row_alt: str       # Alternating table row
    table_row_hover: str     # Table row hover

    # Chart-specific
    chart_bar_primary: str   # Primary bar color
    chart_bar_secondary: str # Secondary bar color
    chart_line: str          # Line color (net)
    chart_axis: str          # Axis text


# Light theme tokens
LIGHT_TOKENS = SemanticTokens(
    # Core surfaces
    canvas=LIGHT_GRAY,
    surface=LIGHT_GRAY,          # Same as canvas, differentiated via border + shadow
    surface_alt=LIGHT_GRAY,
    sidebar=NAVY,
    header=LIGHT_GRAY,

    # Text
    text_primary=DEEP_NAVY,
    text_secondary=NAVY,
    text_muted=MID_GRAY,
    text_on_primary=LIGHT_GRAY,

    # Lines / structure
    border=MID_GRAY,
    divider=MID_GRAY,
    gridline=MID_GRAY,

    # Accent and focus
    accent=GOLD,
    focus_ring=GOLD,
    link=NAVY,

    # States
    positive=GOLD,
    negative=DEEP_NAVY,          # With strong "−" sign + label
    warning=GOLD,

    # Component-specific
    button_primary_bg=NAVY,
    button_primary_text=LIGHT_GRAY,
    input_bg="#FFFFFF",          # White for inputs in light mode
    table_row_alt="#C8C8C8",     # Slightly darker than canvas
    table_row_hover="#BEBEBE",   # Even darker on hover

    # Chart-specific
    chart_bar_primary=NAVY,
    chart_bar_secondary=DEEP_NAVY,
    chart_line=GOLD,
    chart_axis=DEEP_NAVY,
)


# Dark theme tokens
DARK_TOKENS = SemanticTokens(
    # Core surfaces
    canvas=DEEP_NAVY,
    surface=NAVY,                # Raised above canvas
    surface_alt=DEEP_NAVY,       # Same as canvas; differentiate by border + spacing
    sidebar=DEEP_NAVY,           # Deeper
    header=DEEP_NAVY,

    # Text
    text_primary=LIGHT_GRAY,
    text_secondary=MID_GRAY,
    text_muted=MID_GRAY,
    text_on_primary=LIGHT_GRAY,

    # Lines / structure
    border=NAVY,
    divider=NAVY,
    gridline=NAVY,

    # Accent and focus
    accent=GOLD,
    focus_ring=GOLD,
    link=LIGHT_GRAY,             # Links should be readable; accent gold only on hover

    # States
    positive=GOLD,
    negative=LIGHT_GRAY,         # With strong "−" sign + label
    warning=GOLD,

    # Component-specific
    button_primary_bg=NAVY,
    button_primary_text=LIGHT_GRAY,
    input_bg=NAVY,               # Navy for inputs in dark mode
    table_row_alt="#1A2A40",     # Slightly lighter than canvas
    table_row_hover="#2A3A50",   # Even lighter on hover

    # Chart-specific
    chart_bar_primary=LIGHT_GRAY,
    chart_bar_secondary=MID_GRAY,
    chart_line=GOLD,
    chart_axis=LIGHT_GRAY,
)


def get_tokens(theme: str) -> SemanticTokens:
    """Get tokens for a theme.

    Args:
        theme: 'light' or 'dark'

    Returns:
        SemanticTokens for the theme
    """
    if theme == "dark":
        return DARK_TOKENS
    return LIGHT_TOKENS


def tokens_to_dict(tokens: SemanticTokens) -> Dict[str, str]:
    """Convert tokens to a dictionary for QSS substitution.

    Args:
        tokens: SemanticTokens instance

    Returns:
        Dictionary mapping token names to values
    """
    return {
        "canvas": tokens.canvas,
        "surface": tokens.surface,
        "surface_alt": tokens.surface_alt,
        "sidebar": tokens.sidebar,
        "header": tokens.header,
        "text_primary": tokens.text_primary,
        "text_secondary": tokens.text_secondary,
        "text_muted": tokens.text_muted,
        "text_on_primary": tokens.text_on_primary,
        "border": tokens.border,
        "divider": tokens.divider,
        "gridline": tokens.gridline,
        "accent": tokens.accent,
        "focus_ring": tokens.focus_ring,
        "link": tokens.link,
        "positive": tokens.positive,
        "negative": tokens.negative,
        "warning": tokens.warning,
        "button_primary_bg": tokens.button_primary_bg,
        "button_primary_text": tokens.button_primary_text,
        "input_bg": tokens.input_bg,
        "table_row_alt": tokens.table_row_alt,
        "table_row_hover": tokens.table_row_hover,
        "chart_bar_primary": tokens.chart_bar_primary,
        "chart_bar_secondary": tokens.chart_bar_secondary,
        "chart_line": tokens.chart_line,
        "chart_axis": tokens.chart_axis,
    }
