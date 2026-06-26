"""Entry point: Discord bot initialization and scheduler startup."""



from __future__ import annotations



import asyncio

import logging

import sys



import discord

from discord.ext import commands



from bot.config import Settings, get_settings

from bot.database.connection import DatabasePool

from bot.services.cache_service import CacheService

from bot.services.scheduler_service import SchedulerService

from bot.services.stats_service import StatsService

from bot.utils.logger import setup_logging



logger = logging.getLogger("ego_score_bot")



COGS = (
    "bot.cogs.help_cog",
    "bot.cogs.register_cog",
    "bot.cogs.ego_cog",
    "bot.cogs.top_cog",
)





class EgoBot(commands.Bot):

    def __init__(self, settings: Settings) -> None:

        intents = discord.Intents.default()

        super().__init__(command_prefix="!", intents=intents)

        self.settings = settings

        self.db_pool: DatabasePool | None = None

        self.stats: StatsService | None = None

        self.cache_service: CacheService | None = None

        self.scheduler_service: SchedulerService | None = None



    async def setup_hook(self) -> None:

        self.db_pool = await DatabasePool.create(self.settings)

        await self.db_pool.ping()



        from bot.database.queries import bounds_queries



        await bounds_queries.ensure_seed(self.db_pool)



        from bot.services.cache_service import CacheService

        from bot.services.score_service import ScoreService

        from bot.services.stats_service import StatsService



        self.stats = StatsService(api_key=self.settings.henrik_api_key)

        await self.stats.__aenter__()

        self.cache_service = CacheService(

            self.db_pool,

            ScoreService(),

            self.stats,

            self.settings,

        )

        self.scheduler_service = SchedulerService(self)



        for cog in COGS:

            await self.load_extension(cog)



        guild = discord.Object(id=self.settings.discord_guild_id)

        self.tree.copy_global_to(guild=guild)

        synced = await self.tree.sync(guild=guild)

        logger.info("Synced %s slash command(s) to guild %s", len(synced), self.settings.discord_guild_id)



    async def on_ready(self) -> None:

        logger.info("Logged in as %s (id=%s)", self.user, self.user.id if self.user else "?")

        if self.scheduler_service is not None:

            self.scheduler_service.start()



    async def close(self) -> None:

        if self.scheduler_service is not None:

            self.scheduler_service.stop()

            self.scheduler_service = None

        if self.cache_service is not None:

            await self.cache_service.close()

            self.cache_service = None

            self.stats = None

        if self.db_pool is not None:

            await self.db_pool.close()

            self.db_pool = None

        await super().close()





async def main() -> None:

    settings = get_settings()

    setup_logging(settings)



    if not settings.henrik_api_key.strip():

        logger.error("HENRIK_API_KEY is required. Get a key at https://docs.henrikdev.xyz/")

        sys.exit(1)



    bot = EgoBot(settings)



    async with bot:

        logger.info("Starting Ego Score Bot...")

        await bot.start(settings.discord_token)





def run() -> None:

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        logger.info("Shutdown requested")

    except Exception:

        logger.exception("Fatal error")

        sys.exit(1)





if __name__ == "__main__":

    run()

