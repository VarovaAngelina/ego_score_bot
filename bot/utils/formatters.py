"""Discord embed formatting."""

from __future__ import annotations

from datetime import date, datetime

import discord

from bot.config import MSK
from bot.utils.time_utils import as_msk, msk_now
from bot.database.models import LeaderboardEntry, User, WeekSummary
from bot.services.cache_service import BACKGROUND_LOADING_NOTE, PlayerCacheView
from bot.services.stats_utils import is_ranked_player
from bot.utils.progress_bar import STAT_MAX_CONTRIB, format_contrib_percent, render_progress_bar
from bot.utils.riot_privacy import RIOT_PRIVACY_STEPS


def format_msk_datetime(value: datetime) -> str:
    dt = as_msk(value)
    now = datetime.now(tz=MSK)
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%d.%m %H:%M")


def format_msk_date(value: datetime | date) -> str:
    if isinstance(value, datetime):
        value = as_msk(value).date()
    months = (
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    return f"{value.day} {months[value.month - 1]} {value.year}"


def format_week_range(week_start: date, week_end: date) -> str:
    if week_start.month == week_end.month:
        months = (
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря",
        )
        return f"{week_start.day}–{week_end.day} {months[week_start.month - 1]} {week_start.year}"
    return f"{format_msk_date(week_start)} – {format_msk_date(week_end)}"


LEADERBOARD_RIOT_COL_WIDTH = 16
LEADERBOARD_RANK_COL_WIDTH = 14
HISTORY_PAGE_SIZE = 20
HISTORY_WEEKS_PER_PAGE = 10
TOP_LIVE_TITLE_PREFIX = "🏆 Топ-"


def is_live_top_embed(embed: discord.Embed) -> bool:
    title = embed.title or ""
    return title.startswith(TOP_LIVE_TITLE_PREFIX) and "Итоги" not in title


def format_match_count(count: int) -> str:
    n = max(0, int(count))
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} матч"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return f"{n} матча"
    return f"{n} матчей"


def format_player_count(count: int) -> str:
    n = max(0, int(count))
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} игрок"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return f"{n} игрока"
    return f"{n} игроков"


def format_rank_label(rank: str | None) -> str:
    return rank or "Unranked"


def format_weekly_matches_hint(current_rank: str | None = None) -> str:
    if is_ranked_player(current_rank):
        return "Сыграй хотя бы один матч **Competitive** (рейтинговый)."
    if current_rank is not None:
        return "Сыграй хотя бы один матч **Swiftplay** (быстрый)."
    return (
        "С рангом — сыграй **Competitive**. "
        "Без ранга — **Swiftplay** (быстрые)."
    )


def format_rank_delta(rank_delta: int) -> str:
    if rank_delta > 0:
        return "  ↑"
    if rank_delta < 0:
        return "  ↓"
    return ""


def format_leaderboard_line(entry: LeaderboardEntry) -> str:
    rank_col = f"#{entry.rank}"
    riot = entry.riot_id
    if len(riot) > LEADERBOARD_RIOT_COL_WIDTH:
        riot = riot[: LEADERBOARD_RIOT_COL_WIDTH - 1] + "…"
    riot = riot.ljust(LEADERBOARD_RIOT_COL_WIDTH)
    rank_label = format_rank_label(entry.current_rank).ljust(LEADERBOARD_RANK_COL_WIDTH)
    score = f"{entry.ego_score:.1f}".rjust(5)
    return f"{rank_col:<4}{riot}  {rank_label}  {score}{format_rank_delta(entry.rank_delta)}"


def format_leaderboard_block(entries: list[LeaderboardEntry]) -> str:
    if not entries:
        return "Пока никого нет в рейтинге."
    return "\n".join(format_leaderboard_line(entry) for entry in entries)


