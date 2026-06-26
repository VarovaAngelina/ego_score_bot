"""Valorant stats via HenrikDev unofficial API (recommended for bots)."""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
import aiohttp
from bot.services.kast import resolve_kast_percent, estimate_kast_from_totals
from bot.database.models import PlayerStats
from bot.services.stats_types import (
    PlayerNotFoundError,
    ProfilePrivateError,
    StatsError,
    StatsResult,
    StatsUnavailableError,
)
from bot.services.stats_utils import (
    aggregate_match_stats,
    current_week_bounds,
    is_ranked_player,
    match_timestamp,
    parse_riot_id,
    prepare_weekly_scored_matches,
)
logger = logging.getLogger("ego_score_bot.henrik")
HENRIK_BASE = "https://api.henrikdev.xyz"
PLATFORM = "pc"
MATCH_PAGE_SIZE = 10
STORED_MAX_PAGES = 2
STORED_TIMEOUT = 12.0
LIVE_TIMEOUT_BACKGROUND = 120.0
ACCOUNT_TIMEOUT = 15.0
@dataclass(slots=True)
class HenrikAccount:
    puuid: str
    region: str
    name: str
    tag: str
async def verify_riot_account_access(
    session: aiohttp.ClientSession,
    riot_id: str,
    api_key: str,
) -> HenrikAccount:
    """Fast register check: account exists on Riot/Henrik (matches load on /profile)."""
    return await _fetch_account(session, riot_id, api_key)
async def fetch_stats_via_henrik(
    session: aiohttp.ClientSession,
    riot_id: str,
    api_key: str,
    *,
    allow_live: bool = False,
    skip_stored: bool = False,
) -> StatsResult:
    account = await _fetch_account(session, riot_id, api_key)
    rank_task = asyncio.create_task(_fetch_rank(session, account, api_key))
    raw_matches = await _fetch_weekly_matches_raw(
        session,
        account,
        api_key,
        allow_live=allow_live,
        skip_stored=skip_stored,
    )
    rank = await rank_task
    raw_matches = _prepare_weekly_matches(raw_matches, rank)
    normalized = [_normalize_henrik_match(item, account.puuid) for item in raw_matches]
    if not normalized:
        return StatsResult(
            riot_id=riot_id,
            stats=PlayerStats(0.0, 0.0, 0.0, 0.0, 0.0),
            current_rank=rank,
            matches_played=0,
        )
    stats = aggregate_match_stats(normalized)
    return StatsResult(
        riot_id=riot_id,
        stats=stats,
        current_rank=rank,
        matches_played=len(normalized),
    )
async def _fetch_account(
    session: aiohttp.ClientSession,
    riot_id: str,
    api_key: str,
) -> HenrikAccount:
    name, tag = parse_riot_id(riot_id)
    data = await _henrik_get(
        session,
        f"/valorant/v2/account/{quote(name)}/{quote(tag)}",
        api_key,
        timeout=ACCOUNT_TIMEOUT,
    )
    if data is None:
        raise PlayerNotFoundError(f"Player not found: {riot_id}")
    region = (data.get("region") or "").lower()
    puuid = data.get("puuid") or ""
    if not region or not puuid:
        raise StatsError("Henrik account response missing region or puuid")
    return HenrikAccount(
        puuid=puuid,
        region=region,
        name=str(data.get("name") or name),
        tag=str(data.get("tag") or tag),
    )
async def _fetch_weekly_matches_raw(
    session: aiohttp.ClientSession,
    account: HenrikAccount,
    api_key: str,
    *,
    allow_live: bool,
    skip_stored: bool = False,
) -> list[dict[str, Any]]:
    """Stored Henrik DB first (~1-3s). Live v4 only in background (30-120s+ on Riot cache miss)."""
    week_start, week_end = current_week_bounds()
    week_start_ts = int(week_start.timestamp())
    week_end_ts = int(week_end.timestamp())
    if not skip_stored:
        weekly = await _fetch_stored_weekly(
            session,
            account,
            api_key,
            week_start_ts,
            week_end_ts,
        )
        if weekly:
            logger.info("Stored matches: %s match(es) this week", len(weekly))
            return weekly
    if not allow_live:
        logger.info(
            "Stored scan: no weekly matches for %s#%s — skipping live fetch",
            account.name,
            account.tag,
        )
        return []
    logger.info(
        "Live v4 for %s#%s (up to %.0fs; Riot cache miss can be slow)",
        account.name,
        account.tag,
        LIVE_TIMEOUT_BACKGROUND,
    )
    return await _fetch_live_weekly_v4(
        session,
        account,
        api_key,
        week_start_ts,
        week_end_ts,
        timeout=LIVE_TIMEOUT_BACKGROUND,
    )
