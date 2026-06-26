"""Shared helpers for match aggregation and week boundaries."""

from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta

from bot.config import MSK
from bot.database.models import PlayerStats
from bot.services.stats_types import StatsError

COMPETITIVE_MODE = "Competitive"
SWIFTPLAY_MODE = "Swiftplay"

STAT_ALIASES: dict[str, tuple[str, ...]] = {
    "acs": ("scorePerRound", "scorePerRoundAvg", "averageCombatScore", "acs"),
    "kills": ("kills",),
    "deaths": ("deaths",),
    "damage": ("damage", "damageDealt"),
    "damage_received": ("damageReceived",),
    "headshots": ("headshots",),
    "shots": ("shotsFired", "shots", "bodyshots", "legshots"),
    "kast": ("kAST", "kast", "kastPercentage"),
    "kd": ("kDRatio", "kdRatio", "killDeathRatio"),
    "damage_delta": ("damageDeltaPerRound", "damagePerRoundDelta", "damageDelta"),
    "hs_percent": ("headshotPct", "headshotsPercentage", "headshotPercentage"),
}


def parse_riot_id(riot_id: str) -> tuple[str, str]:
    cleaned = riot_id.strip()
    if "#" not in cleaned:
        raise StatsError("Riot ID must be in Name#TAG format")
    name, tag = cleaned.split("#", 1)
    name, tag = name.strip(), tag.strip()
    if not name or not tag:
        raise StatsError("Riot ID must be in Name#TAG format")
    return name, tag


def current_week_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(tz=MSK)
    monday = now.date() - timedelta(days=now.weekday())
    week_start = datetime.combine(monday, dt_time.min, tzinfo=MSK)
    week_end = datetime.combine(monday + timedelta(days=6), dt_time(23, 59, 59), tzinfo=MSK)
    return week_start, week_end


def stat_value(stats: dict, *keys: str) -> float | None:
    for key in keys:
        raw = stats.get(key)
        if raw is None:
            continue
        if isinstance(raw, dict):
            if raw.get("value") is not None:
                return float(raw["value"])
            if raw.get("displayValue") is not None:
                return parse_number(str(raw["displayValue"]))
        elif isinstance(raw, (int, float)):
            return float(raw)
        elif isinstance(raw, str):
            parsed = parse_number(raw)
            if parsed is not None:
                return parsed
    return None


def parse_number(value: str) -> float | None:
    cleaned = value.strip().replace(",", "").replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def match_timestamp(match: dict) -> datetime | None:
    metadata = match.get("metadata") or match.get("meta") or match
    for key in ("timestamp", "started_at", "startedAt", "date", "time", "game_start", "gameStart"):
        raw = metadata.get(key)
        if not raw:
            continue
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=MSK)
        if isinstance(raw, str):
            normalized = raw.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(normalized)
                return dt.astimezone(MSK) if dt.tzinfo else dt.replace(tzinfo=MSK)
            except ValueError:
                continue
    return None


def match_id(match: dict) -> str | None:
    for container in (match.get("meta"), match.get("metadata"), match):
        if not isinstance(container, dict):
            continue
        raw = container.get("id") or container.get("match_id") or container.get("matchid")
        if raw:
            return str(raw)
    return None


def match_mode(match: dict) -> str | None:
    for container in (match.get("meta"), match.get("metadata"), match):
        if not isinstance(container, dict):
            continue
        mode = container.get("mode") or container.get("queue") or container.get("match_type")
        if mode is not None:
            return str(mode).strip()
    return None


def is_mode_match(match: dict, mode: str) -> bool:
    current = match_mode(match)
    if current is None:
        return False
    return current.lower() == mode.lower()


def is_competitive_match(match: dict) -> bool:
    return is_mode_match(match, COMPETITIVE_MODE)


def is_swiftplay_match(match: dict) -> bool:
    return is_mode_match(match, SWIFTPLAY_MODE)


def filter_competitive_matches(matches: list[dict]) -> list[dict]:
    return [match for match in matches if is_competitive_match(match)]


def filter_swiftplay_matches(matches: list[dict]) -> list[dict]:
    return [match for match in matches if is_swiftplay_match(match)]


def is_ranked_player(current_rank: str | None) -> bool:
    """True when the account has a competitive rank (not Unranked)."""
    if not current_rank:
        return False
    normalized = current_rank.strip().lower()
    return normalized not in {"unranked", "0", "none"}


