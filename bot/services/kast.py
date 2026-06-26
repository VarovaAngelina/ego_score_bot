"""KAST calculation (Tracker-style: Kill, Assist, Survive, Trade per round).

Tracker.gg uses per-round logs. Henrik stored matches only have totals — we estimate
distinct contributing rounds with event stacking (multi-kills / multi-assists per round).
"""

from __future__ import annotations

from typing import Any

TRADE_WINDOW_MS = 5000
# Average kill+assist events packed into one round (multi-frags, same-round assists).
KILL_EVENTS_PER_ROUND = 1.25
ASSIST_EVENTS_PER_ROUND = 2.5
TRADE_ASSIST_FACTOR = 0.45


def calculate_kast_from_match(match: dict[str, Any], puuid: str) -> float | None:
    """Exact KAST from roundResults when present (Riot/Henrik full match)."""
    rounds = (
        match.get("roundResults")
        or match.get("round_results")
        or match.get("rounds")
        or []
    )
    if not isinstance(rounds, list) or not rounds:
        return None

    contributed = 0
    for round_data in rounds:
        if not isinstance(round_data, dict):
            continue
        if _round_contributed(round_data, puuid):
            contributed += 1

    total = len(rounds)
    if total <= 0:
        return None
    return round(min(100.0, max(0.0, contributed / total * 100.0)), 1)


def _round_contributed(round_data: dict[str, Any], puuid: str) -> bool:
    player_stats = round_data.get("playerStats") or round_data.get("player_stats") or []
    if not isinstance(player_stats, list):
        return False

    player_round = next(
        (item for item in player_stats if isinstance(item, dict) and item.get("subject") == puuid),
        None,
    )
    if player_round is None:
        return False

    kills = player_round.get("kills") or []
    if not isinstance(kills, list):
        kills = []

    has_kill = any(
        isinstance(item, dict) and item.get("killer") == puuid
        for item in kills
    )
    has_assist = any(
        isinstance(item, dict) and puuid in (item.get("assistants") or [])
        for item in kills
    )

    died = any(
        isinstance(item, dict) and item.get("victim") == puuid
        for item in kills
    )
    has_survive = not died
    has_trade = _was_traded(kills, puuid)

    return has_kill or has_assist or has_survive or has_trade


def _was_traded(kills: list[Any], puuid: str) -> bool:
    for death in kills:
        if not isinstance(death, dict) or death.get("victim") != puuid:
            continue
        killer = death.get("killer")
        if not killer:
            continue
        death_time = _round_time_ms(death)
        for event in kills:
            if not isinstance(event, dict):
                continue
            if event.get("victim") != killer or event.get("killer") == puuid:
                continue
            trade_time = _round_time_ms(event)
            if 0 <= trade_time - death_time <= TRADE_WINDOW_MS:
                return True
    return False


def _round_time_ms(event: dict[str, Any]) -> int:
    raw = event.get("roundTime") or event.get("round_time") or 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def estimate_kast_from_totals(
    rounds: int,
    kills: float,
    deaths: float,
    assists: float,
) -> float:
    """Estimate KAST from aggregate match stats (Henrik stored v1).

    Round types are disjoint: survived (no death) vs death rounds.
    - Every survived round counts toward KAST.
    - A death round counts only with K/A on that round or a trade.
    Kills are split between round types before estimating death-round impact.
    """
    if rounds <= 0:
        return 0.0

    deaths = min(max(deaths, 0.0), float(rounds))
    kills = max(kills, 0.0)
    assists = max(assists, 0.0)
    survived = float(rounds) - deaths

    if deaths <= 0:
        return 100.0 if survived > 0 else 0.0

    survive_share = survived / float(rounds)
    kills_on_survive = min(survived * 1.5, kills * survive_share * 1.1)
    kills_on_death = max(0.0, min(kills - kills_on_survive, deaths * 1.5))

    ka_on_death = min(
        deaths,
        kills_on_death / KILL_EVENTS_PER_ROUND + assists / (ASSIST_EVENTS_PER_ROUND * 2),
    )

    naked_deaths = max(0.0, deaths - ka_on_death)
    traded = min(naked_deaths, assists * TRADE_ASSIST_FACTOR)
    death_contrib = ka_on_death + traded

    contributed = min(float(rounds), survived + death_contrib)
    return round(min(100.0, max(0.0, contributed / float(rounds) * 100.0)), 1)


def resolve_kast_percent(
    match: dict[str, Any],
    puuid: str,
    *,
    rounds: int,
    kills: float,
    deaths: float,
    assists: float,
    explicit: float | None = None,
) -> float:
    if explicit is not None and explicit > 0:
        return round(float(explicit), 1)

    from_rounds = calculate_kast_from_match(match, puuid)
    if from_rounds is not None:
        return from_rounds

    return estimate_kast_from_totals(rounds, kills, deaths, assists)
