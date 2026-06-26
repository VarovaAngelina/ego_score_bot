"""Integration tests for database queries (requires MySQL on localhost:3307)."""

from __future__ import annotations

import os
from datetime import datetime

import pytest
import pytest_asyncio

from bot.config import Settings
from bot.database.connection import DatabasePool
from bot.database.models import PlayerStats, ScoreResult
from bot.database.queries import bounds_queries, cache_queries, snapshot_queries, user_queries
from bot.utils.time_utils import current_week_end, current_week_start, msk_now

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db() -> DatabasePool:
    if not os.getenv("RUN_DB_TESTS"):
        pytest.skip("Set RUN_DB_TESTS=1 to run database integration tests")

    settings = Settings()
    pool = await DatabasePool.create(settings)
    await pool.execute("DELETE FROM weekly_snapshots WHERE user_id IN (SELECT id FROM users WHERE discord_id >= 999000)")
    await pool.execute("DELETE FROM player_cache WHERE user_id IN (SELECT id FROM users WHERE discord_id >= 999000)")
    await pool.execute("DELETE FROM users WHERE discord_id >= 999000")
    await bounds_queries.ensure_seed(pool)
    yield pool
    await pool.close()


async def test_user_register_flow(db: DatabasePool) -> None:
    user = await user_queries.register(db, 999001, "Test#EU1")
    assert user.riot_id == "Test#EU1"

    found = await user_queries.get_by_discord_id(db, 999001)
    assert found is not None
    assert found.id == user.id

    user = await user_queries.register(db, 999001, "Test#EU2")
    assert user.riot_id == "Test#EU2"
    found = await user_queries.get_by_discord_id(db, 999001)
    assert found is not None
    assert found.riot_id == "Test#EU2"

    assert await user_queries.unregister(db, 999001) is True
    assert await user_queries.get_by_discord_id(db, 999001) is None


async def test_cache_upsert_and_top(db: DatabasePool) -> None:
    user = await user_queries.register(db, 999002, "Top#EU1")
    week = current_week_start()
    stats = PlayerStats(250, 1.5, 30, 24, 70)
    result = ScoreResult(75.0, 28.0, 21.0, 16.0, 11.0, -8.0)

    await cache_queries.upsert(
        db,
        user_id=user.id,
        week_start=week,
        stats=stats,
        result=result,
        current_rank="Diamond 2",
        rank_delta=1,
        fetched_at=msk_now(),
    )

    cached = await cache_queries.get_by_user_week(db, user.id, week)
    assert cached is not None
    assert cached.ego_score == 75.0
    assert cached.current_rank == "Diamond 2"

    top = await cache_queries.get_top_for_week(db, week, limit=10)
    assert len(top) == 1
    assert top[0].riot_id == "Top#EU1"


async def test_snapshot_save_and_list(db: DatabasePool) -> None:
    from bot.database.models import WeeklySnapshotRow

    user = await user_queries.register(db, 999003, "Snap#EU1")
    week_start = current_week_start()
    week_end = current_week_end(week_start)
    row = WeeklySnapshotRow(
        week_start=week_start,
        week_end=week_end,
        rank=1,
        user_id=user.id,
        riot_id=user.riot_id,
        current_rank="Platinum 1",
        ego_score=60.0,
        stats=PlayerStats(180, 1.1, 10, 20, 65),
    )
    await snapshot_queries.save_week(db, week_start, week_end, [row])

    weeks = await snapshot_queries.list_weeks(db)
    assert len(weeks) == 1
    assert weeks[0].player_count == 1

    page = await snapshot_queries.get_page(db, week_start, offset=0, limit=20)
    assert page[0].riot_id == "Snap#EU1"


async def test_bounds_seed(db: DatabasePool) -> None:
    bounds = await bounds_queries.get_all(db)
    assert "acs" in bounds
    assert bounds["acs"].max_val == 350
