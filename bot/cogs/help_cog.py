"""Slash commands: /help, /ping."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.services.guide_service import ensure_pinned_guide
from bot.services.top_service import update_live_top
from bot.utils.discord_utils import ack_ephemeral
from bot.utils.guide import build_guide_embed

logger = logging.getLogger("ego_score_bot.help")


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Справка по командам Ego Score Bot")
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        await ack_ephemeral(interaction)
        embed = build_guide_embed(top_limit=self.bot.settings.top_limit)
        if self.bot.settings.guide_enabled:
            embed.description = (
                f"{embed.description}\n\n"
                f"📌 Полная инструкция закреплена в <#{self.bot.settings.guide_channel_id}>."
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ping", description="Проверка связи с ботом и базой данных")
    async def ping(self, interaction: discord.Interaction) -> None:
        db_status = "не подключена"
        db_pool = getattr(self.bot, "db_pool", None)
        if db_pool is not None:
            try:
                await db_pool.ping()
                db_status = "ok"
            except Exception as exc:
                db_status = f"ошибка: {exc.__class__.__name__}"

        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"Pong! Discord: **{latency_ms} ms** · MySQL: **{db_status}**",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await ensure_pinned_guide(self.bot)
        if self.bot.settings.live_top_enabled:
            try:
                await update_live_top(self.bot)
            except Exception:
                logger.exception("Failed to update live top on ready")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
