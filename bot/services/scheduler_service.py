"""APScheduler jobs: 30-min cache refresh, Sunday 23:59 MSK snapshot."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bot.config import MSK
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
        first_refresh = datetime.now(tz=MSK) + timedelta(minutes=refresh_minutes)

        self.scheduler.add_job(
            self._job_refresh_cache,
            IntervalTrigger(minutes=refresh_minutes),
            id="refresh_cache",
            replace_existing=True,
            max_instances=1,
            next_run_time=first_refresh,
        )
        self.scheduler.add_job(
            self._job_update_live_top,
            IntervalTrigger(minutes=refresh_minutes),
            id="update_live_top",
            replace_existing=True,
            max_instances=1,
            next_run_time=datetime.now(tz=MSK) + timedelta(seconds=20),
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
            "Scheduler started: first refresh at %s MSK, then every %s min; snapshot Sun 23:59 %s",
            first_refresh.strftime("%H:%M"),
            refresh_minutes,
            self.bot.settings.tz,
        )

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    async def _job_refresh_cache(self) -> None:
        cache = self.bot.cache_service
        if cache is None:
            logger.warning("Scheduled refresh skipped: cache service unavailable")
            return

        try:
            refreshed = await cache.refresh_all_users()
            logger.info("Scheduled refresh completed: %s users updated", refreshed)
        except Exception:
            logger.exception("Scheduled refresh failed")
            return

        if self.bot.settings.live_top_enabled:
            try:
                from bot.services.top_service import update_live_top

                await update_live_top(self.bot)
            except Exception:
                logger.exception("Live top update failed")

    async def _job_update_live_top(self) -> None:
        if not self.bot.settings.live_top_enabled:
            return
        try:
            from bot.services.top_service import update_live_top

            await update_live_top(self.bot)
            logger.info("Scheduled live top embed updated")
        except Exception:
            logger.exception("Scheduled live top update failed")

    async def _job_weekly_snapshot(self) -> None:
        try:
            await self.snapshot.take_snapshot(self.bot)
        except Exception:
            logger.exception("Weekly snapshot job failed")
