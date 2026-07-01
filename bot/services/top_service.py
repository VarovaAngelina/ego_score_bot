"""Post and periodically edit the live weekly top embed in Discord."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import discord

from bot.database.queries import cache_queries, config_queries, snapshot_queries, user_queries
from bot.services.rank_delta import refresh_rank_deltas
from bot.utils.formatters import build_announce_embed, build_top_embed, format_week_range, is_live_top_embed
from bot.utils.time_utils import current_week_end, current_week_start, msk_now

logger = logging.getLogger("ego_score_bot.top")

CONFIG_CHANNEL_KEY = "live_top_channel_id"
CONFIG_MESSAGE_KEY = "live_top_message_id"
CONFIG_WEEK_KEY = "live_top_week_start"
CONFIG_FINALIZED_WEEK_KEY = "live_top_finalized_week"
CONFIG_ROLLOVER_MIGRATION_KEY = "live_top_rollover_v1"


class TopService:
    def __init__(self, bot) -> None:
        self.bot = bot

    @property
    def db(self):
        pool = getattr(self.bot, "db_pool", None)
        if pool is None:
            raise RuntimeError("Database pool is not initialized")
        return pool

    def resolve_channel_id(self) -> int | None:
        settings = self.bot.settings
        if settings.top_channel_id > 0:
            return settings.top_channel_id
        if settings.announce_channel_id > 0:
            return settings.announce_channel_id
        return None

    async def _load_tracked_week(self) -> date | None:
        raw = await config_queries.get(self.db, CONFIG_WEEK_KEY)
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            logger.warning("Invalid live_top_week_start in config: %s", raw)
            return None

    async def _save_tracked_week(self, week_start: date) -> None:
        await config_queries.set(self.db, CONFIG_WEEK_KEY, week_start.isoformat())

    async def build_embed_for_week(self, week_start: date) -> discord.Embed:
        await refresh_rank_deltas(self.db, week_start)

        week_end = current_week_end(week_start)
        week_label = format_week_range(week_start, week_end)
        top_limit = self.bot.settings.top_limit

        entries = await cache_queries.get_top_for_week(self.db, week_start, limit=top_limit)
        scored_count = await cache_queries.count_scored_for_week(self.db, week_start)
        registered_count = await user_queries.count_all(self.db)

        return build_top_embed(
            entries,
            week_label=week_label,
            registered_count=registered_count,
            scored_count=scored_count,
            updated_at=msk_now(),
            top_limit=top_limit,
        )

    async def _get_top_channel(self) -> discord.TextChannel | None:
        channel_id = self.resolve_channel_id()
        if channel_id is None:
            return None
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.HTTPException, discord.NotFound):
                logger.error("Top channel %s not found", channel_id)
                return None
        if not isinstance(channel, discord.TextChannel):
            logger.error("Top channel %s is not a text channel", channel_id)
            return None
        return channel

    async def finalize_week_for_snapshot(self, week_start: date) -> None:
        """Sunday snapshot: freeze the live top message; do not post a second summary."""
        channel = await self._get_top_channel()
        if channel is None:
            return

        live_message = await self._find_newest_top_message(channel)
        await self._finalize_week(channel, week_start, live_message)
        await self._save_tracked_week(week_start)
        await config_queries.set(self.db, CONFIG_FINALIZED_WEEK_KEY, week_start.isoformat())
        logger.info("Week %s finalized in top channel %s (no duplicate post)", week_start, channel.id)

    async def build_embed(self) -> discord.Embed:
        return await self.build_embed_for_week(current_week_start())

    async def _leaderboard_for_week(self, week_start: date, *, top_limit: int) -> tuple[list, int]:
        if await snapshot_queries.week_exists(self.db, week_start):
            all_entries = await snapshot_queries.get_all_for_week(self.db, week_start)
            scored_count = await snapshot_queries.count_for_week(self.db, week_start)
            return all_entries[:top_limit], scored_count

        entries = await cache_queries.get_top_for_week(self.db, week_start, limit=top_limit)
        scored_count = await cache_queries.count_scored_for_week(self.db, week_start)
        return entries, scored_count

    async def _finalize_week(
        self,
        channel: discord.TextChannel,
        week_start: date,
        message: discord.Message | None,
    ) -> discord.Message | None:
        week_end = current_week_end(week_start)
        week_label = format_week_range(week_start, week_end)
        top_limit = self.bot.settings.top_limit

        entries, scored_count = await self._leaderboard_for_week(week_start, top_limit=top_limit)
        registered_count = await user_queries.count_all(self.db)

        embed = build_announce_embed(
            entries,
            week_label=week_label,
            registered_count=registered_count,
            scored_count=scored_count,
            top_limit=top_limit,
        )

        if message is not None and message.embeds and is_live_top_embed(message.embeds[0]):
            await message.edit(embed=embed)
            logger.info(
                "Finalized week %s on live top message %s in channel %s",
                week_label,
                message.id,
                channel.id,
            )
            return message

        posted = await channel.send(embed=embed)
        logger.info("Posted finalized week %s in channel %s", week_label, channel.id)
        return posted

    async def _maybe_migrate_rollover(
        self,
        channel: discord.TextChannel,
        message: discord.Message | None,
        current_week: date,
    ) -> discord.Message | None:
        if await config_queries.get(self.db, CONFIG_ROLLOVER_MIGRATION_KEY):
            return message

        await config_queries.set(self.db, CONFIG_ROLLOVER_MIGRATION_KEY, "1")

        if message is None or not message.embeds or not is_live_top_embed(message.embeds[0]):
            await self._save_tracked_week(current_week)
            return message

        previous_week = current_week - timedelta(days=7)
        scored_prev = await cache_queries.count_scored_for_week(self.db, previous_week)
        snap_prev = await snapshot_queries.week_exists(self.db, previous_week)
        if scored_prev <= 0 and not snap_prev:
            await self._save_tracked_week(current_week)
            return message

        await self._finalize_week(channel, previous_week, message)
        await self._save_tracked_week(current_week)
        return None

    async def _handle_week_rollover(
        self,
        channel: discord.TextChannel,
        message: discord.Message | None,
        tracked_week: date | None,
        current_week: date,
    ) -> discord.Message | None:
        if tracked_week is None:
            return await self._maybe_migrate_rollover(channel, message, current_week)

        if tracked_week >= current_week:
            return message

        finalized_raw = await config_queries.get(self.db, CONFIG_FINALIZED_WEEK_KEY)
        if finalized_raw != tracked_week.isoformat():
            await self._finalize_week(channel, tracked_week, message)
        else:
            logger.info("Week %s already finalized on snapshot — skipping duplicate", tracked_week)

        await self._save_tracked_week(current_week)
        return None

    async def update_live_top(self, *, channel: discord.TextChannel | None = None) -> discord.Message | None:
        if channel is None:
            channel = await self._get_top_channel()
            if channel is None:
                return None
        elif not isinstance(channel, discord.TextChannel):
            logger.error("Top channel %s is not a text channel", getattr(channel, "id", channel))
            return None

        current_week = current_week_start()
        message = await self._find_newest_top_message(channel)
        tracked_week = await self._load_tracked_week()
        message = await self._handle_week_rollover(channel, message, tracked_week, current_week)

        embed = await self.build_embed()
        if message is None:
            message = await channel.send(embed=embed)
            logger.info("Posted live top in channel %s", channel.id)
        else:
            await message.edit(embed=embed)
            logger.info("Updated live top message %s in channel %s", message.id, channel.id)

        await self._remove_stale_top_messages(channel, keep_id=message.id)
        await self._save_tracked_week(current_week)

        await config_queries.set(self.db, CONFIG_CHANNEL_KEY, str(channel.id))
        await config_queries.set(self.db, CONFIG_MESSAGE_KEY, str(message.id))
        return message

    async def post_finalized_week(
        self,
        channel: discord.TextChannel,
        week_start: date,
    ) -> discord.Message | None:
        """Post frozen weekly results (e.g. after Sunday snapshot)."""
        return await self._finalize_week(channel, week_start, message=None)

    async def _find_newest_top_message(self, channel: discord.TextChannel) -> discord.Message | None:
        """Newest bot message with a live top embed (channel history is newest-first)."""
        async for message in channel.history(limit=100):
            if message.author.id != self.bot.user.id or not message.embeds:
                continue
            if is_live_top_embed(message.embeds[0]):
                return message
        return None

    async def _remove_stale_top_messages(self, channel: discord.TextChannel, *, keep_id: int) -> None:
        removed = 0
        async for message in channel.history(limit=100):
            if message.id == keep_id:
                continue
            if message.author.id != self.bot.user.id or not message.embeds:
                continue
            if not is_live_top_embed(message.embeds[0]):
                continue
            try:
                await message.delete()
                removed += 1
            except discord.HTTPException as exc:
                logger.warning("Could not delete old top message %s: %s", message.id, exc)
        if removed:
            logger.info("Removed %s old top message(s) in channel %s", removed, channel.id)


async def update_live_top(bot, *, channel: discord.TextChannel | None = None) -> bool:
    message = await TopService(bot).update_live_top(channel=channel)
    return message is not None
