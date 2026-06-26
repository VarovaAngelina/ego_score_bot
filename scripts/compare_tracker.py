"""Compare Henrik weekly stats vs tracker.gg reference."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from bot.services.henrik_service import _normalize_henrik_match, _prepare_weekly_matches
from bot.services.stats_utils import aggregate_match_stats, current_week_bounds, filter_matches_by_week, match_timestamp

RIOT = "LX L1x0#EG0"
TRACKER = {
    "matches": 4,
    "acs": 215,
    "kd": 1.1,
    "hs": 29,
    "dd": 7,
    "kills": 63,
    "deaths": 58,
    "assists": 35,
}


async def main() -> None:
    key = os.environ["HENRIK_API_KEY"]
    name, tag = RIOT.split("#", 1)
    async with aiohttp.ClientSession(headers={"Authorization": key}) as session:
        async with session.get(f"https://api.henrikdev.xyz/valorant/v2/account/{name}/{tag}") as resp:
            acc = (await resp.json())["data"]
        puuid, region = acc["puuid"], acc["region"].lower()

        week_start, week_end = current_week_bounds()
        print(f"Week MSK: {week_start.date()} – {week_end.date()}\n")

        all_raw: list[dict] = []
        for page in range(1, 4):
            async with session.get(
                f"https://api.henrikdev.xyz/valorant/v1/by-puuid/stored-matches/{region}/{puuid}",
                params={"size": "10", "page": str(page)},
            ) as resp:
                batch = (await resp.json()).get("data") or []
            if not batch:
                break
            all_raw.extend(batch)

        weekly_raw = filter_matches_by_week(all_raw, week_start, week_end)
        async with session.get(
            f"https://api.henrikdev.xyz/valorant/v2/by-puuid/mmr/{region}/{puuid}",
        ) as resp:
            mmr = (await resp.json()).get("data") or {}
        current = mmr.get("current_data") or mmr.get("current") or {}
        rank = current.get("currenttierpatched") or current.get("currenttier_patched")
        scored = _prepare_weekly_matches(weekly_raw, str(rank) if rank else None)

        print(f"Stored total fetched: {len(all_raw)}")
        print(f"In week (all modes): {len(weekly_raw)}")
        print(f"In week (scored): {len(scored)}\n")

        for index, raw in enumerate(scored, start=1):
            meta = raw.get("meta") or {}
            stats = raw.get("stats") or {}
            map_name = (meta.get("map") or {}).get("name")
            ts = match_timestamp(raw)
            print(
                f"{index}. {ts}  {map_name}  "
                f"K/D/A {stats.get('kills')}/{stats.get('deaths')}/{stats.get('assists')}"
            )

        normalized = [_normalize_henrik_match(m, puuid) for m in scored]
        bot_stats = aggregate_match_stats(normalized)

        print("\n--- Bot (current formula) ---")
        print(f"matches: {len(normalized)}")
        print(f"ACS {bot_stats.acs}  K/D {bot_stats.kd_ratio}  HS% {bot_stats.hs_percent}")
        print(f"DDΔ {bot_stats.damage_delta}  KAST {bot_stats.kast_percent}%")

        print("\n--- Tracker reference ---")
        print(TRACKER)


if __name__ == "__main__":
    asyncio.run(main())
