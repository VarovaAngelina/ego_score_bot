"""Stats utils and StatsService unit tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bot.services.stats_service import StatsService
from bot.database.models import PlayerStats
from bot.services.stats_types import PlayerNotFoundError, StatsError, StatsResult, StatsUnavailableError
from bot.services.stats_utils import (
    aggregate_match_stats,
    current_week_bounds,
    filter_matches_by_week,
    parse_riot_id,
    stat_value,
)
from tests.fixtures.match_samples import SAMPLE_MATCHES


def test_parse_riot_id() -> None:
    assert parse_riot_id("TenZ#NA1") == ("TenZ", "NA1")
    with pytest.raises(StatsError):
        parse_riot_id("invalid")


def test_stat_value_nested() -> None:
    stats = {"scorePerRound": {"value": 240.5, "displayValue": "240.5"}}
    assert stat_value(stats, "scorePerRound") == 240.5


def test_aggregate_match_stats() -> None:
    stats = aggregate_match_stats(SAMPLE_MATCHES)
    assert stats.acs == pytest.approx(230.0, rel=1e-2)
    assert stats.kd_ratio > 0
    assert stats.kast_percent > 0


def test_filter_matches_by_week() -> None:
    week_start, week_end = current_week_bounds()
    weekly = filter_matches_by_week(SAMPLE_MATCHES, week_start, week_end)
    assert len(weekly) == 2


@pytest.mark.asyncio
async def test_fetch_stats_via_henrik() -> None:
    service = StatsService(api_key="HDEV-test")
    expected = StatsResult(
        riot_id="Player#EU1",
        stats=aggregate_match_stats(SAMPLE_MATCHES),
        current_rank="Diamond 2",
        matches_played=2,
    )

    with patch("bot.services.stats_service.fetch_stats_via_henrik", return_value=expected):
        async with service:
            result = await service.fetch_stats("Player#EU1")
            assert result.current_rank == "Diamond 2"
            assert result.matches_played == 2


@pytest.mark.asyncio
async def test_player_not_found() -> None:
    service = StatsService(api_key="HDEV-test")

    with patch(
        "bot.services.stats_service.fetch_stats_via_henrik",
        side_effect=PlayerNotFoundError("Player not found: Missing#0000"),
    ):
        async with service:
            with pytest.raises(PlayerNotFoundError):
                await service.fetch_stats("Missing#0000")


@pytest.mark.asyncio
async def test_unavailable_on_api_error() -> None:
    service = StatsService(api_key="HDEV-test")

    with patch(
        "bot.services.stats_service.fetch_stats_via_henrik",
        side_effect=StatsUnavailableError("Henrik API rate limit (429)"),
    ):
        async with service:
            with pytest.raises(StatsUnavailableError):
                await service.fetch_stats("Player#EU1")


@pytest.mark.asyncio
async def test_no_matches_for_current_week() -> None:
    service = StatsService(api_key="HDEV-test")
    expected = StatsResult(
        riot_id="Player#EU1",
        stats=PlayerStats(0.0, 0.0, 0.0, 0.0, 0.0),
        current_rank=None,
        matches_played=0,
    )

    with patch(
        "bot.services.stats_service.fetch_stats_via_henrik",
        return_value=expected,
    ):
        async with service:
            result = await service.fetch_stats("Player#EU1")
            assert result.matches_played == 0


def test_stats_service_requires_api_key() -> None:
    with pytest.raises(ValueError, match="HENRIK_API_KEY"):
        StatsService(api_key="")
