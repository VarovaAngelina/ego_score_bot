"""Dataclasses for DB row mapping."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(slots=True)
class PlayerStats:
    acs: float
    kd_ratio: float
    damage_delta: float
    hs_percent: float
    kast_percent: float


@dataclass(slots=True)
class StatBound:
    stat_name: str
    min_val: float
    max_val: float
    updated_at: datetime | None = None


@dataclass(slots=True)
class ScoreResult:
    ego_score: float
    contrib_acs: float
    contrib_kd: float
    contrib_dd: float
    contrib_hs: float
    contrib_kast: float


@dataclass(slots=True)
class User:
    id: int
    discord_id: int
    riot_id: str
    registered_at: datetime


@dataclass(slots=True)
class PlayerCache:
    id: int
    user_id: int
    week_start: date
    stats: PlayerStats
    ego_score: float
    current_rank: str | None
    rank_delta: int
    result: ScoreResult
    fetched_at: datetime
    matches_played: int = 0
    is_stale: bool = False


@dataclass(slots=True)
class LeaderboardEntry:
    rank: int
    user_id: int
    riot_id: str
    current_rank: str | None
    ego_score: float
    rank_delta: int


@dataclass(slots=True)
class WeeklySnapshotRow:
    week_start: date
    week_end: date
    rank: int
    user_id: int
    riot_id: str
    current_rank: str | None
    ego_score: float
    stats: PlayerStats


@dataclass(slots=True)
class WeekSummary:
    week_start: date
    week_end: date
    player_count: int