def build_top_embed(
    entries: list[LeaderboardEntry],
    *,
    week_label: str,
    registered_count: int,
    updated_at: datetime | None,
    top_limit: int,
    scored_count: int | None = None,
) -> discord.Embed:
    title = f"{TOP_LIVE_TITLE_PREFIX}{top_limit} сервера | {week_label}"
    in_rating = scored_count if scored_count is not None else registered_count
    description = (
        f"Зарегистрировано: {registered_count} · в рейтинге: {in_rating}\n\n"
        f"```\n{format_leaderboard_block(entries)}\n```"
    )
    embed = discord.Embed(title=title, description=description, color=discord.Color.gold())
    footer_parts: list[str] = ["↑/↓ — изменение с прошлого обновления"]
    if updated_at is not None:
        footer_parts.insert(0, f"🕐 Обновлено: {format_msk_datetime(updated_at)} МСК")
    embed.set_footer(text=" · ".join(footer_parts))
    return embed


def build_announce_embed(
    entries: list[LeaderboardEntry],
    *,
    week_label: str,
    registered_count: int,
    top_limit: int,
    scored_count: int | None = None,
) -> discord.Embed:
    embed = build_top_embed(
        entries,
        week_label=week_label,
        registered_count=registered_count,
        scored_count=scored_count,
        updated_at=msk_now(),
        top_limit=top_limit,
    )
    embed.title = f"🏆 Итоги недели | {week_label}"
    if embed.footer is not None:
        embed.set_footer(text=embed.footer.text.replace("Обновлено", "Зафиксировано"))
    return embed


def history_player_total(entries: list[LeaderboardEntry]) -> int:
    """Players in the weekly archive (max rank, keeps gaps if a row was removed)."""
    if not entries:
        return 0
    return max(entry.rank for entry in entries)


def build_history_pages(
    entries: list[LeaderboardEntry],
    *,
    week_label: str,
    page_size: int = HISTORY_PAGE_SIZE,
) -> list[discord.Embed]:
    if not entries:
        embed = discord.Embed(
            title=f"📅 Итоги недели {week_label}",
            description="В этой неделе нет зафиксированных игроков.",
            color=discord.Color.blurple(),
        )
        return [embed]

    total = history_player_total(entries)
    pages: list[discord.Embed] = []
    for page_index in range(0, total, page_size):
        chunk = entries[page_index : page_index + page_size]
        page_num = page_index // page_size + 1
        page_count = (total + page_size - 1) // page_size
        description = (
            f"Страница {page_num} / {page_count} • Всего игроков: {total}\n\n"
            f"```\n{format_leaderboard_block(chunk)}\n```"
        )
        pages.append(
            discord.Embed(
                title=f"📅 Итоги недели {week_label}",
                description=description,
                color=discord.Color.blurple(),
            )
        )
    return pages


def history_picker_page_count(
    week_count: int,
    *,
    per_page: int = HISTORY_WEEKS_PER_PAGE,
) -> int:
    if week_count <= 0:
        return 0
    return (week_count + per_page - 1) // per_page


def weeks_for_picker_page(
    weeks: list[WeekSummary],
    page: int,
    *,
    per_page: int = HISTORY_WEEKS_PER_PAGE,
) -> list[WeekSummary]:
    start = page * per_page
    return weeks[start : start + per_page]


def build_history_picker_embed(
    weeks: list[WeekSummary],
    *,
    page: int = 0,
    per_page: int = HISTORY_WEEKS_PER_PAGE,
) -> discord.Embed:
    if not weeks:
        return build_history_list_embed([])

    total_pages = history_picker_page_count(len(weeks), per_page=per_page)
    page = max(0, min(page, total_pages - 1))
    chunk = weeks_for_picker_page(weeks, page, per_page=per_page)

    lines = [
        f"• {format_week_range(week.week_start, week.week_end)} ({format_player_count(week.player_count)})"
        for week in chunk
    ]
    description = "Выбери неделю кнопкой ниже:\n\n" + "\n".join(lines)
    if total_pages > 1:
        description += f"\n\nСтраница {page + 1} / {total_pages}"

    return discord.Embed(
        title="📋 История — выбор недели",
        description=description,
        color=discord.Color.blurple(),
    )


