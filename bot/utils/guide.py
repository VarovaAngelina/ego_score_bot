"""Pinned guide and /help embed content."""

from __future__ import annotations

import discord

GUIDE_EMBED_TITLE = "Ego Score Bot — инструкция"


def build_guide_embed(*, top_limit: int = 10) -> discord.Embed:
    embed = discord.Embed(
        title=GUIDE_EMBED_TITLE,
        description=(
            "**Ego Score** — рейтинг твоей игры в Valorant за текущую неделю "
            "(пн 00:00 — вс 23:59 **МСК**).\n"
            "**Есть ранг** — считаются только матчи **Competitive** (рейтинговые).\n"
            "**Без ранга** — только **Swiftplay** (быстрые).\n"
            "Шкала **0–100**: чем выше, тем сильнее «эго-стата» за неделю."
        ),
        color=discord.Color.gold(),
    )

    embed.add_field(
        name="🚀 Быстрый старт",
        value=(
            "1. `/register Имя#TAG` — привязать Riot ID к Discord\n"
            "2. `/profile` — проверить ранг и score\n"
            "3. `/ego` — подробный разбор Ego Score"
        ),
        inline=False,
    )

    embed.add_field(
        name="📋 Команды",
        value=(
            "`/register` · привязка аккаунта\n"
            "`/unregister` · отвязка\n"
            "`/profile` · Riot ID, ранг, score\n"
            "`/ego` · твой score и вклад статистик\n"
            "`/ego player Имя#TAG` · score другого игрока бота\n"
            f"`/top` · топ-{top_limit} сервера за неделю\n"
            "`/history` · архив прошлых недель\n"
            "`/help` · справка"
        ),
        inline=False,
    )

    embed.add_field(
        name="📊 Из чего складывается score",
        value=(
            "**ACS** — +30%\n"
            "**K/D** — +25%\n"
            "**Damage Δ** — +20%\n"
            "**HS%** — +15%\n"
            "**KAST** — −10%"
        ),
        inline=True,
    )

    embed.add_field(
        name="ℹ️ Полезно знать",
        value=(
            "• `/ego` и `/history` видишь **только ты**\n"
            "• `/top` — общий рейтинг для всех\n"
            "• **↑ ↓** в топе — с прошлого обновления\n"
            "• С рангом — только **Competitive**, без ранга — **Swiftplay**\n"
            "• Данные обновляются **каждые 30 мин**\n"
            "• Воскресенье **23:59 МСК** — итоги недели в канал"
        ),
        inline=True,
    )

    embed.set_footer(text="Valorant Ego Score · неделя по МСК · ранг → Competitive · без ранга → Swiftplay")
    return embed
