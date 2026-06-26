"""aiomysql connection pool."""

from __future__ import annotations

import logging
from typing import Any

import aiomysql

from bot.config import Settings

logger = logging.getLogger("ego_score_bot.db")


class DatabasePool:
    def __init__(self, pool: aiomysql.Pool) -> None:
        self._pool = pool

    @classmethod
    async def create(cls, settings: Settings) -> DatabasePool:
        pool = await aiomysql.create_pool(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            db=settings.db_name,
            autocommit=True,
            minsize=1,
            maxsize=10,
            charset="utf8mb4",
            init_command="SET time_zone = '+03:00'",
        )
        logger.info("MySQL pool created (%s:%s/%s)", settings.db_host, settings.db_port, settings.db_name)
        return cls(pool)

    async def close(self) -> None:
        self._pool.close()
        await self._pool.wait_closed()
        logger.info("MySQL pool closed")

    async def ping(self) -> None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()

    async def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> int:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, args or ())
                return cur.rowcount

    async def fetchone(self, sql: str, args: tuple[Any, ...] | None = None) -> tuple[Any, ...] | None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, args or ())
                return await cur.fetchone()

    async def fetchall(self, sql: str, args: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, args or ())
                return await cur.fetchall()

    async def insert(self, sql: str, args: tuple[Any, ...] | None = None) -> int:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, args or ())
                return int(cur.lastrowid)