def build_history_list_embed(weeks: list[WeekSummary]) -> discord.Embed:
    embed = discord.Embed(
        title="📋 Доступные недели в истории:",
        color=discord.Color.blurple(),
    )
    if not weeks:
        embed.description = (
            "История пуста.\n"
            "Снепшоты создаются по воскресеньям в 23:59 МСК."
        )
        return embed

    lines = [
        f"• {format_week_range(week.week_start, week.week_end)}    ({format_player_count(week.player_count)})"
        for week in weeks
    ]
    embed.description = "\n".join(lines)
    return embed


def build_profile_embed(
    user: User,
    view: PlayerCacheView | None,
    *,
    week_label: str,
    error_note: str | None = None,
    current_rank: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"👤 Профиль — {user.riot_id}",
        color=discord.Color.blurple(),
    )

    if view is None:
        if error_note and (
            "private" in error_note.lower()
            or "match history is unavailable" in error_note.lower()
        ):
            embed.description = RIOT_PRIVACY_STEPS
        elif error_note and "not found" in error_note.lower():
            embed.description = (
                "Игрок **не найден**.\n"
                "Проверь Riot ID: имя, **тег** (например `EG0` vs `EGO`) и пробелы."
            )
        elif error_note == BACKGROUND_LOADING_NOTE:
            embed.description = (
                "Статистика загружается в фоне.\n"
                "Повтори `/profile` через 1–2 минуты."
            )
        elif error_note and ("timeout" in error_note.lower() or "не ответил" in error_note.lower()):
            embed.description = (
                "Сервис статистики не успел ответить за отведённое время.\n"
                "Повтори `/profile` через минуту."
            )
        elif error_note and "no matches" in error_note.lower():
            embed.description = (
                "Профиль открыт, но **нет подходящих матчей за текущую неделю** (пн–вс МСК).\n"
                f"{format_weekly_matches_hint(current_rank)}"
            )
        elif error_note and ("429" in error_note or "rate limit" in error_note.lower()):
            embed.description = (
                "Сервис статистики временно ограничил запросы.\n"
                "Повтори `/profile` через минуту."
            )
        else:
            embed.description = (
                "Аккаунт привязан, но **нет данных за текущую неделю**.\n"
                f"{format_weekly_matches_hint(current_rank)} "
                "Или дождись обновления кэша."
            )
        embed.add_field(name="Riot ID", value=user.riot_id, inline=False)
        embed.add_field(name="Registered", value=format_msk_date(user.registered_at), inline=False)
        return embed

    cache = view.cache
    rank = cache.current_rank or "Unranked"
    stale_note = ""
    if view.stats_unavailable:
        stale_note = f"\n⚠ данные от {format_msk_datetime(cache.fetched_at)} МСК"
    elif view.served_from_cache and not cache.is_stale:
        stale_note = f"\n🕐 Обновлено: {format_msk_datetime(cache.fetched_at)} МСК"

    if cache.matches_played <= 0:
        embed.description = (
            f"**Riot ID:** {user.riot_id}\n"
            f"**Rank:** {rank}\n\n"
            "Нет подходящих матчей за текущую неделю (пн–вс МСК).\n"
            f"{format_weekly_matches_hint(cache.current_rank)}"
            f"{stale_note}"
        )
        embed.add_field(name="Registered", value=format_msk_date(user.registered_at), inline=False)
        return embed

    embed.description = (
        f"**Riot ID:** {user.riot_id}\n"
        f"**Rank:** {rank}\n"
        f"**Ego Score:** {cache.ego_score:.1f} / 100  ({week_label})\n"
        f"**Registered:** {format_msk_date(user.registered_at)}"
        f"{stale_note}"
    )
    return embed


def _format_damage_delta(value: float) -> str:
    if value >= 0:
        return f"+{value:.1f}"
    return f"{value:.1f}"


def format_ego_score_block(score: float) -> str:
    """Large score with smaller / 100 on the next line (Discord -# subtext)."""
    return f"# **{score:.1f}**\n-# / 100"


