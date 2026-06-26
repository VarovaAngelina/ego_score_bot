"""Top service rank delta integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.top_service import TopService


@pytest.mark.asyncio
async def test_build_embed_refreshes_rank_deltas_before_load() -> None:
    bot = MagicMock()
    bot.settings.top_limit = 10
    bot.db_pool = AsyncMock()

    service = TopService(bot)

    with patch(
        "bot.services.top_service.refresh_rank_deltas",
        new=AsyncMock(),
    ) as refresh:
        with patch(
            "bot.services.top_service.cache_queries.get_top_for_week",
            new=AsyncMock(return_value=[]),
        ):
            with patch(
                "bot.services.top_service.cache_queries.count_scored_for_week",
                new=AsyncMock(return_value=0),
            ):
                with patch(
                    "bot.services.top_service.user_queries.count_all",
                    new=AsyncMock(return_value=0),
                ):
                    await service.build_embed()

    refresh.assert_awaited_once()