async def _fetch_stored_weekly(
    session: aiohttp.ClientSession,
    account: HenrikAccount,
    api_key: str,
    week_start_ts: int,
    week_end_ts: int,
) -> list[dict[str, Any]]:
    weekly = await _paginate_stored_weekly(
        session,
        account,
        api_key,
        week_start_ts,
        week_end_ts,
    )
    if not weekly:
        logger.info(
            "Stored scan: no matches this week for %s#%s in Henrik DB",
            account.name,
            account.tag,
        )
    return weekly
async def _paginate_stored_weekly(
    session: aiohttp.ClientSession,
    account: HenrikAccount,
    api_key: str,
    week_start_ts: int,
    week_end_ts: int,
) -> list[dict[str, Any]]:
    weekly: list[dict[str, Any]] = []
    for page in range(1, STORED_MAX_PAGES + 1):
        batch = await _fetch_stored_page(session, account, api_key, page=page)
        if not batch:
            break
        page_weekly, stop = _split_batch_by_week(batch, week_start_ts, week_end_ts)
        weekly.extend(page_weekly)
        if stop or len(batch) < MATCH_PAGE_SIZE:
            break
    return weekly
def _prepare_weekly_matches(
    matches: list[dict[str, Any]],
    current_rank: str | None,
) -> list[dict[str, Any]]:
    """Current week scored matches: Competitive if ranked, Swiftplay if not."""
    return prepare_weekly_scored_matches(matches, ranked=is_ranked_player(current_rank))
async def _fetch_live_weekly_v4(
    session: aiohttp.ClientSession,
    account: HenrikAccount,
    api_key: str,
    week_start_ts: int,
    week_end_ts: int,
    *,
    timeout: float,
) -> list[dict[str, Any]]:
    try:
        batch = await _fetch_live_v4_page(session, account, api_key, start=0, timeout=timeout)
    except StatsError as exc:
        logger.warning("Live v4 failed: %s", exc)
        raise
    if not batch:
        return []
    weekly, _ = _split_batch_by_week(batch, week_start_ts, week_end_ts)
    return weekly
async def _fetch_stored_page(
    session: aiohttp.ClientSession,
    account: HenrikAccount,
    api_key: str,
    *,
    page: int,
) -> list[dict[str, Any]]:
    path = f"/valorant/v1/by-puuid/stored-matches/{account.region}/{account.puuid}"
    params = {"size": str(MATCH_PAGE_SIZE), "page": str(page)}
    data = await _henrik_get(session, path, api_key, params=params, timeout=STORED_TIMEOUT)
    return _coerce_match_list(data)
async def _fetch_live_v4_page(
    session: aiohttp.ClientSession,
    account: HenrikAccount,
    api_key: str,
    *,
    start: int,
    timeout: float,
) -> list[dict[str, Any]]:
    path = f"/valorant/v4/by-puuid/matches/{account.region}/{PLATFORM}/{account.puuid}"
    params = {"size": str(MATCH_PAGE_SIZE), "start": str(start)}
    data = await _henrik_get(session, path, api_key, params=params, timeout=timeout)
    if data is None:
        raise ProfilePrivateError(
            "Riot profile is private or match history is unavailable"
        )
    return _coerce_match_list(data)
