"""Progress bar unit tests."""

import pytest

from bot.utils.progress_bar import format_contrib_percent, render_progress_bar


def test_render_progress_bar_empty() -> None:
    assert render_progress_bar(0, 30) == "░░░░░░░░░░"


def test_render_progress_bar_full() -> None:
    assert render_progress_bar(30, 30) == "██████████"


def test_render_progress_bar_half() -> None:
    assert render_progress_bar(15, 30) == "█████░░░░░"


def test_render_progress_bar_clamps_above_max() -> None:
    assert render_progress_bar(50, 30) == "██████████"


def test_format_contrib_positive() -> None:
    assert format_contrib_percent(28.5) == "+28.5%"


def test_format_contrib_negative() -> None:
    assert format_contrib_percent(-8.4) == "−8.4%"
