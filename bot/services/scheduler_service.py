"""APScheduler jobs: cache refresh + live top, Sunday 23:59 MSK snapshot."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bot.config import MSK
from bot.services.refresh_jobs import refresh_all_and_update_top
from bot.services.snapshot_service import SnapshotService

logger = logging.getLogger("ego_score_bot.scheduler")


class SchedulerService:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone=bot.settings.timezone)
        self.snapshot = SnapshotService(bot.db_pool, bot.settings)

    def start(self) -> None:
        if self.scheduler.running:
            return

        refresh_minutes = self.bot.settings.cache_ttl_minutes
        first_refresh = datetime.now(tz=MSK) + timedelta(seconds=30)

        self.scheduler.add_job(
            self._job_refresh_and_top,
            IntervalTrigger(minutes=refresh_minutes),
            id="refresh_and_top",
            replace_existing=True,
            max_instances=1,
            next_run_time=first_refresh,
        )
        self.scheduler.add_job(
            self._job_pre_snapshot_refresh,
            CronTrigger(
                day_of_week="sun",
                hour=23,
                minute=45,
                timezone=self.bot.settings.timezone,
            ),
            id="pre_snapshot_refresh",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._job_weekly_snapshot,
            CronTrigger(
                day_of_week="sun",
                hour=23,
                minute=59,
                timezone=self.bot.settings.timezone,
            ),
            id="weekly_snapshot",
            replace_existing=True,
            max_instances=1,
        )
        self.scheduler.start()
        logger.info(
            "Scheduler started: first refresh+top at %s MSK, then every %s min; snapshot Sun 23:59 %s",
            first_refresh.strftime("%H:%M:%S"),
            refresh_minutes,
            self.bot.settings.tz,
        )

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    async def _job_refresh_and_top(self) -> None:
        try:
            await refresh_all_and_update_top(self.bot)
        except Exception:
            logger.exception("Scheduled refresh and top update failed")

    async def _job_pre_snapshot_refresh(self) -> None:
        cache = self.bot.cache_service
        if cache is None:
            logger.warning("Pre-snapshot refresh skipped: cache service unavailable")
            return
        try:
            refreshed = await cache.refresh_all_users()
            logger.info("Pre-snapshot refresh completed: %s users updated", refreshed)
        except Exception:
            logger.exception("Pre-snapshot refresh failed")

    async def _job_weekly_snapshot(self) -> None:
        try:
            await self.snapshot.take_snapshot(self.bot)
        except Exception:
            logger.exception("Weekly snapshot job failed")

    async def run_startup_refresh(self) -> None:
        """Refresh all registered players soon after bot start."""
        await asyncio.sleep(20)
        try:
            await refresh_all_and_update_top(self.bot)
            logger.info("Startup refresh and top update completed")
        except Exception:
            logger.exception("Startup refresh failed")
