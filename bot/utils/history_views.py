"""Interactive views for /history: week picker and in-message leaderboard pagination."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bot.database.models import WeekSummary
from bot.database.queries import snapshot_queries
from bot.utils.formatters import (
    HISTORY_PAGE_SIZE,
    HISTORY_WEEKS_PER_PAGE,
    build_history_pages,
    build_history_picker_embed,
    format_week_range,
    history_picker_page_count,
    weeks_for_picker_page,
)

if TYPE_CHECKING:
    from bot.database.connection import DatabasePool

VIEW_TIMEOUT = 900


class HistoryWeekPickerView(discord.ui.View):
    """Week list with up to 10 select buttons per page; edits the same message."""

    def __init__(
        self,
        db: DatabasePool,
        weeks: list[WeekSummary],
        *,
        page: int = 0,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.db = db
        self.weeks = weeks
        self.page = page
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        chunk = weeks_for_picker_page(self.weeks, self.page)
        nav_row = 1 if len(chunk) <= 5 else 2

        for index, week in enumerate(chunk):
            label = format_week_range(week.week_start, week.week_end)
            if len(label) > 80:
                label = label[:77] + "…"
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                row=index // 5,
            )
            button.callback = self._make_week_callback(week)
            self.add_item(button)

        total_pages = history_picker_page_count(len(self.weeks))
        if self.page > 0:
            prev = discord.ui.Button(
                label="◀ Недели",
                style=discord.ButtonStyle.primary,
                row=nav_row,
            )
            prev.callback = self._prev_page
            self.add_item(prev)

        if self.page + 1 < total_pages:
            nxt = discord.ui.Button(
                label="Недели ▶",
                style=discord.ButtonStyle.primary,
                row=nav_row,
            )
            nxt.callback = self._next_page
            self.add_item(nxt)

    def _make_week_callback(self, week: WeekSummary):
        async def callback(interaction: discord.Interaction) -> None:
            await HistoryLeaderboardView.open_week(
                interaction,
                db=self.db,
                weeks=self.weeks,
                week=week,
                picker_page=self.page,
            )

        return callback

    async def _prev_page(self, interaction: discord.Interaction) -> None:
        self.page -= 1
        self._build_items()
        embed = build_history_picker_embed(self.weeks, page=self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _next_page(self, interaction: discord.Interaction) -> None:
        self.page += 1
        self._build_items()
        embed = build_history_picker_embed(self.weeks, page=self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class HistoryLeaderboardView(discord.ui.View):
    """Leaderboard pages for one week; optional back button to week picker."""

    def __init__(
        self,
        db: DatabasePool,
        weeks: list[WeekSummary],
        pages: list[discord.Embed],
        *,
        picker_page: int = 0,
        show_back: bool = True,
        current: int = 0,
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.db = db
        self.weeks = weeks
        self.pages = pages
        self.picker_page = picker_page
        self.show_back = show_back
        self.current = current
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        row = 0

        if len(self.pages) > 1:
            prev = discord.ui.Button(
                label="◀ Пред.",
                style=discord.ButtonStyle.secondary,
                row=row,
                disabled=self.current == 0,
            )
            prev.callback = self._prev_page
            self.add_item(prev)

            nxt = discord.ui.Button(
                label="▶ След.",
                style=discord.ButtonStyle.primary,
                row=row,
                disabled=self.current >= len(self.pages) - 1,
            )
            nxt.callback = self._next_page
            self.add_item(nxt)

        if self.show_back and self.weeks:
            back = discord.ui.Button(
                label="◀ К неделям",
                style=discord.ButtonStyle.secondary,
                row=row,
            )
            back.callback = self._back_to_weeks
            self.add_item(back)

    async def _prev_page(self, interaction: discord.Interaction) -> None:
        self.current -= 1
        self._build_items()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def _next_page(self, interaction: discord.Interaction) -> None:
        self.current += 1
        self._build_items()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def _back_to_weeks(self, interaction: discord.Interaction) -> None:
        embed = build_history_picker_embed(self.weeks, page=self.picker_page)
        view = HistoryWeekPickerView(self.db, self.weeks, page=self.picker_page)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @classmethod
    async def open_week(
        cls,
        interaction: discord.Interaction,
        *,
        db: DatabasePool,
        weeks: list[WeekSummary],
        week: WeekSummary,
        picker_page: int = 0,
        show_back: bool = True,
    ) -> None:
        week_label = format_week_range(week.week_start, week.week_end)
        entries = await snapshot_queries.get_all_for_week(db, week.week_start)
        pages = build_history_pages(entries, week_label=week_label, page_size=HISTORY_PAGE_SIZE)
        view = cls(
            db=db,
            weeks=weeks,
            pages=pages,
            picker_page=picker_page,
            show_back=show_back,
        )
        await interaction.response.edit_message(embed=pages[0], view=view)

    @classmethod
    def for_week(
        cls,
        *,
        db: DatabasePool,
        weeks: list[WeekSummary],
        pages: list[discord.Embed],
        picker_page: int = 0,
        show_back: bool = True,
    ) -> HistoryLeaderboardView:
        return cls(
            db=db,
            weeks=weeks,
            pages=pages,
            picker_page=picker_page,
            show_back=show_back,
        )


# Backward-compatible alias used in older imports/tests.
PaginationView = HistoryLeaderboardView
