"""Shared scheduled refresh: update all registered players, then live top."""

from __future__ import annotations

import logging

logger = logging.getLogger("ego_score_bot.refresh")


async def refresh_all_and_update_top(bot) -> int:
    cache = getattr(bot, "cache_service", None)
    if cache is None:
        logger.warning("Refresh skipped: cache service unavailable")
        return 0

    refreshed = await cache.refresh_all_users()
    logger.info("Refreshed stats for %s registered user(s)", refreshed)

    if bot.settings.live_top_enabled:
        from bot.services.top_service import update_live_top

        await update_live_top(bot)

    return refreshed
