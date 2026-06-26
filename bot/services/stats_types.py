"""Stats fetch result and errors."""

from __future__ import annotations

from dataclasses import dataclass

from bot.database.models import PlayerStats


@dataclass(slots=True)
class StatsResult:
    riot_id: str
    stats: PlayerStats
    current_rank: str | None
    matches_played: int


class StatsError(Exception):
    """Base stats error."""


class PlayerNotFoundError(StatsError):
    """Riot ID not found."""


class ProfilePrivateError(StatsError):
    """Riot account exists but match history is not accessible (privacy)."""


class StatsUnavailableError(StatsError):
    """Stats API blocked or unreachable."""


class StatsNotReadyError(StatsUnavailableError):
    """Stored cache has no weekly data yet; live fetch should run in background."""
