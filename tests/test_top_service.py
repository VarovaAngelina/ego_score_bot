"""Top service week rollover and finalize."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import discord
import pytest

from bot.services.top_service import TopService


def _live_embed(week_label: str = "29 июня – 5 июля 2026") -> discord.Embed:
    return discord.Embed(title=f"🏆 Топ-10 сервера | {week_label}")


@pytest.mark.asyncio
async def test_week_rollover_finalizes_old_message_and_posts_new() -> None:
    bot = MagicMock()
    bot.settings.top_limit = 10
    bot.user.id = 1
    bot.db_pool = AsyncMock()

    old_message = AsyncMock(spec=discord.Message)
    old_message.id = 50
    old_message.author.id = 1
    old_message.embeds = [_live_embed()]

    new_message = AsyncMock(spec=discord.Message)
    new_message.id = 51

    channel = create_autospec(discord.TextChannel, instance=True)
    channel.id = 100
    channel.send = AsyncMock(return_value=new_message)
    channel.history = MagicMock(return_value=_async_iter([]))

    service = TopService(bot)

    with (
        patch.object(service, "_find_newest_top_message", AsyncMock(return_value=old_message)),
        patch.object(service, "_load_tracked_week", AsyncMock(return_value=date(2026, 6, 29))),
        patch.object(service, "_handle_week_rollover", AsyncMock(return_value=None)) as rollover,
        patch.object(service, "build_embed", AsyncMock(return_value=_live_embed("6–12 июля 2026"))),
        patch.object(service, "_remove_stale_top_messages", AsyncMock()),
        patch.object(service, "_save_tracked_week", AsyncMock()),
        patch("bot.services.top_service.config_queries.set", AsyncMock()),
        patch("bot.services.top_service.current_week_start", return_value=date(2026, 7, 6)),
    ):
        result = await service.update_live_top(channel=channel)

    rollover.assert_awaited_once()
    channel.send.assert_awaited_once()
    assert result is new_message


async def _async_iter(items):
    for item in items:
        yield item
