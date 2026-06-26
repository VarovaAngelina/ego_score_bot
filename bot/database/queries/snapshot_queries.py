"""weekly_snapshots table queries."""

from __future__ import annotations

from datetime import date

from bot.database.connection import DatabasePool
from bot.database.models import LeaderboardEntry, PlayerStats, WeekSummary, WeeklySnapshotRow


def _row_to_snapshot(row: tuple) -> WeeklySnapshotRow:
    return WeeklySnapshotRow(
        week_start=row[0],
        week_end=row[1],
        rank=int(row[2]),
        user_id=int(row[3]),
        riot_id=str(row[4]),
        current_rank=row[5],
        ego_score=float(row[6]),
        stats=PlayerStats(
            acs=float(row[7] or 0),
            kd_ratio=float(row[8] or 0),
            damage_delta=float(row[9] or 0),
            hs_percent=float(row[10] or 0),
            kast_percent=float(row[11] or 0),
        ),
    )


async def save_week(
    db: DatabasePool,
    week_start: date,
    week_end: date,
    rows: list[WeeklySnapshotRow],
) -> None:
    await db.execute("DELETE FROM weekly_snapshots WHERE week_start = %s", (week_start,))
    for row in rows:
        await db.execute(
            """
            INSERT INTO weekly_snapshots (
                week_start, week_end, `rank`, user_id, riot_id, current_rank,
                ego_score, acs, kd_ratio, damage_delta, hs_percent, kast_percent
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                week_start,
                week_end,
                row.rank,
                row.user_id,
                row.riot_id,
                row.current_rank,
                row.ego_score,
                row.stats.acs,
                row.stats.kd_ratio,
                row.stats.damage_delta,
                row.stats.hs_percent,
                row.stats.kast_percent,
            ),
        )


async def get_all_for_week(
    db: DatabasePool,
    week_start: date,
) -> list[LeaderboardEntry]:
    count = await count_for_week(db, week_start)
    if count == 0:
        return []
    return await get_page(db, week_start, 0, count)


async def get_page(
    db: DatabasePool,
    week_start: date,
    offset: int,
    limit: int = 20,
) -> list[LeaderboardEntry]:
    rows = await db.fetchall(
        """
        SELECT `rank`, user_id, riot_id, current_rank, ego_score
        FROM weekly_snapshots
        WHERE week_start = %s
        ORDER BY `rank` ASC
        LIMIT %s OFFSET %s
        """,
        (week_start, limit, offset),
    )
    return [
        LeaderboardEntry(
            rank=int(row[0]),
            user_id=int(row[1]),
            riot_id=str(row[2]),
            current_rank=row[3],
            ego_score=float(row[4]),
            rank_delta=0,
        )
        for row in rows
    ]


async def count_for_week(db: DatabasePool, week_start: date) -> int:
    row = await db.fetchone(
        "SELECT COUNT(*) FROM weekly_snapshots WHERE week_start = %s",
        (week_start,),
    )
    return int(row[0]) if row else 0


async def list_weeks(db: DatabasePool, limit: int = 20) -> list[WeekSummary]:
    rows = await db.fetchall(
        """
        SELECT week_start, week_end, COUNT(*) AS player_count
        FROM weekly_snapshots
        GROUP BY week_start, week_end
        ORDER BY week_start DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [
        WeekSummary(
            week_start=row[0],
            week_end=row[1],
            player_count=int(row[2]),
        )
        for row in rows
    ]


async def week_exists(db: DatabasePool, week_start: date) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM weekly_snapshots WHERE week_start = %s LIMIT 1",
        (week_start,),
    )
    return row is not None


async def get_user_ranks_map(db: DatabasePool, week_start: date) -> dict[int, int]:
    rows = await db.fetchall(
        """
        SELECT user_id, `rank`
        FROM weekly_snapshots
        WHERE week_start = %s
        """,
        (week_start,),
    )
    return {int(row[0]): int(row[1]) for row in rows}
