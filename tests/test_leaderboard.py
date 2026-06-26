"""Leaderboard formatter and pagination tests."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import discord

from bot.config import MSK
from bot.database.models import LeaderboardEntry, WeekSummary
from bot.utils.formatters import (
    build_announce_embed,
    build_history_list_embed,
    build_history_pages,
    build_history_picker_embed,
    build_top_embed,
    format_leaderboard_line,
    format_player_count,
    format_rank_delta,
    history_picker_page_count,
    weeks_for_picker_page,
)
from bot.utils.history_views import HistoryLeaderboardView
from bot.utils.pagination import PaginationView
from bot.utils.time_utils import parse_week_argument


def test_format_rank_delta() -> None:
    assert format_rank_delta(2) == "  ↑"
    assert format_rank_delta(-1) == "  ↓"
    assert format_rank_delta(0) == ""


def test_format_leaderboard_line() -> None:
    entry = LeaderboardEntry(
        rank=1,
        user_id=1,
        riot_id="TenZ#NA1",
        current_rank="Radiant",
        ego_score=78.5,
        rank_delta=1,
    )
    line = format_leaderboard_line(entry)
    assert line.startswith("#1  ")
    assert "TenZ#NA1" in line
    assert "Radiant" in line
    assert "[" not in line.split("TenZ#NA1")[1].split("78.5")[0]
    assert "78.5" in line
    assert line.endswith("↑")


def test_format_player_count() -> None:
    assert format_player_count(1) == "1 игрок"
    assert format_player_count(3) == "3 игрока"
    assert format_player_count(31) == "31 игрок"


def test_build_top_embed() -> None:
    entries = [
        LeaderboardEntry(
            rank=1,
            user_id=1,
            riot_id="TenZ#NA1",
            current_rank="Radiant",
            ego_score=78.5,
            rank_delta=0,
        )
    ]
    embed = build_top_embed(
        entries,
        week_label="16–22 июня 2026",
        registered_count=47,
        scored_count=12,
        updated_at=datetime(2026, 6, 24, 14, 35, tzinfo=MSK),
        top_limit=10,
    )
    assert embed.title == "🏆 Топ-10 сервера | 16–22 июня 2026"
    assert "Зарегистрировано: 47" in embed.description
    assert "в рейтинге: 12" in embed.description
    assert "TenZ#NA1" in embed.description
    assert embed.footer is not None
    assert "14:35" in embed.footer.text
    assert "↑/↓" in embed.footer.text


def test_build_announce_embed() -> None:
    entries = [
        LeaderboardEntry(
            rank=1,
            user_id=1,
            riot_id="TenZ#NA1",
            current_rank="Radiant",
            ego_score=78.5,
            rank_delta=0,
        )
    ]
    embed = build_announce_embed(
        entries,
        week_label="22–28 июня 2026",
        registered_count=47,
        top_limit=10,
    )
    assert embed.title == "🏆 Итоги недели | 22–28 июня 2026"
    assert embed.footer is not None
    assert "Зафиксировано" in embed.footer.text


def test_build_history_pages_single_page() -> None:
    entries = [
        LeaderboardEntry(
            rank=index,
            user_id=index,
            riot_id=f"Player{index:02d}#TST",
            current_rank="Gold 1",
            ego_score=50.0 + index,
            rank_delta=0,
        )
        for index in range(1, 6)
    ]
    pages = build_history_pages(entries, week_label="9–15 июня 2026")
    assert len(pages) == 1
    assert "Страница 1 / 1" in pages[0].description
    assert "Player01#TST" in pages[0].description


def test_build_history_pages_multiple_pages() -> None:
    entries = [
        LeaderboardEntry(
            rank=index,
            user_id=index,
            riot_id=f"Player{index:03d}#TST",
            current_rank="Silver 1",
            ego_score=40.0,
            rank_delta=0,
        )
        for index in range(1, 22)
    ]
    pages = build_history_pages(entries, week_label="9–15 июня 2026", page_size=20)
    assert len(pages) == 2
    assert "Страница 1 / 2" in pages[0].description
    assert "Страница 2 / 2" in pages[1].description
    assert "Player001#TST" in pages[0].description
    assert "Player021#TST" in pages[1].description


def test_build_history_list_embed_empty() -> None:
    embed = build_history_list_embed([])
    assert "История пуста" in embed.description


def test_build_history_list_embed_weeks() -> None:
    weeks = [
        WeekSummary(
            week_start=date(2026, 6, 9),
            week_end=date(2026, 6, 15),
            player_count=31,
        )
    ]
    embed = build_history_list_embed(weeks)
    assert "9–15 июня 2026" in embed.description
    assert "31 игрок" in embed.description


def test_history_picker_embed_pagination() -> None:
    weeks = [
        WeekSummary(
            week_start=date(2026, 6, 22) - timedelta(weeks=index),
            week_end=date(2026, 6, 28) - timedelta(weeks=index),
            player_count=35,
        )
        for index in range(12)
    ]
    assert history_picker_page_count(len(weeks)) == 2
    assert len(weeks_for_picker_page(weeks, 0)) == 10
    assert len(weeks_for_picker_page(weeks, 1)) == 2

    page_one = build_history_picker_embed(weeks, page=0)
    assert "Страница 1 / 2" in page_one.description
    assert "Выбери неделю" in page_one.description

    page_two = build_history_picker_embed(weeks, page=1)
    assert "Страница 2 / 2" in page_two.description


def test_parse_week_argument() -> None:
    assert parse_week_argument("2026-06-08") == date(2026, 6, 8)
    assert parse_week_argument("2026-06-11") == date(2026, 6, 8)


def test_pagination_view_button_states() -> None:
    pages = [
        discord.Embed(title="Page 1"),
        discord.Embed(title="Page 2"),
    ]
    view = HistoryLeaderboardView(
        db=MagicMock(),
        weeks=[],
        pages=pages,
        show_back=False,
        current=0,
    )
    buttons = [item for item in view.children if isinstance(item, discord.ui.Button)]
    prev = next(btn for btn in buttons if btn.label == "◀ Пред.")
    nxt = next(btn for btn in buttons if btn.label == "▶ След.")
    assert prev.disabled is True
    assert nxt.disabled is False

    view.current = 1
    view._build_items()
    buttons = [item for item in view.children if isinstance(item, discord.ui.Button)]
    prev = next(btn for btn in buttons if btn.label == "◀ Пред.")
    nxt = next(btn for btn in buttons if btn.label == "▶ След.")
    assert prev.disabled is False
    assert nxt.disabled is True


def test_pagination_view_alias() -> None:
    assert PaginationView is HistoryLeaderboardView
