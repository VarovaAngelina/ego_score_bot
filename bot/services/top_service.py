"""Post and periodically edit the live weekly top embed in Discord."""

from __future__ import annotations

import logging

import discord

from bot.database.queries import cache_queries, config_queries, user_queries
from bot.services.rank_delta import refresh_rank_deltas
from bot.utils.formatters import build_top_embed, format_week_range, is_live_top_embed
from bot.utils.time_utils import current_week_end, current_week_start, msk_now

logger = logging.getLogger("ego_score_bot.top")

CONFIG_CHANNEL_KEY = "live_top_channel_id"
CONFIG_MESSAGE_KEY = "live_top_message_id"


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

    async def build_embed(self) -> discord.Embed:
        week_start = current_week_start()
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

    async def update_live_top(self, *, channel: discord.TextChannel | None = None) -> discord.Message | None:
        if channel is None:
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
            logger.error("Top channel %s is not a text channel", getattr(channel, "id", channel))
            return None

        embed = await self.build_embed()
        message = await self._find_newest_top_message(channel)

        if message is None:
            message = await channel.send(embed=embed)
            logger.info("Posted live top in channel %s", channel.id)
        else:
            await message.edit(embed=embed)
            logger.info("Updated live top message %s in channel %s", message.id, channel.id)

        await self._remove_stale_top_messages(channel, keep_id=message.id)

        await config_queries.set(self.db, CONFIG_CHANNEL_KEY, str(channel.id))
        await config_queries.set(self.db, CONFIG_MESSAGE_KEY, str(message.id))
        return message

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
