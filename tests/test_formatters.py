"""Formatter unit tests."""

from datetime import date, datetime

import pytest

from bot.config import MSK
from bot.database.models import PlayerCache, PlayerStats, ScoreResult, User, LeaderboardEntry
from bot.services.cache_service import PlayerCacheView
from bot.utils.formatters import (
    build_ego_embed,
    build_stat_contrib_lines,
    format_ego_score_block,
    format_leaderboard_line,
    format_match_count,
    format_msk_date,
    format_rank_delta,
    format_week_range,
)
from bot.utils.time_utils import current_week_end, current_week_start


@pytest.fixture
def sample_view() -> PlayerCacheView:
    user = User(
        id=1,
        discord_id=100,
        riot_id="TenZ#NA1",
        registered_at=datetime(2026, 6, 10, 12, 0, tzinfo=MSK),
    )
    stats = PlayerStats(
        acs=302.4,
        kd_ratio=1.87,
        damage_delta=45.2,
        hs_percent=24.1,
        kast_percent=72.3,
    )
    result = ScoreResult(
        ego_score=78.5,
        contrib_acs=28.5,
        contrib_kd=21.3,
        contrib_dd=16.8,
        contrib_hs=11.9,
        contrib_kast=-8.4,
    )
    cache = PlayerCache(
        id=1,
        user_id=1,
        week_start=date(2026, 6, 16),
        stats=stats,
        ego_score=78.5,
        current_rank="Radiant",
        rank_delta=0,
        result=result,
        fetched_at=datetime(2026, 6, 24, 14, 32, tzinfo=MSK),
        matches_played=6,
        is_stale=False,
    )
    return PlayerCacheView(user=user, cache=cache, served_from_cache=True)


def test_format_match_count_one() -> None:
    assert format_match_count(1) == "1 матч"


def test_format_match_count_few() -> None:
    assert format_match_count(3) == "3 матча"


def test_format_match_count_many() -> None:
    assert format_match_count(6) == "6 матчей"


def test_format_week_range_same_month() -> None:
    assert format_week_range(date(2026, 6, 16), date(2026, 6, 22)) == "16–22 июня 2026"


def test_format_msk_date() -> None:
    assert format_msk_date(date(2026, 6, 10)) == "10 июня 2026"


def test_format_ego_score_block() -> None:
    block = format_ego_score_block(78.5)
    assert "# **78.5**" in block
    assert "-# / 100" in block


def test_build_stat_contrib_lines_contains_stats(sample_view: PlayerCacheView) -> None:
    text = build_stat_contrib_lines(sample_view)
    assert "ACS (302.4)" in text
    assert "K/D (1.87)" in text
    assert "+28.5%" in text
    assert "−8.4%" in text
    assert "█" in text


def test_build_ego_embed_score_and_footer(sample_view: PlayerCacheView) -> None:
    week_label = format_week_range(current_week_start(), current_week_end())
    embed = build_ego_embed(
        sample_view,
        week_label=week_label,
        week_rank=3,
        scored_count=15,
    )

    assert embed.title == "🎯 Ego Score — TenZ#NA1"
    assert "**Матчи:** 6 матчей" in embed.description
    assert "**Место в топе:** #3 из 15" in embed.description
    assert "# **78.5**" in embed.description
    assert "-# / 100" in embed.description
    assert embed.fields[0].name == "Вклад статистик"
    assert "ACS (302.4)" in embed.fields[0].value
    assert embed.footer is not None
    assert "14:32" in embed.footer.text


def test_leaderboard_line_helpers() -> None:
    assert format_rank_delta(1) == "  ↑"
    line = format_leaderboard_line(
        LeaderboardEntry(
            rank=2,
            user_id=1,
            riot_id="s1mple#EU1",
            current_rank="Immortal 3",
            ego_score=74.2,
            rank_delta=0,
        )
    )
    assert "#2  " in line
    assert "74.2" in line
