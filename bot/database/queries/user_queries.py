"""users table queries."""

from __future__ import annotations

import logging

from bot.database.connection import DatabasePool
from bot.database.models import User

logger = logging.getLogger("ego_score_bot.users")


class RegistrationPersistError(RuntimeError):
    """User row was not saved or could not be read back."""


def _row_to_user(row: tuple) -> User:
    return User(
        id=int(row[0]),
        discord_id=int(row[1]),
        riot_id=str(row[2]),
        registered_at=row[3],
    )


async def get_by_discord_id(db: DatabasePool, discord_id: int) -> User | None:
    row = await db.fetchone(
        """
        SELECT id, discord_id, riot_id, registered_at
        FROM users
        WHERE discord_id = %s
        """,
        (discord_id,),
    )
    return _row_to_user(row) if row else None


async def get_by_id(db: DatabasePool, user_id: int) -> User | None:
    row = await db.fetchone(
        """
        SELECT id, discord_id, riot_id, registered_at
        FROM users
        WHERE id = %s
        """,
        (user_id,),
    )
    return _row_to_user(row) if row else None


async def get_by_riot_id(db: DatabasePool, riot_id: str) -> User | None:
    row = await db.fetchone(
        """
        SELECT id, discord_id, riot_id, registered_at
        FROM users
        WHERE riot_id = %s
        """,
        (riot_id,),
    )
    return _row_to_user(row) if row else None


async def register(db: DatabasePool, discord_id: int, riot_id: str) -> User:
    await db.execute(
        """
        INSERT INTO users (discord_id, riot_id)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE riot_id = VALUES(riot_id)
        """,
        (discord_id, riot_id),
    )

    saved = await get_by_discord_id(db, discord_id)
    if saved is None or saved.riot_id != riot_id:
        logger.error(
            "Registration did not persist (discord_id=%s, riot_id=%s, saved=%s)",
            discord_id,
            riot_id,
            saved,
        )
        raise RegistrationPersistError("Registration failed to persist")

    logger.info(
        "Registered user id=%s discord_id=%s riot_id=%s",
        saved.id,
        saved.discord_id,
        saved.riot_id,
    )
    return saved


async def unregister(db: DatabasePool, discord_id: int) -> bool:
    user = await get_by_discord_id(db, discord_id)
    if user is None:
        return False

    await db.execute("DELETE FROM player_cache WHERE user_id = %s", (user.id,))
    await db.execute("DELETE FROM weekly_snapshots WHERE user_id = %s", (user.id,))
    rows = await db.execute("DELETE FROM users WHERE id = %s", (user.id,))
    if rows > 0:
        logger.info("Unregistered user id=%s discord_id=%s", user.id, discord_id)
    return rows > 0


async def list_all(db: DatabasePool) -> list[User]:
    rows = await db.fetchall(
        """
        SELECT id, discord_id, riot_id, registered_at
        FROM users
        ORDER BY registered_at ASC
        """
    )
    return [_row_to_user(row) for row in rows]


async def count_all(db: DatabasePool) -> int:
    row = await db.fetchone("SELECT COUNT(*) FROM users")
    return int(row[0]) if row else 0
