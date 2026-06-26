"""Rank position change vs previous cache refresh (shown in /top)."""

from __future__ import annotations

from datetime import date

from bot.database.connection import DatabasePool
from bot.database.queries import cache_queries


def compute_rank_delta(reference_rank: int | None, current_rank: int) -> int:
    """Positive delta means the player moved up (lower rank number)."""
    if reference_rank is None:
        return 0
    return reference_rank - current_rank


def compute_rank_deltas_since_last_refresh(
    reference_ranks: dict[int, int],
    scored_user_ids: list[int],
) -> tuple[dict[int, int], dict[int, int]]:
    """Return (rank_delta, new_reference_rank) for each user in leaderboard order."""
    deltas: dict[int, int] = {}
    new_refs: dict[int, int] = {}
    for rank, user_id in enumerate(scored_user_ids, start=1):
        ref = reference_ranks.get(user_id)
        deltas[user_id] = compute_rank_delta(ref, rank)
        new_refs[user_id] = rank
    return deltas, new_refs


async def refresh_rank_deltas(db: DatabasePool, week_start: date) -> None:
    scored = await cache_queries.list_scored_for_week(db, week_start)
    if not scored:
        return

    user_ids = [row[0] for row in scored]
    reference_ranks = await cache_queries.get_reference_ranks(db, week_start)
    deltas, new_refs = compute_rank_deltas_since_last_refresh(reference_ranks, user_ids)
    await cache_queries.apply_rank_deltas(db, week_start, deltas)
    await cache_queries.apply_reference_ranks(db, week_start, new_refs)
