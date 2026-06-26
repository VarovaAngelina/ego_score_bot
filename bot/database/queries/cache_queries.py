"""player_cache table queries."""

from __future__ import annotations

from datetime import date, datetime

from bot.database.connection import DatabasePool
from bot.database.models import LeaderboardEntry, PlayerCache, PlayerStats, ScoreResult


def _row_to_cache(row: tuple) -> PlayerCache:
    stats = PlayerStats(
        acs=float(row[3] or 0),
        kd_ratio=float(row[4] or 0),
        damage_delta=float(row[5] or 0),
        hs_percent=float(row[6] or 0),
        kast_percent=float(row[7] or 0),
    )
    result = ScoreResult(
        ego_score=float(row[8] or 0),
        contrib_acs=float(row[11] or 0),
        contrib_kd=float(row[12] or 0),
        contrib_dd=float(row[13] or 0),
        contrib_hs=float(row[14] or 0),
        contrib_kast=float(row[15] or 0),
    )
    return PlayerCache(
        id=int(row[0]),
        user_id=int(row[1]),
        week_start=row[2],
        stats=stats,
        ego_score=float(row[8] or 0),
        current_rank=row[9],
        rank_delta=int(row[10] or 0),
        result=result,
        fetched_at=row[17],
        matches_played=int(row[16] or 0),
        is_stale=bool(row[18]),
    )


async def get_by_user_week(db: DatabasePool, user_id: int, week_start: date) -> PlayerCache | None:
    row = await db.fetchone(
        """
        SELECT id, user_id, week_start,
               acs, kd_ratio, damage_delta, hs_percent, kast_percent,
               ego_score, current_rank, rank_delta,
               contrib_acs, contrib_kd, contrib_dd, contrib_hs, contrib_kast,
               matches_played, fetched_at, is_stale
        FROM player_cache
        WHERE user_id = %s AND week_start = %s
        """,
        (user_id, week_start),
    )
    return _row_to_cache(row) if row else None


async def upsert(
    db: DatabasePool,
    *,
    user_id: int,
    week_start: date,
    stats: PlayerStats,
    result: ScoreResult,
    current_rank: str | None,
    rank_delta: int,
    fetched_at: datetime,
    is_stale: bool = False,
    matches_played: int = 0,
) -> None:
    await db.execute(
        """
        INSERT INTO player_cache (
            user_id, week_start,
            acs, kd_ratio, damage_delta, hs_percent, kast_percent,
            ego_score, current_rank, rank_delta,
            contrib_acs, contrib_kd, contrib_dd, contrib_hs, contrib_kast,
            matches_played, fetched_at, is_stale
        ) VALUES (
            %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            acs = VALUES(acs),
            kd_ratio = VALUES(kd_ratio),
            damage_delta = VALUES(damage_delta),
            hs_percent = VALUES(hs_percent),
            kast_percent = VALUES(kast_percent),
            ego_score = VALUES(ego_score),
            current_rank = VALUES(current_rank),
            contrib_acs = VALUES(contrib_acs),
            contrib_kd = VALUES(contrib_kd),
            contrib_dd = VALUES(contrib_dd),
            contrib_hs = VALUES(contrib_hs),
            contrib_kast = VALUES(contrib_kast),
            matches_played = VALUES(matches_played),
            fetched_at = VALUES(fetched_at),
            is_stale = VALUES(is_stale)
        """,
        (
            user_id,
            week_start,
            stats.acs,
            stats.kd_ratio,
            stats.damage_delta,
            stats.hs_percent,
            stats.kast_percent,
            result.ego_score,
            current_rank,
            rank_delta,
            result.contrib_acs,
            result.contrib_kd,
            result.contrib_dd,
            result.contrib_hs,
            result.contrib_kast,
            matches_played,
            fetched_at,
            is_stale,
        ),
    )


_SCORED_WEEK_FILTER = (
    "pc.week_start = %s AND pc.ego_score > 0 AND pc.matches_played > 0"
)


async def count_scored_for_week(db: DatabasePool, week_start: date) -> int:
    row = await db.fetchone(
        f"""
        SELECT COUNT(*)
        FROM player_cache pc
        WHERE {_SCORED_WEEK_FILTER}
        """,
        (week_start,),
    )
    return int(row[0]) if row else 0


async def get_latest_fetched_at(
    db: DatabasePool,
    week_start: date,
) -> datetime | None:
    row = await db.fetchone(
        f"""
        SELECT MAX(pc.fetched_at)
        FROM player_cache pc
        WHERE {_SCORED_WEEK_FILTER}
        """,
        (week_start,),
    )
    return row[0] if row and row[0] is not None else None


