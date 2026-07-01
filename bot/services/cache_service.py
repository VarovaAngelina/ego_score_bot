"""player_cache read/write, refresh orchestration."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime

from bot.config import MSK, Settings
from bot.database.connection import DatabasePool
from bot.database.models import PlayerCache, PlayerStats, User
from bot.database.queries import bounds_queries, cache_queries, user_queries
from bot.services.score_service import ScoreService
from bot.services.stats_service import StatsService
from bot.services.stats_types import (
    PlayerNotFoundError,
    StatsError,
    StatsNotReadyError,
    StatsUnavailableError,
)
from bot.utils.time_utils import current_week_start, msk_now

logger = logging.getLogger("ego_score_bot.cache")

BACKGROUND_LOADING_NOTE = "__background__"


@dataclass(slots=True)
class PlayerCacheView:
    user: User
    cache: PlayerCache
    served_from_cache: bool
    stats_unavailable: bool = False


class CacheService:
    def __init__(
        self,
        db: DatabasePool,
        scorer: ScoreService,
        stats: StatsService,
        settings: Settings,
    ) -> None:
        self.db = db
        self.scorer = scorer
        self.stats = stats
        self.settings = settings
        self._background_user_ids: set[int] = set()

    async def close(self) -> None:
        await self.stats.close()

    def background_refresh_pending(self, user_id: int) -> bool:
        return user_id in self._background_user_ids

    def is_fresh(self, fetched_at: datetime) -> bool:
        from bot.utils.time_utils import as_msk

        now = datetime.now(tz=MSK)
        fetched = as_msk(fetched_at)
        age_seconds = (now - fetched).total_seconds()
        return age_seconds < self.settings.cache_ttl_minutes * 60

    @staticmethod
    def _cache_needs_refresh(cached: PlayerCache) -> bool:
        """Refresh when derived stats were never stored or used outdated estimates."""
        if cached.matches_played <= 0 and cached.ego_score <= 0:
            return False
        if cached.ego_score <= 0:
            return False
        if cached.matches_played <= 0:
            return True
        if cached.stats.kast_percent <= 0:
            return cached.stats.acs > 0 or cached.stats.kd_ratio > 0
        if cached.stats.kast_percent >= 99.5 and cached.stats.kd_ratio < 2.0:
            return True
        # Before Competitive-only filter the bot counted Deathmatch/Unrated too.
        if cached.matches_played >= 6:
            return True
        return False

    async def warm_up_user(self, user: User) -> None:
        """Start background stats load (live API) without blocking Discord commands."""
        week_start = current_week_start()
        cached = await cache_queries.get_by_user_week(self.db, user.id, week_start)
        self._schedule_background_refresh(user, week_start, cached)

    async def get_or_refresh(self, user: User, *, force: bool = False) -> PlayerCacheView:
        week_start = current_week_start()
        cached = await cache_queries.get_by_user_week(self.db, user.id, week_start)

        if (
            cached
            and not force
            and not cached.is_stale
            and self.is_fresh(cached.fetched_at)
            and not self._cache_needs_refresh(cached)
        ):
            return PlayerCacheView(user=user, cache=cached, served_from_cache=True)

        try:
            return await self._refresh_user(user, week_start, cached)
        except StatsNotReadyError:
            self._schedule_background_refresh(user, week_start, cached)
            if cached:
                return PlayerCacheView(
                    user=user,
                    cache=cached,
                    served_from_cache=True,
                    stats_unavailable=True,
                )
            raise
        except StatsUnavailableError as exc:
            if self._should_background_refresh(exc):
                self._schedule_background_refresh(user, week_start, cached)
            if cached:
                logger.warning("Stats API unavailable, serving stale cache for %s", user.riot_id)
                return PlayerCacheView(
                    user=user,
                    cache=cached,
                    served_from_cache=True,
                    stats_unavailable=True,
                )
            raise

    def _should_background_refresh(self, exc: StatsUnavailableError) -> bool:
        return "timeout" in str(exc).lower()

    def _schedule_background_refresh(
        self,
        user: User,
        week_start,
        previous: PlayerCache | None,
    ) -> None:
        if user.id in self._background_user_ids:
            return
        self._background_user_ids.add(user.id)
        asyncio.create_task(self._run_background_refresh(user, week_start, previous))

    async def _run_background_refresh(
        self,
        user: User,
        week_start,
        previous: PlayerCache | None,
    ) -> None:
        try:
            await self._refresh_user(
                user,
                week_start,
                previous,
                background=True,
            )
            logger.info("Background refresh completed for %s", user.riot_id)
        except Exception as exc:
            logger.warning("Background refresh failed for %s: %s", user.riot_id, exc)
        finally:
            self._background_user_ids.discard(user.id)

    async def _refresh_user(
        self,
        user: User,
        week_start,
        previous: PlayerCache | None,
        *,
        background: bool = False,
        scheduled: bool = False,
    ) -> PlayerCacheView:
        if background:
            stats_result = await self.stats.fetch_stats_background(user.riot_id)
        elif scheduled:
            stats_result = await self.stats.fetch_stats(user.riot_id, allow_live=True)
        else:
            stats_result = await self.stats.fetch_stats(user.riot_id, allow_live=False)

        if stats_result.matches_played < 1:
            if previous and previous.matches_played > 0 and previous.ego_score > 0:
                logger.info(
                    "Keeping cached stats for %s (refresh returned no matches)",
                    user.riot_id,
                )
                return PlayerCacheView(
                    user=user,
                    cache=previous,
                    served_from_cache=True,
                )
            return await self._save_empty_week(user, week_start, stats_result.current_rank)

        bounds = await bounds_queries.get_all(self.db)
        if self.scorer.needs_bounds_update(stats_result.stats, bounds):
            expanded = self.scorer.expand_bounds(stats_result.stats, bounds)
            await bounds_queries.upsert(self.db, expanded)
            bounds = expanded

        score = self.scorer.calculate(stats_result.stats, bounds)
        fetched_at = msk_now()

        await cache_queries.upsert(
            self.db,
            user_id=user.id,
            week_start=week_start,
            stats=stats_result.stats,
            result=score,
            current_rank=stats_result.current_rank,
            rank_delta=0,
            fetched_at=fetched_at,
            is_stale=False,
            matches_played=stats_result.matches_played,
        )

        updated = await cache_queries.get_by_user_week(self.db, user.id, week_start)
        assert updated is not None
        return PlayerCacheView(user=user, cache=updated, served_from_cache=False)

    async def _save_empty_week(
        self,
        user: User,
        week_start,
        current_rank: str | None,
    ) -> PlayerCacheView:
        empty_stats = PlayerStats(0.0, 0.0, 0.0, 0.0, 0.0)
        bounds = await bounds_queries.get_all(self.db)
        empty_result = self.scorer.calculate(empty_stats, bounds)
        fetched_at = msk_now()

        await cache_queries.upsert(
            self.db,
            user_id=user.id,
            week_start=week_start,
            stats=empty_stats,
            result=empty_result,
            current_rank=current_rank,
            rank_delta=0,
            fetched_at=fetched_at,
            is_stale=False,
            matches_played=0,
        )

        updated = await cache_queries.get_by_user_week(self.db, user.id, week_start)
        assert updated is not None
        return PlayerCacheView(user=user, cache=updated, served_from_cache=False)

    async def refresh_all_users(self) -> int:
        users = await user_queries.list_all(self.db)
        if not users:
            return 0

        week_start = current_week_start()
        refreshed = 0
        delay_min = self.settings.request_delay_min
        delay_max = max(delay_min, self.settings.request_delay_max)

        for index, user in enumerate(users):
            try:
                cached = await cache_queries.get_by_user_week(self.db, user.id, week_start)
                await self._refresh_user(
                    user,
                    week_start,
                    cached,
                    scheduled=True,
                )
                refreshed += 1
            except PlayerNotFoundError:
                logger.warning("Player not found during refresh: %s", user.riot_id)
            except StatsError as exc:
                logger.warning("Refresh skipped for %s: %s", user.riot_id, exc)
            except Exception as exc:
                logger.warning("Refresh failed for %s: %s", user.riot_id, exc)

            if index < len(users) - 1:
                await asyncio.sleep(random.uniform(delay_min, delay_max))

        return refreshed

    async def invalidate_week(self, week_start=None) -> None:
        target = week_start or current_week_start()
        await cache_queries.mark_week_stale(self.db, target)

    async def get_by_discord_id(
        self,
        discord_id: int,
        *,
        force: bool = False,
    ) -> PlayerCacheView | None:
        user = await user_queries.get_by_discord_id(self.db, discord_id)
        if user is None:
            return None
        return await self.get_or_refresh(user, force=force)

    async def get_by_riot_id(
        self,
        riot_id: str,
        *,
        force: bool = False,
    ) -> PlayerCacheView | None:
        user = await user_queries.get_by_riot_id(self.db, riot_id)
        if user is None:
            return None
        return await self.get_or_refresh(user, force=force)
