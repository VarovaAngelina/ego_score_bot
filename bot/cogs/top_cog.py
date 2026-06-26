"""Slash commands: /top (top 10), /history (all players, paginated)."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import snapshot_queries
from bot.services.top_service import TopService
from bot.utils.discord_utils import ack_ephemeral
from bot.utils.formatters import (
    build_history_list_embed,
    build_history_pages,
    build_history_picker_embed,
    format_week_range,
)
from bot.utils.history_views import HistoryLeaderboardView, HistoryWeekPickerView
from bot.utils.time_utils import (
    current_week_end,
    current_week_start,
    parse_week_argument,
)

logger = logging.getLogger("ego_score_bot.top")

HISTORY_WEEK_LIST_LIMIT = 100


class TopCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def db(self):
        pool = getattr(self.bot, "db_pool", None)
        if pool is None:
            raise RuntimeError("Database pool is not initialized")
        return pool

    async def _load_history_weeks(self):
        return await snapshot_queries.list_weeks(self.db, limit=HISTORY_WEEK_LIST_LIMIT)

    async def _history_send(self, interaction: discord.Interaction, **kwargs) -> None:
        kwargs.setdefault("ephemeral", True)
        await interaction.followup.send(**kwargs)

    @app_commands.command(
        name="top",
        description="Топ игроков текущей недели по Ego Score",
    )
    async def top(self, interaction: discord.Interaction) -> None:
        await ack_ephemeral(interaction)

        service = TopService(self.bot)
        channel_id = service.resolve_channel_id()

        if channel_id is None:
            await interaction.followup.send(
                "Канал для топа не настроен (`TOP_CHANNEL_ID` или `ANNOUNCE_CHANNEL_ID`).",
                ephemeral=True,
            )
            return

        target_channel = interaction.channel
        if not isinstance(target_channel, discord.TextChannel) or target_channel.id != channel_id:
            target_channel = self.bot.get_channel(channel_id)
            if target_channel is None:
                try:
                    target_channel = await self.bot.fetch_channel(channel_id)
                except (discord.HTTPException, discord.NotFound):
                    target_channel = None

        try:
            if isinstance(target_channel, discord.TextChannel):
                message = await service.update_live_top(channel=target_channel)
            else:
                message = await service.update_live_top()
        except Exception:
            logger.exception("Failed to update live top")
            await interaction.followup.send(
                "Не удалось обновить рейтинг. Попробуй позже.",
                ephemeral=True,
            )
            return

        if message is None:
            await interaction.followup.send(
                "Не удалось обновить рейтинг. Проверь канал топа.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Топ обновлён: {message.jump_url}",
            ephemeral=True,
        )

    @app_commands.command(
        name="history",
        description="Итоги прошлых недель (выбор недели кнопками или по дате)",
    )
    @app_commands.describe(week="Начало недели (YYYY-MM-DD), например 2026-06-09")
    async def history(self, interaction: discord.Interaction, week: str | None = None) -> None:
        await ack_ephemeral(interaction)

        if week is None:
            try:
                weeks = await self._load_history_weeks()
            except Exception:
                logger.exception("Failed to list history weeks")
                await self._history_send(
                    interaction,
                    content="Не удалось загрузить историю. Попробуй позже.",
                )
                return

            if not weeks:
                embed = build_history_list_embed([])
                await self._history_send(interaction, embed=embed)
                return

            embed = build_history_picker_embed(weeks, page=0)
            view = HistoryWeekPickerView(self.db, weeks, page=0)
            await self._history_send(interaction, embed=embed, view=view)
            return

        try:
            week_start = parse_week_argument(week)
        except ValueError:
            await self._history_send(
                interaction,
                content="Неверный формат даты. Используй `YYYY-MM-DD`, например `2026-06-09`.",
            )
            return

        week_end = current_week_end(week_start)
        week_label = format_week_range(week_start, week_end)

        try:
            exists = await snapshot_queries.week_exists(self.db, week_start)
            if not exists:
                embed = discord.Embed(
                    title=f"📅 Итоги недели {week_label}",
                    description=(
                        f"Нет снепшота за неделю **{week_label}**.\n"
                        "Вызови `/history` без аргумента для списка недель."
                    ),
                    color=discord.Color.orange(),
                )
                await self._history_send(interaction, embed=embed)
                return

            entries = await snapshot_queries.get_all_for_week(self.db, week_start)
            weeks = await self._load_history_weeks()
        except Exception:
            logger.exception("Failed to load /history for week %s", week_start)
            await self._history_send(
                interaction,
                content="Не удалось загрузить историю недели. Попробуй позже.",
            )
            return

        pages = build_history_pages(entries, week_label=week_label)
        view = HistoryLeaderboardView.for_week(
            db=self.db,
            weeks=weeks,
            pages=pages,
            show_back=bool(weeks),
        )
        if view.children:
            await self._history_send(interaction, embed=pages[0], view=view)
        else:
            await self._history_send(interaction, embed=pages[0])


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TopCog(bot))
