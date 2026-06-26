"""One-off Henrik API probe for LX L1x0#EG0."""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from urllib.parse import quote

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
KEY = os.getenv("HENRIK_API_KEY", "")
BASE = "https://api.henrikdev.xyz"
NAME, TAG = "LX L1x0", "EG0"


async def fetch(session: aiohttp.ClientSession, path: str, timeout: float = 45.0) -> None:
    t0 = time.perf_counter()
    try:
        async with session.get(
            f"{BASE}{path}",
            headers={"Authorization": KEY},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            cache = resp.headers.get("X-Cache-Status", "?")
            body = await resp.json()
            elapsed = time.perf_counter() - t0
            status = body.get("status")
            data = body.get("data")
            count = len(data) if isinstance(data, list) else data
            print(f"{elapsed:5.1f}s cache={cache} status={status} items={count} {path.split('?')[0]}")
            if isinstance(data, list) and data:
                sample = data[0]
                meta = sample.get("metadata") or sample.get("meta") or sample
                gs = meta.get("game_start") or meta.get("gameStart") or meta.get("timestamp")
                print(f"      sample game_start={gs} keys={list(sample.keys())[:6]}")
                if path.startswith("/valorant/v1/"):
                    import json
                    print("      meta=", json.dumps(sample.get("meta"), default=str)[:500])
                    print("      stats=", json.dumps(sample.get("stats"), default=str)[:500])
                    if os.environ.get("FULL"):
                        print(json.dumps(sample, indent=2)[:2000])
    except Exception as exc:
        print(f" FAIL {path.split('?')[0]}: {exc}")


async def main() -> None:
    if not KEY:
        raise SystemExit("HENRIK_API_KEY missing")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE}/valorant/v2/account/{quote(NAME)}/{quote(TAG)}",
            headers={"Authorization": KEY},
        ) as resp:
            acc = await resp.json()
        data = acc.get("data") or {}
        puuid = data["puuid"]
        region = (data.get("region") or "eu").lower()
        print(f"account ok region={region} puuid={puuid[:8]}...")

        await fetch(session, f"/valorant/v1/by-puuid/stored-matches/{region}/{puuid}?size=10&page=1")
        await fetch(session, f"/valorant/v1/stored-matches/{region}/{quote(NAME)}/{quote(TAG)}?size=10&page=1")
        return
        await fetch(session, f"/valorant/v4/by-puuid/matches/{region}/pc/{puuid}?size=3&start=0", timeout=60)
        await fetch(
            session,
            f"/valorant/v4/matches/{region}/pc/{quote(NAME)}/{quote(TAG)}?size=3&start=0",
            timeout=60,
        )
        await fetch(session, f"/valorant/v3/by-puuid/matches/{region}/{puuid}?size=3&page=1", timeout=60)


if __name__ == "__main__":
    asyncio.run(main())
