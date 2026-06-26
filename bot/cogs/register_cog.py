"""Slash commands: /register, /unregister, /profile."""



from __future__ import annotations



import logging



import discord

from discord import app_commands

from discord.ext import commands



from bot.database.queries import cache_queries, user_queries

from bot.services.cache_service import BACKGROUND_LOADING_NOTE, CacheService

from bot.services.stats_service import StatsService

from bot.services.stats_types import PlayerNotFoundError, ProfilePrivateError, StatsError, StatsNotReadyError, StatsUnavailableError

from bot.utils.discord_utils import ack_ephemeral, reply_ephemeral

from bot.utils.formatters import build_profile_embed, format_week_range

from bot.utils.time_utils import current_week_end, current_week_start



logger = logging.getLogger("ego_score_bot.register")





class RegisterCog(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:

        self.bot = bot



    @property

    def cache(self) -> CacheService:

        service = getattr(self.bot, "cache_service", None)

        if service is None:

            raise RuntimeError("CacheService is not initialized")

        return service



    @property

    def stats(self) -> StatsService:

        service = getattr(self.bot, "stats", None)

        if service is None:

            raise RuntimeError("StatsService is not initialized")

        return service



    async def _profile_rank_hint(self, user, view) -> str | None:
        if view is not None:
            return view.cache.current_rank
        cached = await cache_queries.get_by_user_week(
            self.cache.db,
            user.id,
            current_week_start(),
        )
        return cached.current_rank if cached else None



    @app_commands.command(name="register", description="Привязать Discord-аккаунт к Riot ID")

    @app_commands.describe(riot_id="Riot ID в формате Name#TAG")

    async def register(self, interaction: discord.Interaction, riot_id: str) -> None:

        await ack_ephemeral(interaction)



        try:

            StatsService.parse_riot_id(riot_id)

        except StatsError:

            await interaction.followup.send(

                "Неверный формат Riot ID. Используй `Name#TAG`, например `TenZ#NA1`.",

                ephemeral=True,

            )

            return



        normalized = riot_id.strip()

        if normalized.count("#") != 1:

            await interaction.followup.send("Неверный формат Riot ID.", ephemeral=True)

            return



        name, tag = normalized.split("#", 1)

        normalized = f"{name.strip()}#{tag.strip()}"



        existing_self = await user_queries.get_by_discord_id(self.cache.db, interaction.user.id)

        if existing_self is not None:

            if existing_self.riot_id == normalized:

                await interaction.followup.send(

                    f"Ты уже зарегистрирован как **{existing_self.riot_id}**.\n"

                    "Используй `/profile` или `/ego`.",

                    ephemeral=True,

                )

                return

            await interaction.followup.send(

                f"Ты уже привязан к **{existing_self.riot_id}**.\n"

                "Сначала `/unregister`, затем `/register` с новым Riot ID.",

                ephemeral=True,

            )

            return



        existing_riot = await user_queries.get_by_riot_id(self.cache.db, normalized)

        if existing_riot is not None:

            await interaction.followup.send(

                "Этот Riot ID уже привязан к другому Discord-аккаунту.",

                ephemeral=True,

            )

            return



        settings = getattr(self.bot, "settings", None)

        if settings and settings.henrik_api_key:

            try:

                from bot.services.henrik_service import verify_riot_account_access



                await verify_riot_account_access(

                    self.stats.http_session,

                    normalized,

                    settings.henrik_api_key,

                )

            except PlayerNotFoundError:

                await interaction.followup.send(

                    "Аккаунт **не найден** в Riot.\n"

                    "Проверь имя, **тег** (`EG0` vs `EGO`) и пробелы.",

                    ephemeral=True,

                )

                return

            except StatsUnavailableError:

                await interaction.followup.send(

                    "Проверка Riot ID временно недоступна.\n"

                    "Попробуй `/register` через минуту.",

                    ephemeral=True,

                )

                return

        else:

            await interaction.followup.send(

                "Сервис проверки аккаунтов не настроен. Обратись к администратору.",

                ephemeral=True,

            )

            return



        try:

            user = await user_queries.register(self.cache.db, interaction.user.id, normalized)

        except user_queries.RegistrationPersistError:

            logger.exception("Failed to persist registration for discord_id=%s", interaction.user.id)

            await interaction.followup.send(

                "Не удалось сохранить регистрацию в базе данных. Попробуй `/register` ещё раз.",

                ephemeral=True,

            )

            return



        await self.cache.warm_up_user(user)

        await interaction.followup.send(

            f"✅ Аккаунт привязан: **{user.riot_id}**\n"

            "Используй `/profile` для Ego Score.\n"

            "Если профиль закрыт — `/profile` покажет, как его открыть.",

            ephemeral=True,

        )



    @app_commands.command(name="unregister", description="Отвязать Riot ID от Discord-аккаунта")

    async def unregister(self, interaction: discord.Interaction) -> None:

        await ack_ephemeral(interaction)

        removed = await user_queries.unregister(self.cache.db, interaction.user.id)

        if not removed:

            await interaction.followup.send(

                "Ты не зарегистрирован. Используй `/register <nick#tag>`.",

                ephemeral=True,

            )

            return

        await interaction.followup.send("✅ Аккаунт отвязан.", ephemeral=True)



    @app_commands.command(name="profile", description="Riot ID, ранг и Ego Score текущей недели")

    async def profile(self, interaction: discord.Interaction) -> None:

        await ack_ephemeral(interaction)



        user = await user_queries.get_by_discord_id(self.cache.db, interaction.user.id)

        if user is None:

            await interaction.followup.send(

                "Используй `/register <nick#tag>` для привязки.",

                ephemeral=True,

            )

            return



        week_label = format_week_range(current_week_start(), current_week_end())

        error_note: str | None = None



        try:

            view = await self.cache.get_or_refresh(user)

        except ProfilePrivateError as exc:

            error_note = str(exc)

            logger.warning("Profile private for %s", user.riot_id)

            view = None

        except StatsNotReadyError:

            error_note = BACKGROUND_LOADING_NOTE

            logger.info("Profile stats not ready yet for %s, background refresh scheduled", user.riot_id)

            view = None

        except StatsUnavailableError as exc:

            if self.cache.background_refresh_pending(user.id) or "timeout" in str(exc).lower():

                error_note = BACKGROUND_LOADING_NOTE

            else:

                error_note = str(exc)

            logger.warning("Profile unavailable for %s: %s", user.riot_id, exc)

            view = None

        except StatsError as exc:

            error_note = str(exc)

            logger.warning("Profile cache error for %s: %s", user.riot_id, exc)

            view = None

        except Exception as exc:

            error_note = f"Internal error: {exc}"

            logger.exception("Profile command failed for %s", user.riot_id)

            view = None



        embed = build_profile_embed(
            user,
            view,
            week_label=week_label,
            error_note=error_note,
            current_rank=await self._profile_rank_hint(user, view),
        )

        await interaction.followup.send(embed=embed, ephemeral=True)





async def setup(bot: commands.Bot) -> None:

    await bot.add_cog(RegisterCog(bot))

