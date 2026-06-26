"""Ego Score calculation, normalization, stat_bounds integration."""

from __future__ import annotations

from dataclasses import dataclass

from bot.database.models import PlayerStats, ScoreResult, StatBound

STAT_ACS = "acs"
STAT_KD = "kd"
STAT_DD = "dd"
STAT_HS = "hs"
STAT_KAST = "kast"

ALL_STATS = (STAT_ACS, STAT_KD, STAT_DD, STAT_HS, STAT_KAST)


@dataclass(frozen=True, slots=True)
class Weights:
    acs: float = 0.30
    kd: float = 0.25
    dd: float = 0.20
    hs: float = 0.15
    kast: float = 0.10


FALLBACK_BOUNDS: dict[str, StatBound] = {
    STAT_ACS: StatBound(STAT_ACS, 50.0, 350.0),
    STAT_KD: StatBound(STAT_KD, 0.3, 3.0),
    STAT_DD: StatBound(STAT_DD, -80.0, 120.0),
    STAT_HS: StatBound(STAT_HS, 10.0, 45.0),
    STAT_KAST: StatBound(STAT_KAST, 30.0, 90.0),
}


class ScoreService:
    def __init__(self, weights: Weights | None = None) -> None:
        self.weights = weights or Weights()

    @staticmethod
    def normalize(value: float, min_val: float, max_val: float) -> float:
        if max_val == min_val:
            return 0.5
        return (value - min_val) / (max_val - min_val)

    @staticmethod
    def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    def resolve_bounds(self, stored: dict[str, StatBound] | None = None) -> dict[str, StatBound]:
        bounds = dict(FALLBACK_BOUNDS)
        if stored:
            bounds.update(stored)
        return bounds

    def expand_bounds(self, stats: PlayerStats, bounds: dict[str, StatBound]) -> dict[str, StatBound]:
        """Return bounds expanded to include the given stat values."""
        values = {
            STAT_ACS: stats.acs,
            STAT_KD: stats.kd_ratio,
            STAT_DD: stats.damage_delta,
            STAT_HS: stats.hs_percent,
            STAT_KAST: stats.kast_percent,
        }
        updated: dict[str, StatBound] = {}
        for name, value in values.items():
            bound = bounds[name]
            new_min = min(bound.min_val, value)
            new_max = max(bound.max_val, value)
            updated[name] = StatBound(name, new_min, new_max, bound.updated_at)
        return updated

    def calculate(self, stats: PlayerStats, bounds: dict[str, StatBound] | None = None) -> ScoreResult:
        resolved = self.resolve_bounds(bounds)

        norm_acs = self.normalize(stats.acs, resolved[STAT_ACS].min_val, resolved[STAT_ACS].max_val)
        norm_kd = self.normalize(stats.kd_ratio, resolved[STAT_KD].min_val, resolved[STAT_KD].max_val)
        norm_dd = self.normalize(stats.damage_delta, resolved[STAT_DD].min_val, resolved[STAT_DD].max_val)
        norm_hs = self.normalize(stats.hs_percent, resolved[STAT_HS].min_val, resolved[STAT_HS].max_val)
        norm_kast = self.normalize(
            stats.kast_percent,
            resolved[STAT_KAST].min_val,
            resolved[STAT_KAST].max_val,
        )

        w = self.weights
        raw = (
            w.acs * norm_acs
            + w.kd * norm_kd
            + w.dd * norm_dd
            + w.hs * norm_hs
            - w.kast * norm_kast
        )
        clipped = self.clip(raw)
        ego_score = round(clipped * 100, 1)

        return ScoreResult(
            ego_score=ego_score,
            contrib_acs=round(w.acs * norm_acs * 100, 1),
            contrib_kd=round(w.kd * norm_kd * 100, 1),
            contrib_dd=round(w.dd * norm_dd * 100, 1),
            contrib_hs=round(w.hs * norm_hs * 100, 1),
            contrib_kast=round(-w.kast * norm_kast * 100, 1),
        )

    def needs_bounds_update(self, stats: PlayerStats, bounds: dict[str, StatBound] | None = None) -> bool:
        resolved = self.resolve_bounds(bounds)
        expanded = self.expand_bounds(stats, resolved)
        return any(
            expanded[name].min_val != resolved[name].min_val
            or expanded[name].max_val != resolved[name].max_val
            for name in ALL_STATS
        )