def _coerce_match_list(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    return []
def _raw_match_game_start(match: dict[str, Any]) -> int | None:
    dt = match_timestamp(match)
    if dt is not None:
        return int(dt.timestamp())
    for key in ("game_start", "gameStart"):
        raw = match.get(key)
        if isinstance(raw, (int, float)):
            return int(raw)
    return None
def _split_batch_by_week(
    batch: list[dict[str, Any]],
    week_start_ts: int,
    week_end_ts: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Split newest-first batch into current-week matches; stop when week boundary passed."""
    weekly: list[dict[str, Any]] = []
    for match in batch:
        ts = _raw_match_game_start(match)
        if ts is None:
            continue
        if ts < week_start_ts:
            return weekly, True
        if ts <= week_end_ts:
            weekly.append(match)
    return weekly, False
async def _fetch_rank(
    session: aiohttp.ClientSession,
    account: HenrikAccount,
    api_key: str,
) -> str | None:
    mmr = await _henrik_get(
        session,
        f"/valorant/v2/by-puuid/mmr/{account.region}/{account.puuid}",
        api_key,
        timeout=ACCOUNT_TIMEOUT,
    )
    if not mmr:
        return None
    current = mmr.get("current_data") or mmr.get("current") or {}
    tier = current.get("currenttierpatched") or current.get("currenttier_patched")
    if tier:
        return str(tier)
    tier_id = current.get("currenttier")
    return str(tier_id) if tier_id is not None else None
async def _henrik_get(
    session: aiohttp.ClientSession,
    path: str,
    api_key: str,
    *,
    params: dict[str, str] | None = None,
    timeout: float | None = None,
) -> Any:
    try:
        if timeout is not None:
            return await asyncio.wait_for(
                _henrik_get_once(session, path, api_key, params=params),
                timeout=timeout,
            )
        return await _henrik_get_once(session, path, api_key, params=params)
    except asyncio.TimeoutError as exc:
        raise StatsUnavailableError(
            f"Stats API timeout ({int(timeout or 0)}s)"
        ) from exc
async def _henrik_get_once(
    session: aiohttp.ClientSession,
    path: str,
    api_key: str,
    *,
    params: dict[str, str] | None = None,
) -> Any:
    url = f"{HENRIK_BASE}{path}"
    headers = {"Authorization": api_key}
    try:
        async with session.get(url, headers=headers, params=params) as resp:
            cache_status = resp.headers.get("X-Cache-Status")
            if cache_status and "/v4/" in path and "matches" in path:
                logger.info("Henrik live cache=%s path=%s", cache_status, path)
            elif cache_status and "stored-matches" in path:
                logger.debug("Henrik stored cache=%s path=%s", cache_status, path)
            if resp.status in {400, 404}:
                payload = await _safe_json(resp)
                mapped = _map_henrik_error(payload, default=None)
                if mapped is None:
                    return None
                if isinstance(mapped, Exception):
                    raise mapped
            if resp.status == 429:
                raise StatsUnavailableError("Stats API rate limit (429)")
            if resp.status >= 500:
                raise StatsUnavailableError(f"Stats API server error ({resp.status})")
            if resp.status != 200:
                text = await resp.text()
                raise StatsUnavailableError(f"Stats API error ({resp.status}): {text[:120]}")
            payload = await resp.json()
    except aiohttp.ClientError as exc:
        raise StatsUnavailableError(f"Stats API request failed: {exc}") from exc
    status = payload.get("status")
    if status == 404:
        return _map_henrik_error(payload, default=None)
    if status != 200:
        mapped = _map_henrik_error(payload, default="raise")
        if mapped is None:
            return None
        if isinstance(mapped, Exception):
            raise mapped
        raise StatsUnavailableError(str(mapped))
    return payload.get("data")
async def _safe_json(resp: aiohttp.ClientResponse) -> dict[str, Any]:
    try:
        payload = await resp.json()
        if isinstance(payload, dict):
            return payload
    except (aiohttp.ContentTypeError, ValueError):
        pass
    return {}
def _map_henrik_error(payload: dict[str, Any], *, default: str | None) -> Any:
    errors = payload.get("errors") or []
    if not errors:
        return None if default is None else _default_error(default, "Stats API error")
    error = errors[0]
    code = error.get("code")
    message = str(error.get("message") or "Stats API error")
    if code == 22 or "not found" in message.lower():
        return None if default is None else ProfilePrivateError(
            "Riot profile is private or match history is unavailable"
        )
    if code == 43:
        raise StatsError(
            "Stats API: invalid PUUID — use fresh puuid from /v2/account and "
            f"/v4/by-puuid/matches/{{region}}/pc/{{puuid}} (not hardcoded)"
        )
    if code == 0 and "unauthorized" in message.lower():
        raise StatsUnavailableError("Stats API: invalid or missing API key")
    if default == "raise":
        raise StatsUnavailableError(message)
    return None if default is None else _default_error(default, message)
def _default_error(default: str, message: str) -> Any:
    if default == "raise":
        raise StatsUnavailableError(message)
    return None
def _normalize_henrik_match(match: dict[str, Any], puuid: str) -> dict[str, Any]:
    if match.get("players"):
        return _normalize_full_match(match, puuid)
    if match.get("meta") and isinstance(match.get("stats"), dict):
        stats = match["stats"]
        if stats.get("puuid") or stats.get("kills") is not None:
            return _normalize_stored_v1_match(match)
    return _normalize_compact_match(match)


def _rounds_from_stored_match(meta: dict[str, Any], teams: Any) -> int:
    for key in ("rounds_played", "rounds"):
        raw = meta.get(key)
        if raw is not None:
            try:
                rounds = int(raw)
                if rounds > 0:
                    return rounds
            except (TypeError, ValueError):
                pass

    total = 0
    if isinstance(teams, list):
        for team in teams:
            if isinstance(team, dict):
                total += int(team.get("rounds_won") or team.get("rounds") or 0)
    elif isinstance(teams, dict):
        for value in teams.values():
            if isinstance(value, (int, float)):
                total += int(value)
            elif isinstance(value, dict):
                total += int(value.get("rounds_won") or value.get("rounds") or 0)
    if total > 0:
        return total
    return 20


def _normalize_stored_v1_match(match: dict[str, Any]) -> dict[str, Any]:
    meta = match.get("meta") or {}
    stats = match.get("stats") or {}
    teams = match.get("teams") or {}
    rounds = _rounds_from_stored_match(meta, teams)
    score = float(stats.get("score") or 0)
    acs = score / rounds
    kills = float(stats.get("kills") or 0)
    deaths = float(stats.get("deaths") or 0)
    assists = float(stats.get("assists") or 0)
    shots = stats.get("shots") or {}
    headshots = float(shots.get("head") or stats.get("headshots") or 0)
    bodyshots = float(shots.get("body") or stats.get("bodyshots") or 0)
    legshots = float(shots.get("leg") or stats.get("legshots") or 0)
    total_shots = headshots + bodyshots + legshots
    damage = stats.get("damage") or {}
    made = float(damage.get("made") or damage.get("dealt") or 0)
    received = float(damage.get("received") or 0)
    damage_delta = (made - received) / rounds
    started = meta.get("started_at") or meta.get("game_start") or meta.get("gameStart")
    puuid = str(stats.get("puuid") or "")
    explicit_kast = stats.get("kast") or stats.get("kast_percent") or stats.get("kAST")
    explicit_val = float(explicit_kast) if explicit_kast is not None else None
    kast = resolve_kast_percent(
        match,
        puuid,
        rounds=rounds,
        kills=kills,
        deaths=deaths,
        assists=assists,
        explicit=explicit_val,
    )

    return {
        "metadata": {
            "game_start": started,
            "timestamp": started,
            "rounds_played": rounds,
        },
        "stats": {
            "scorePerRound": {"value": acs},
            "kills": {"value": kills},
            "deaths": {"value": deaths},
            "damageDeltaPerRound": {"value": damage_delta},
            "headshots": {"value": headshots},
            "shotsFired": {"value": total_shots},
            "assists": {"value": assists},
            "kAST": {"value": kast},
        },
    }


def _normalize_compact_match(match: dict[str, Any]) -> dict[str, Any]:
    metadata = match.get("metadata") or match.get("meta") or {}
    stats = match.get("stats") or {}
    return _build_normalized_match(metadata, stats)
def _normalize_full_match(match: dict[str, Any], puuid: str) -> dict[str, Any]:
    metadata = match.get("metadata") or match.get("meta") or {}
    players = (match.get("players") or {}).get("all_players") or []
    player = next((item for item in players if item.get("puuid") == puuid), None)
    if player is None:
        raise StatsError("Player not found in Henrik match payload")
    stats = dict(player.get("stats") or {})
    assists = float(stats.get("assists") or 0)
    kills = float(stats.get("kills") or 0)
    deaths = float(stats.get("deaths") or 0)
    rounds = int(
        metadata.get("rounds_played")
        or metadata.get("rounds")
        or stats.get("rounds_played")
        or stats.get("roundsPlayed")
        or 0
    )
    if rounds <= 0:
        rounds = max(int(kills + deaths), 1)
    damage = stats.get("damage")
    if not isinstance(damage, dict):
        made = player.get("damage_made")
        received = player.get("damage_received")
        if made is not None or received is not None:
            stats["damage"] = {
                "made": made or 0,
                "received": received or 0,
            }
        elif isinstance(player.get("damage"), list):
            stats["damage"] = {
                "made": sum(int(item.get("damage") or 0) for item in player["damage"]),
                "received": 0,
            }
    explicit_kast = stats.get("kast") or stats.get("kast_percent") or stats.get("kAST")
    explicit_val = float(explicit_kast) if explicit_kast is not None else None
    kast = resolve_kast_percent(
        match,
        puuid,
        rounds=rounds,
        kills=kills,
        deaths=deaths,
        assists=assists,
        explicit=explicit_val,
    )
    stats["kAST"] = kast
    return _build_normalized_match(metadata, stats)
def _build_normalized_match(metadata: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any]:
    rounds = (
        metadata.get("rounds_played")
        or metadata.get("rounds")
        or stats.get("rounds_played")
        or stats.get("roundsPlayed")
        or 0
    )
    try:
        rounds = int(rounds)
    except (TypeError, ValueError):
        rounds = 0
    if rounds <= 0:
        rounds = 1
    score = float(stats.get("score") or 0)
    acs = score / rounds
    kills = float(stats.get("kills") or 0)
    deaths = float(stats.get("deaths") or 0)
    headshots = float(stats.get("headshots") or 0)
    bodyshots = float(stats.get("bodyshots") or 0)
    legshots = float(stats.get("legshots") or 0)
    shots = headshots + bodyshots + legshots
    damage = stats.get("damage") or {}
    damage_delta = 0.0
    if isinstance(damage, dict):
        made = float(damage.get("made") or damage.get("dealt") or 0)
        received = float(damage.get("received") or 0)
        damage_delta = (made - received) / rounds
    assists = float(stats.get("assists") or 0)
    if isinstance(stats.get("kAST"), (int, float)):
        kast = round(float(stats["kAST"]), 1)
    else:
        explicit_kast = stats.get("kast") or stats.get("kast_percent") or stats.get("kAST")
        if isinstance(explicit_kast, dict):
            explicit_kast = explicit_kast.get("value")
        explicit_val = float(explicit_kast) if explicit_kast is not None else None
        if explicit_val is not None and explicit_val > 0:
            kast = round(explicit_val, 1)
        else:
            kast = estimate_kast_from_totals(rounds, kills, deaths, assists)
    hs_percent = round(headshots / shots * 100.0, 1) if shots > 0 else None
    game_start = (
        metadata.get("started_at")
        or metadata.get("game_start")
        or metadata.get("gameStart")
    )
    out_stats = {
        "scorePerRound": {"value": acs},
        "kills": {"value": kills},
        "deaths": {"value": deaths},
        "damageDeltaPerRound": {"value": damage_delta},
        "headshots": {"value": headshots},
        "shotsFired": {"value": shots},
        "assists": {"value": assists},
        "kAST": {"value": kast},
    }
    if hs_percent is not None:
        out_stats["headshotPercentage"] = {"value": hs_percent}
    return {
        "metadata": {
            "game_start": game_start,
            "timestamp": game_start,
            "rounds_played": rounds,
        },
        "stats": out_stats,
    }
