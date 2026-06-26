"""Slash commands: /ego, /ego with optional player Riot ID."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.models import User
from bot.database.queries import cache_queries, user_queries
from bot.services.cache_service import BACKGROUND_LOADING_NOTE, CacheService
from bot.services.stats_service import StatsService
from bot.services.stats_types import (
    ProfilePrivateError,
    StatsError,
    StatsNotReadyError,
    StatsUnavailableError,
)
from bot.utils.discord_utils import ack_ephemeral, reply_ephemeral
from bot.utils.formatters import build_ego_embed, build_ego_error_embed, format_week_range
from bot.utils.time_utils import current_week_end, current_week_start

logger = logging.getLogger("ego_score_bot.ego")


class EgoCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def cache(self) -> CacheService:
        service = getattr(self.bot, "cache_service", None)
        if service is None:
            raise RuntimeError("CacheService is not initialized")
        return service

    async def _profile_rank_hint(self, user: User, view) -> str | None:
        if view is not None:
            return view.cache.current_rank
        cached = await cache_queries.get_by_user_week(
            self.cache.db,
            user.id,
            current_week_start(),
        )
        return cached.current_rank if cached else None

    async def _resolve_user(
        self,
        interaction: discord.Interaction,
        player: str | None,
    ) -> User | None:
        if player is None:
            user = await user_queries.get_by_discord_id(self.cache.db, interaction.user.id)
            if user is None:
                await reply_ephemeral(
                    interaction,
                    "Сначала привяжи аккаунт: `/register <nick#tag>`.",
                )
            return user

        try:
            StatsService.parse_riot_id(player)
        except StatsError:
            await reply_ephemeral(
                interaction,
                "Неверный формат Riot ID. Используй `Name#TAG`, например `TenZ#NA1`.",
            )
            return None

        normalized = player.strip()
        name, tag = normalized.split("#", 1)
        normalized = f"{name.strip()}#{tag.strip()}"

        user = await user_queries.get_by_riot_id(self.cache.db, normalized)
        if user is None:
            await reply_ephemeral(
                interaction,
                f"Игрок **{normalized}** не зарегистрирован в боте.",
            )
            return None
        return user

    @app_commands.command(
        name="ego",
        description="Ego Score текущей недели (свой или зарегистрированного игрока)",
    )
    @app_commands.describe(player="Riot ID игрока (опционально, формат Name#TAG)")
    async def ego(self, interaction: discord.Interaction, player: str | None = None) -> None:
        user = await self._resolve_user(interaction, player)
        if user is None:
            return

        week_label = format_week_range(current_week_start(), current_week_end())

        await ack_ephemeral(interaction)

        error_note: str | None = None
        view = None

        try:
            view = await self.cache.get_or_refresh(user)
        except ProfilePrivateError as exc:
            error_note = str(exc)
            logger.warning("Ego score private profile for %s", user.riot_id)
        except StatsNotReadyError:
            error_note = BACKGROUND_LOADING_NOTE
            logger.info("Ego stats not ready for %s, background refresh scheduled", user.riot_id)
        except StatsUnavailableError as exc:
            if self.cache.background_refresh_pending(user.id) or "timeout" in str(exc).lower():
                error_note = BACKGROUND_LOADING_NOTE
            else:
                error_note = str(exc)
            logger.warning("Ego unavailable for %s: %s", user.riot_id, exc)
        except StatsError as exc:
            error_note = str(exc)
            logger.warning("Ego cache error for %s: %s", user.riot_id, exc)
        except Exception as exc:
            error_note = f"Internal error: {exc}"
            logger.exception("Ego command failed for %s", user.riot_id)

        if view is None:
            embed = build_ego_error_embed(
                user,
                week_label=week_label,
                error_note=error_note,
                current_rank=await self._profile_rank_hint(user, view),
            )
        else:
            week_rank: int | None = None
            scored_count = 0
            if view.cache.ego_score > 0 and view.cache.matches_played > 0:
                week_rank, scored_count = await cache_queries.get_user_week_rank(
                    self.cache.db,
                    user.id,
                    current_week_start(),
                )
            embed = build_ego_embed(
                view,
                week_label=week_label,
                week_rank=week_rank,
                scored_count=scored_count,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EgoCog(bot))