def prepare_weekly_scored_matches(matches: list[dict], *, ranked: bool) -> list[dict]:
    """Ranked accounts: Competitive only. Unranked: Swiftplay only."""
    deduped = dedupe_matches(matches)
    if ranked:
        return filter_competitive_matches(deduped)
    return filter_swiftplay_matches(deduped)


def dedupe_matches(matches: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for match in matches:
        mid = match_id(match)
        if mid and mid in seen:
            continue
        if mid:
            seen.add(mid)
        unique.append(match)
    return unique


def filter_matches_by_week(
    matches: list[dict],
    week_start: datetime,
    week_end: datetime,
) -> list[dict]:
    result: list[dict] = []
    for match in matches:
        ts = match_timestamp(match)
        if ts is None:
            continue
        if week_start <= ts <= week_end:
            result.append(match)
    return result


def match_rounds(match: dict) -> int:
    metadata = match.get("metadata") or match.get("meta") or {}
    for key in ("rounds_played", "rounds", "roundsPlayed"):
        raw = metadata.get(key) or (match.get("stats") or {}).get(key)
        if raw is not None:
            try:
                rounds = int(raw)
                if rounds > 0:
                    return rounds
            except (TypeError, ValueError):
                continue
    return 1


def _match_hs_percent(stats: dict) -> float | None:
    hs = stat_value(stats, *STAT_ALIASES["hs_percent"])
    if hs is not None:
        return hs
    headshots = stat_value(stats, *STAT_ALIASES["headshots"])
    shots = stat_value(stats, *STAT_ALIASES["shots"])
    if headshots is not None and shots and shots > 0:
        return headshots / shots * 100.0
    return None


def aggregate_match_stats(matches: list[dict]) -> PlayerStats:
    """Aggregate weekly stats using tracker.gg-style weighting.

    - ACS and DDΔ: weighted by rounds played
    - HS% and KAST: simple average across matches
    - K/D: total kills / total deaths
    """
    total_kills = 0.0
    total_deaths = 0.0
    total_rounds = 0
    weighted_acs = 0.0
    weighted_dd = 0.0
    hs_values: list[float] = []
    kast_values: list[float] = []

    for match in matches:
        stats = match.get("stats") or match.get("segments", [{}])[0].get("stats") or {}
        rounds = match_rounds(match)

        acs = stat_value(stats, *STAT_ALIASES["acs"])
        if acs is not None:
            weighted_acs += acs * rounds
            total_rounds += rounds

        kd = stat_value(stats, *STAT_ALIASES["kd"])
        kills = stat_value(stats, *STAT_ALIASES["kills"])
        deaths = stat_value(stats, *STAT_ALIASES["deaths"])
        if kills is not None:
            total_kills += kills
        if deaths is not None:
            total_deaths += deaths
        elif kd is not None and kills is not None and kd > 0:
            total_deaths += kills / kd

        damage_delta = stat_value(stats, *STAT_ALIASES["damage_delta"])
        if damage_delta is not None:
            weighted_dd += damage_delta * rounds
        else:
            damage = stat_value(stats, *STAT_ALIASES["damage"])
            damage_received = stat_value(stats, *STAT_ALIASES["damage_received"])
            if damage is not None and damage_received is not None and rounds > 0:
                weighted_dd += (damage - damage_received) / rounds * rounds

        hs = _match_hs_percent(stats)
        if hs is not None:
            hs_values.append(hs)

        kast = stat_value(stats, *STAT_ALIASES["kast"])
        if kast is not None:
            kast_values.append(kast)

    if total_rounds == 0 and total_kills == 0:
        raise StatsError("Could not aggregate match stats")

    acs_avg = weighted_acs / total_rounds if total_rounds > 0 else 0.0
    kd_ratio = total_kills / total_deaths if total_deaths > 0 else total_kills
    damage_delta_avg = weighted_dd / total_rounds if total_rounds > 0 else 0.0
    hs_percent = sum(hs_values) / len(hs_values) if hs_values else 0.0
    kast_percent = sum(kast_values) / len(kast_values) if kast_values else 0.0

    return PlayerStats(
        acs=round(acs_avg, 1),
        kd_ratio=round(kd_ratio, 2),
        damage_delta=round(damage_delta_avg, 1),
        hs_percent=round(hs_percent, 1),
        kast_percent=round(kast_percent, 1),
    )
