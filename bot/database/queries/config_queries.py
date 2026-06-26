"""bot_config key-value persistence."""

from __future__ import annotations

from bot.database.connection import DatabasePool


async def get(db: DatabasePool, key: str) -> str | None:
    row = await db.fetchone(
        "SELECT key_value FROM bot_config WHERE key_name = %s",
        (key,),
    )
    return str(row[0]) if row else None


async def set(db: DatabasePool, key: str, value: str) -> None:
    await db.execute(
        """
        INSERT INTO bot_config (key_name, key_value)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE key_value = VALUES(key_value)
        """,
        (key, value),
    )
