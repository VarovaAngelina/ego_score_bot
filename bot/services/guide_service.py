"""Post and pin the bot usage guide in a Discord channel."""

from __future__ import annotations

import logging

import discord

from bot.utils.guide import GUIDE_EMBED_TITLE, build_guide_embed

logger = logging.getLogger("ego_score_bot.guide")


async def ensure_pinned_guide(bot: discord.Client) -> None:
    settings = bot.settings
    if not settings.guide_enabled:
        return

    channel = bot.get_channel(settings.guide_channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(settings.guide_channel_id)
        except (discord.HTTPException, discord.NotFound):
            logger.error("Guide channel %s not found", settings.guide_channel_id)
            return

    if not isinstance(channel, discord.TextChannel):
        logger.error("Guide channel %s is not a text channel", settings.guide_channel_id)
        return

    embed = build_guide_embed(top_limit=settings.top_limit)
    guide_message = await _find_guide_message(channel, bot.user.id)

    if guide_message is None:
        guide_message = await channel.send(embed=embed)
        logger.info("Posted guide in channel %s", channel.id)
    else:
        await guide_message.edit(embed=embed)
        logger.info("Updated guide in channel %s", channel.id)

    if not guide_message.pinned:
        try:
            await guide_message.pin(reason="Ego Score Bot — инструкция")
            logger.info("Pinned guide in channel %s", channel.id)
        except discord.Forbidden:
            logger.warning("Cannot pin guide in channel %s — need Manage Messages", channel.id)


async def _find_guide_message(
    channel: discord.TextChannel,
    bot_user_id: int,
) -> discord.Message | None:
    pins = await channel.pins()
    for message in pins:
        if message.author.id == bot_user_id and _is_guide_message(message):
            return message

    async for message in channel.history(limit=100):
        if message.author.id == bot_user_id and _is_guide_message(message):
            return message
    return None


def _is_guide_message(message: discord.Message) -> bool:
    if not message.embeds:
        return False
    return message.embeds[0].title == GUIDE_EMBED_TITLE