def build_stat_contrib_lines(view: PlayerCacheView) -> str:
    cache = view.cache
    stats = cache.stats
    result = cache.result
    rows = (
        ("ACS", f"{stats.acs:.1f}", result.contrib_acs, STAT_MAX_CONTRIB["acs"]),
        ("K/D", f"{stats.kd_ratio:.2f}", result.contrib_kd, STAT_MAX_CONTRIB["kd"]),
        ("Dmg Δ", _format_damage_delta(stats.damage_delta), result.contrib_dd, STAT_MAX_CONTRIB["dd"]),
        ("HS%", f"{stats.hs_percent:.1f}%", result.contrib_hs, STAT_MAX_CONTRIB["hs"]),
        ("KAST", f"{stats.kast_percent:.1f}%", result.contrib_kast, STAT_MAX_CONTRIB["kast"]),
    )
    lines: list[str] = []
    for label, stat_display, contrib, max_contrib in rows:
        bar = render_progress_bar(abs(contrib), max_contrib)
        left = f"{label} ({stat_display})"
        lines.append(f"{left:<16}{bar}  {format_contrib_percent(contrib)}")
    return "\n".join(lines)


def format_weekly_top_place(rank: int | None, scored_count: int) -> str:
    if rank is None or rank <= 0:
        return "не в топе"
    return f"#{rank} из {scored_count}"


def build_ego_embed(
    view: PlayerCacheView,
    *,
    week_label: str,
    week_rank: int | None = None,
    scored_count: int = 0,
) -> discord.Embed:
    user = view.user
    cache = view.cache
    rank = cache.current_rank or "Unranked"

    if cache.matches_played <= 0:
        return build_ego_error_embed(
            user,
            week_label=week_label,
            error_note="No matches for current week",
            current_rank=cache.current_rank,
        )

    embed = discord.Embed(
        title=f"🎯 Ego Score — {user.riot_id}",
        color=discord.Color.gold(),
    )
    embed.description = (
        f"**Rank:** {rank} · **Неделя:** {week_label} · "
        f"**Матчи:** {format_match_count(cache.matches_played)}\n"
        f"**Место в топе:** {format_weekly_top_place(week_rank, scored_count)}\n"
        f"{format_ego_score_block(cache.ego_score)}"
    )
    embed.add_field(
        name="Вклад статистик",
        value=f"```\n{build_stat_contrib_lines(view)}\n```",
        inline=False,
    )

    if view.stats_unavailable:
        embed.set_footer(text=f"⚠ Данные от {format_msk_datetime(cache.fetched_at)} МСК")
    else:
        embed.set_footer(text=f"🕐 Обновлено: {format_msk_datetime(cache.fetched_at)} МСК")

    return embed


def build_ego_error_embed(
    user: User,
    *,
    week_label: str,
    error_note: str | None = None,
    current_rank: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=f"🎯 Ego Score — {user.riot_id}",
        color=discord.Color.orange(),
    )

    if error_note and (
        "private" in error_note.lower()
        or "match history is unavailable" in error_note.lower()
    ):
        embed.description = RIOT_PRIVACY_STEPS
    elif error_note == BACKGROUND_LOADING_NOTE:
        embed.description = (
            "⏳ Статистика загружается.\n"
            "Повтори `/ego` через 1–2 минуты."
        )
    elif error_note and "no matches" in error_note.lower():
        embed.description = (
            f"**Неделя:** {week_label}\n\n"
            "Нет подходящих матчей за текущую неделю (пн–вс МСК).\n"
            f"{format_weekly_matches_hint(current_rank)}"
        )
    elif error_note and ("timeout" in error_note.lower() or "не ответил" in error_note.lower()):
        embed.description = (
            "⏳ Сервис статистики не успел ответить.\n"
            "Повтори `/ego` через минуту."
        )
    elif error_note and ("429" in error_note or "rate limit" in error_note.lower()):
        embed.description = (
            "Сервис статистики временно ограничил запросы.\n"
            "Повтори `/ego` через минуту."
        )
    else:
        embed.description = (
            f"**Неделя:** {week_label}\n\n"
            "Нет данных за текущую неделю.\n"
            f"{format_weekly_matches_hint(current_rank)} "
            "Или дождись обновления кэша."
        )

    return embed
