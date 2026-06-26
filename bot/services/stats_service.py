"""Valorant weekly stats via Henrik API."""

from __future__ import annotations

import aiohttp

from bot.services.henrik_service import fetch_stats_via_henrik
from bot.services.stats_types import StatsResult
from bot.services.stats_utils import current_week_bounds, parse_riot_id


class StatsService:
    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("HENRIK_API_KEY is required")
        self._session = session
        self._owns_session = session is None

    @property
    def http_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("StatsService is not initialized; use async with StatsService()")
        return self._session

    async def __aenter__(self) -> StatsService:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=120)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._owns_session = True
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    @staticmethod
    def parse_riot_id(riot_id: str) -> tuple[str, str]:
        return parse_riot_id(riot_id)

    @staticmethod
    def current_week_bounds(now=None):
        return current_week_bounds(now)

    async def fetch_stats(self, riot_id: str, *, allow_live: bool = False) -> StatsResult:
        if self._session is None:
            raise RuntimeError("StatsService is not initialized; use async with StatsService()")
        return await fetch_stats_via_henrik(
            self._session,
            riot_id,
            self.api_key,
            allow_live=allow_live,
        )

    async def fetch_stats_background(self, riot_id: str) -> StatsResult:
        if self._session is None:
            raise RuntimeError("StatsService is not initialized; use async with StatsService()")
        return await fetch_stats_via_henrik(
            self._session,
            riot_id,
            self.api_key,
            allow_live=True,
            skip_stored=True,
        )
