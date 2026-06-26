"""CacheService unit tests."""



from __future__ import annotations



from datetime import datetime, timedelta

from unittest.mock import AsyncMock, patch



import pytest



from bot.config import MSK, Settings

from bot.database.models import PlayerCache, PlayerStats, ScoreResult, User

from bot.services.cache_service import CacheService, PlayerCacheView

from bot.services.score_service import ScoreService

from bot.services.stats_types import StatsResult, StatsUnavailableError





@pytest.fixture

def settings() -> Settings:

    return Settings(

        discord_token="x",

        discord_guild_id=1,

        db_password="secret",

        cache_ttl_minutes=30,

    )





@pytest.fixture

def user() -> User:

    return User(id=1, discord_id=100, riot_id="Test#EU1", registered_at=datetime.now(tz=MSK))





@pytest.fixture

def stats_result() -> StatsResult:

    return StatsResult(

        riot_id="Test#EU1",

        stats=PlayerStats(250, 1.5, 30, 24, 70),

        current_rank="Diamond 2",

        matches_played=2,

    )





def _make_cache(fetched_at: datetime, is_stale: bool = False):

    from bot.database.models import PlayerCache



    result = ScoreResult(75.0, 28.0, 21.0, 16.0, 11.0, -8.0)

    stats = PlayerStats(250, 1.5, 30, 24, 70)

    return PlayerCache(

        id=1,

        user_id=1,

        week_start=fetched_at.date(),

        stats=stats,

        ego_score=75.0,

        current_rank="Diamond 2",

        rank_delta=0,

        result=result,

        fetched_at=fetched_at,

        matches_played=2,

        is_stale=is_stale,

    )





@pytest.mark.asyncio

async def test_returns_fresh_cache_without_stats_fetch(settings, user) -> None:

    db = AsyncMock()

    stats = AsyncMock()

    service = CacheService(db, ScoreService(), stats, settings)

    fresh = _make_cache(datetime.now(tz=MSK) - timedelta(minutes=5))



    with patch("bot.services.cache_service.cache_queries.get_by_user_week", return_value=fresh):

        view = await service.get_or_refresh(user)



    assert view.served_from_cache is True

    stats.fetch_stats.assert_not_called()





@pytest.mark.asyncio

async def test_refreshes_when_cache_expired(settings, user, stats_result) -> None:

    db = AsyncMock()

    stats = AsyncMock()

    stats.fetch_stats.return_value = stats_result

    service = CacheService(db, ScoreService(), stats, settings)

    stale = _make_cache(datetime.now(tz=MSK) - timedelta(minutes=60))

    updated = _make_cache(datetime.now(tz=MSK))



    with patch("bot.services.cache_service.cache_queries.get_by_user_week", side_effect=[stale, updated]):

        with patch("bot.services.cache_service.bounds_queries.get_all", return_value={}):

            with patch("bot.services.cache_service.bounds_queries.upsert", new=AsyncMock()):

                with patch("bot.services.cache_service.cache_queries.upsert", new=AsyncMock()):

                    view = await service.get_or_refresh(user)



    assert view.served_from_cache is False

    stats.fetch_stats.assert_awaited_once()





@pytest.mark.asyncio

async def test_stats_unavailable_returns_stale_cache(settings, user) -> None:

    db = AsyncMock()

    stats = AsyncMock()

    stats.fetch_stats.side_effect = StatsUnavailableError("429")

    service = CacheService(db, ScoreService(), stats, settings)

    stale = _make_cache(datetime.now(tz=MSK) - timedelta(hours=2))



    with patch("bot.services.cache_service.cache_queries.get_by_user_week", return_value=stale):

        view = await service.get_or_refresh(user, force=True)



    assert view.stats_unavailable is True

    assert view.served_from_cache is True


@pytest.mark.asyncio
async def test_empty_week_is_cached_and_reused(settings, user) -> None:
    db = AsyncMock()
    stats = AsyncMock()
    empty_result = StatsResult(
        riot_id=user.riot_id,
        stats=PlayerStats(0.0, 0.0, 0.0, 0.0, 0.0),
        current_rank="Unranked",
        matches_played=0,
    )
    stats.fetch_stats.return_value = empty_result
    service = CacheService(db, ScoreService(), stats, settings)

    cached_empty = _make_cache(datetime.now(tz=MSK), is_stale=False)
    cached_empty = PlayerCache(
        id=cached_empty.id,
        user_id=cached_empty.user_id,
        week_start=cached_empty.week_start,
        stats=PlayerStats(0.0, 0.0, 0.0, 0.0, 0.0),
        ego_score=0.0,
        current_rank="Unranked",
        rank_delta=0,
        result=ScoreResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        fetched_at=datetime.now(tz=MSK),
        matches_played=0,
        is_stale=False,
    )

    with patch(
        "bot.services.cache_service.cache_queries.get_by_user_week",
        side_effect=[None, cached_empty, cached_empty],
    ):
        with patch("bot.services.cache_service.bounds_queries.get_all", return_value={}):
            with patch("bot.services.cache_service.cache_queries.upsert", new=AsyncMock()):
                first = await service.get_or_refresh(user)
                second = await service.get_or_refresh(user)

    assert first.cache.matches_played == 0
    assert second.served_from_cache is True
    stats.fetch_stats.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_keeps_scored_cache_when_api_returns_empty(settings, user) -> None:
    db = AsyncMock()
    stats = AsyncMock()
    empty_result = StatsResult(
        riot_id=user.riot_id,
        stats=PlayerStats(0.0, 0.0, 0.0, 0.0, 0.0),
        current_rank="Gold 1",
        matches_played=0,
    )
    stats.fetch_stats.return_value = empty_result
    service = CacheService(db, ScoreService(), stats, settings)

    previous = _make_cache(datetime.now(tz=MSK))
    previous = PlayerCache(
        id=previous.id,
        user_id=previous.user_id,
        week_start=previous.week_start,
        stats=PlayerStats(250, 1.5, 30, 24, 70),
        ego_score=75.0,
        current_rank="Gold 1",
        rank_delta=0,
        result=ScoreResult(75.0, 28.0, 21.0, 16.0, 11.0, -8.0),
        fetched_at=datetime.now(tz=MSK) - timedelta(hours=1),
        matches_played=4,
        is_stale=False,
    )

    with patch(
        "bot.services.cache_service.cache_queries.get_by_user_week",
        side_effect=[previous, previous],
    ):
        view = await service._refresh_user(user, previous.week_start, previous)

    assert view.served_from_cache is True
    assert view.cache.ego_score == 75.0
    stats.fetch_stats.assert_awaited_once()

