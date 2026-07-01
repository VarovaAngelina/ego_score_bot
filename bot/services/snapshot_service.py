"""Weekly snapshot persistence (all players) and announce embed (top 10)."""

from __future__ import annotations

import logging

import discord

from bot.config import Settings
from bot.database.connection import DatabasePool
from bot.database.models import LeaderboardEntry, WeeklySnapshotRow
from bot.database.queries import cache_queries, snapshot_queries, user_queries
from bot.services.top_service import TopService
from bot.utils.formatters import build_announce_embed, format_week_range
from bot.utils.time_utils import current_week_end, current_week_start

logger = logging.getLogger("ego_score_bot.snapshot")


class SnapshotService:
    def __init__(self, db: DatabasePool, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def take_snapshot(self, bot: discord.Client) -> bool:
        cache = getattr(bot, "cache_service", None)
        if cache is not None:
            try:
                refreshed = await cache.refresh_all_users()
                logger.info("Snapshot pre-refresh: %s users updated", refreshed)
            except Exception:
                logger.exception("Snapshot pre-refresh failed")

        week_start = current_week_start()
        week_end = current_week_end(week_start)
        week_label = format_week_range(week_start, week_end)

        registered_count = await user_queries.count_all(self.db)
        if registered_count == 0:
            logger.warning("Weekly snapshot skipped: no registered users")
            return False

        scored = await cache_queries.list_scored_for_week(self.db, week_start)
        if not scored:
            logger.warning("Weekly snapshot skipped: no scored players for %s", week_label)
            return False

        snapshot_rows: list[WeeklySnapshotRow] = []
        leaderboard: list[LeaderboardEntry] = []
        for rank, (user_id, riot_id, current_rank, ego_score, stats) in enumerate(scored, start=1):
            snapshot_rows.append(
                WeeklySnapshotRow(
                    week_start=week_start,
                    week_end=week_end,
                    rank=rank,
                    user_id=user_id,
                    riot_id=riot_id,
                    current_rank=current_rank,
                    ego_score=ego_score,
                    stats=stats,
                )
            )
            if rank <= self.settings.top_limit:
                leaderboard.append(
                    LeaderboardEntry(
                        rank=rank,
                        user_id=user_id,
                        riot_id=riot_id,
                        current_rank=current_rank,
                        ego_score=ego_score,
                        rank_delta=0,
                    )
                )

        await snapshot_queries.save_week(self.db, week_start, week_end, snapshot_rows)
        await cache_queries.mark_week_stale(self.db, week_start)
        logger.info(
            "Weekly snapshot saved for %s: %s players",
            week_label,
            len(snapshot_rows),
        )

        top = TopService(bot)
        top_channel_id = top.resolve_channel_id()
        if top_channel_id:
            await top.finalize_week_for_snapshot(week_start)

        announce_id = self.settings.announce_channel_id
        if (
            self.settings.announce_enabled
            and announce_id > 0
            and (top_channel_id is None or announce_id != top_channel_id)
        ):
            await self.announce(
                bot,
                week_label=week_label,
                leaderboard=leaderboard,
                registered_count=registered_count,
                scored_count=len(scored),
            )

        return True

    async def announce(
        self,
        bot: discord.Client,
        *,
        week_label: str,
        leaderboard: list[LeaderboardEntry],
        registered_count: int,
        scored_count: int,
    ) -> None:
        if not self.settings.announce_enabled:
            logger.info("Weekly announce skipped (ANNOUNCE_CHANNEL_ID=0)")
            return

        if not leaderboard:
            logger.warning("Weekly announce skipped: empty leaderboard")
            return

        channel = bot.get_channel(self.settings.announce_channel_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(self.settings.announce_channel_id)
            except (discord.HTTPException, discord.NotFound):
                logger.error(
                    "Announce channel %s not found",
                    self.settings.announce_channel_id,
                )
                return

        if not isinstance(channel, discord.abc.Messageable):
            logger.error("Announce channel %s is not messageable", self.settings.announce_channel_id)
            return

        embed = build_announce_embed(
            leaderboard,
            week_label=week_label,
            registered_count=registered_count,
            scored_count=scored_count,
            top_limit=self.settings.top_limit,
        )
        await channel.send(embed=embed)
        logger.info("Weekly announce posted to channel %s", self.settings.announce_channel_id)
