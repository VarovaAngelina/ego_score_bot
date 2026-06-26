"""Discord interaction helpers."""

from __future__ import annotations

import logging

import discord

logger = logging.getLogger("ego_score_bot.discord")


async def ack_ephemeral(interaction: discord.Interaction) -> None:
    """Acknowledge a slash command within Discord's 3-second window."""
    if interaction.response.is_done():
        return
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.NotFound:
        age = (discord.utils.utcnow() - interaction.created_at).total_seconds()
        logger.error(
            "Interaction expired before ack (age=%.2fs, command=%s)",
            age,
            interaction.command.name if interaction.command else "?",
        )
        raise


async def reply_ephemeral(interaction: discord.Interaction, content: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)