async def list_scored_for_week(
    db: DatabasePool,
    week_start: date,
) -> list[tuple[int, str, str | None, float, PlayerStats]]:
    rows = await db.fetchall(
        f"""
        SELECT pc.user_id, u.riot_id, pc.current_rank, pc.ego_score,
               pc.acs, pc.kd_ratio, pc.damage_delta, pc.hs_percent, pc.kast_percent
        FROM player_cache pc
        JOIN users u ON u.id = pc.user_id
        WHERE {_SCORED_WEEK_FILTER}
        ORDER BY pc.ego_score DESC, u.registered_at ASC
        """,
        (week_start,),
    )
    result: list[tuple[int, str, str | None, float, PlayerStats]] = []
    for row in rows:
        stats = PlayerStats(
            acs=float(row[4] or 0),
            kd_ratio=float(row[5] or 0),
            damage_delta=float(row[6] or 0),
            hs_percent=float(row[7] or 0),
            kast_percent=float(row[8] or 0),
        )
        result.append((int(row[0]), str(row[1]), row[2], float(row[3]), stats))
    return result


async def get_top_for_week(
    db: DatabasePool,
    week_start: date,
    limit: int = 10,
) -> list[LeaderboardEntry]:
    rows = await db.fetchall(
        f"""
        SELECT u.riot_id, pc.current_rank, pc.ego_score, pc.rank_delta, pc.user_id
        FROM player_cache pc
        JOIN users u ON u.id = pc.user_id
        WHERE {_SCORED_WEEK_FILTER}
        ORDER BY pc.ego_score DESC, u.registered_at ASC
        LIMIT %s
        """,
        (week_start, limit),
    )
    entries: list[LeaderboardEntry] = []
    for index, row in enumerate(rows, start=1):
        entries.append(
            LeaderboardEntry(
                rank=index,
                user_id=int(row[4]),
                riot_id=str(row[0]),
                current_rank=row[1],
                ego_score=float(row[2]),
                rank_delta=int(row[3] or 0),
            )
        )
    return entries


async def get_user_week_rank(
    db: DatabasePool,
    user_id: int,
    week_start: date,
) -> tuple[int | None, int]:
    """Return (rank, total_scored) for a user in the weekly leaderboard."""
    rows = await db.fetchall(
        f"""
        SELECT pc.user_id
        FROM player_cache pc
        JOIN users u ON u.id = pc.user_id
        WHERE {_SCORED_WEEK_FILTER}
        ORDER BY pc.ego_score DESC, u.registered_at ASC
        """,
        (week_start,),
    )
    total = len(rows)
    for index, row in enumerate(rows, start=1):
        if int(row[0]) == user_id:
            return index, total
    return None, total


async def mark_week_stale(db: DatabasePool, week_start: date) -> None:
    await db.execute(
        "UPDATE player_cache SET is_stale = TRUE WHERE week_start = %s",
        (week_start,),
    )


async def delete_week(db: DatabasePool, week_start: date) -> None:
    await db.execute("DELETE FROM player_cache WHERE week_start = %s", (week_start,))


async def set_rank_delta(
    db: DatabasePool,
    user_id: int,
    week_start: date,
    rank_delta: int,
) -> None:
    await db.execute(
        """
        UPDATE player_cache
        SET rank_delta = %s
        WHERE user_id = %s AND week_start = %s
        """,
        (rank_delta, user_id, week_start),
    )


async def apply_rank_deltas(
    db: DatabasePool,
    week_start: date,
    deltas: dict[int, int],
) -> None:
    for user_id, rank_delta in deltas.items():
        await set_rank_delta(db, user_id, week_start, rank_delta)


async def get_reference_ranks(db: DatabasePool, week_start: date) -> dict[int, int]:
    rows = await db.fetchall(
        """
        SELECT user_id, reference_rank
        FROM player_cache
        WHERE week_start = %s AND reference_rank IS NOT NULL
        """,
        (week_start,),
    )
    return {int(row[0]): int(row[1]) for row in rows}


async def apply_reference_ranks(
    db: DatabasePool,
    week_start: date,
    reference_ranks: dict[int, int],
) -> None:
    for user_id, reference_rank in reference_ranks.items():
        await db.execute(
            """
            UPDATE player_cache
            SET reference_rank = %s
            WHERE user_id = %s AND week_start = %s
            """,
            (reference_rank, user_id, week_start),
        )
