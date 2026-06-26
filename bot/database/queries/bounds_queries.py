"""stat_bounds table queries."""

from __future__ import annotations

from bot.database.connection import DatabasePool
from bot.database.models import StatBound
from bot.services.score_service import ALL_STATS, FALLBACK_BOUNDS


async def get_all(db: DatabasePool) -> dict[str, StatBound]:
    rows = await db.fetchall(
        """
        SELECT stat_name, min_val, max_val, updated_at
        FROM stat_bounds
        """
    )
    if not rows:
        return dict(FALLBACK_BOUNDS)

    bounds = dict(FALLBACK_BOUNDS)
    for row in rows:
        bounds[str(row[0])] = StatBound(
            stat_name=str(row[0]),
            min_val=float(row[1]),
            max_val=float(row[2]),
            updated_at=row[3],
        )
    return bounds


async def upsert(db: DatabasePool, bounds: dict[str, StatBound]) -> None:
    for name, bound in bounds.items():
        await db.execute(
            """
            INSERT INTO stat_bounds (stat_name, min_val, max_val)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                min_val = VALUES(min_val),
                max_val = VALUES(max_val)
            """,
            (name, bound.min_val, bound.max_val),
        )


async def ensure_seed(db: DatabasePool) -> None:
    row = await db.fetchone("SELECT COUNT(*) FROM stat_bounds")
    if row and int(row[0]) > 0:
        return
    await upsert(db, FALLBACK_BOUNDS)
