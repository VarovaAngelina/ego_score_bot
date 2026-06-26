"""SnapshotService unit tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.config import Settings
from bot.database.models import PlayerStats
from bot.services.snapshot_service import SnapshotService


@pytest.fixture
def settings() -> Settings:
    return Settings(
        discord_token="x",
        discord_guild_id=1,
        db_password="secret",
        announce_channel_id=0,
        top_limit=10,
    )


@pytest.fixture
def service(settings: Settings) -> SnapshotService:
    return SnapshotService(db=AsyncMock(), settings=settings)


@pytest.mark.asyncio
async def test_take_snapshot_skips_without_users(service: SnapshotService) -> None:
    with patch("bot.services.snapshot_service.user_queries.count_all", AsyncMock(return_value=0)):
        bot = MagicMock()
        result = await service.take_snapshot(bot)

    assert result is False
    bot.get_channel.assert_not_called()


@pytest.mark.asyncio
async def test_take_snapshot_skips_without_scored_players(service: SnapshotService) -> None:
    with (
        patch("bot.services.snapshot_service.user_queries.count_all", AsyncMock(return_value=3)),
        patch("bot.services.snapshot_service.cache_queries.list_scored_for_week", AsyncMock(return_value=[])),
    ):
        bot = MagicMock()
        result = await service.take_snapshot(bot)

    assert result is False


@pytest.mark.asyncio
async def test_take_snapshot_saves_and_marks_stale(service: SnapshotService) -> None:
    scored = [
        (
            1,
            "TenZ#NA1",
            "Radiant",
            78.5,
            PlayerStats(250, 1.5, 30, 24, 70),
        ),
        (
            2,
            "s1mple#EU1",
            "Immortal 3",
            74.2,
            PlayerStats(220, 1.3, 20, 22, 68),
        ),
    ]
    save_week = AsyncMock()
    mark_stale = AsyncMock()
    announce = AsyncMock()

    with (
        patch("bot.services.snapshot_service.current_week_start", return_value=date(2026, 6, 22)),
        patch("bot.services.snapshot_service.current_week_end", return_value=date(2026, 6, 28)),
        patch("bot.services.snapshot_service.user_queries.count_all", AsyncMock(return_value=2)),
        patch("bot.services.snapshot_service.cache_queries.list_scored_for_week", AsyncMock(return_value=scored)),
        patch("bot.services.snapshot_service.snapshot_queries.save_week", save_week),
        patch("bot.services.snapshot_service.cache_queries.mark_week_stale", mark_stale),
        patch.object(service, "announce", announce),
    ):
        bot = MagicMock()
        result = await service.take_snapshot(bot)

    assert result is True
    save_week.assert_awaited_once()
    saved_rows = save_week.await_args.args[3]
    assert len(saved_rows) == 2
    assert saved_rows[0].rank == 1
    assert saved_rows[0].riot_id == "TenZ#NA1"
    mark_stale.assert_awaited_once()
    announce.assert_awaited_once()


@pytest.mark.asyncio
async def test_announce_skipped_when_disabled(service: SnapshotService) -> None:
    channel = AsyncMock()
    bot = MagicMock()
    bot.get_channel.return_value = channel

    await service.announce(
        bot,
        week_label="22–28 июня 2026",
        leaderboard=[],
        registered_count=0,
    )

    channel.send.assert_not_called()
