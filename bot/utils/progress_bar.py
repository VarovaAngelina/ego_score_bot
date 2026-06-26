"""Progress bar generator (█████░░░)."""

from __future__ import annotations

STAT_MAX_CONTRIB: dict[str, float] = {
    "acs": 30.0,
    "kd": 25.0,
    "dd": 20.0,
    "hs": 15.0,
    "kast": 10.0,
}

DEFAULT_BAR_WIDTH = 10


def render_progress_bar(value: float, max_value: float, width: int = DEFAULT_BAR_WIDTH) -> str:
    """Fill proportionally; value and max_value should be non-negative."""
    if width < 1:
        return ""
    if max_value <= 0:
        return "░" * width
    ratio = min(max(value / max_value, 0.0), 1.0)
    filled = round(ratio * width)
    filled = min(filled, width)
    return "█" * filled + "░" * (width - filled)


def format_contrib_percent(value: float) -> str:
    if value >= 0:
        return f"+{value:.1f}%"
    return f"−{abs(value):.1f}%"
