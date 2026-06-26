"""Henrik API normalization tests."""

from __future__ import annotations

from bot.services.henrik_service import (
    _normalize_full_match,
    _normalize_henrik_match,
    _normalize_stored_v1_match,
    _split_batch_by_week,
)
from bot.services.stats_utils import aggregate_match_stats, current_week_bounds, filter_matches_by_week


def test_normalize_full_match_by_puuid_payload() -> None:
    puuid = "98880686-2fd6-5704-aa6b-405a55c1bbaf"
    match = {
        "metadata": {
            "game_start": 1782149715,
            "rounds_played": 19,
            "mode": "Competitive",
        },
        "players": {
            "all_players": [
                {
                    "puuid": puuid,
                    "stats": {
                        "score": 3800,
                        "kills": 18,
                        "deaths": 12,
                        "headshots": 9,
                        "bodyshots": 20,
                        "legshots": 3,
                    },
                    "damage_made": 3200,
                    "damage_received": 2500,
                }
            ]
        },
    }

    normalized = _normalize_full_match(match, puuid)
    assert normalized["stats"]["scorePerRound"]["value"] > 0
    assert normalized["stats"]["kills"]["value"] == 18
    assert normalized["stats"]["damageDeltaPerRound"]["value"] > 0


def test_weekly_filter_on_normalized_full_matches() -> None:
    puuid = "abc"
    week_start, week_end = current_week_bounds()
    ts = int(week_end.timestamp()) - 3600
    match = {
        "metadata": {"game_start": ts, "rounds_played": 10},
        "players": {
            "all_players": [
                {
                    "puuid": puuid,
                    "stats": {
                        "score": 2000,
                        "kills": 10,
                        "deaths": 8,
                        "headshots": 4,
                        "bodyshots": 10,
                        "legshots": 1,
                    },
                    "damage_made": 1800,
                    "damage_received": 1500,
                }
            ]
        },
    }
    normalized = _normalize_henrik_match(match, puuid)
    weekly = filter_matches_by_week([normalized], week_start, week_end)
    stats = aggregate_match_stats(weekly)
    assert stats.acs > 0
    assert stats.kd_ratio > 0


def test_split_batch_stops_at_week_boundary() -> None:
    week_start, week_end = current_week_bounds()
    week_start_ts = int(week_start.timestamp())
    week_end_ts = int(week_end.timestamp())

    in_week = int(week_end.timestamp()) - 3600
    before_week = week_start_ts - 86400

    batch = [
        {"metadata": {"game_start": in_week}},
        {"metadata": {"game_start": before_week}},
    ]
    weekly, stop = _split_batch_by_week(batch, week_start_ts, week_end_ts)
    assert len(weekly) == 1
    assert stop is True


def test_split_batch_continues_when_all_in_week() -> None:
    week_start, week_end = current_week_bounds()
    week_start_ts = int(week_start.timestamp())
    week_end_ts = int(week_end.timestamp())
    ts = int(week_end.timestamp()) - 7200

    batch = [{"metadata": {"game_start": ts}}, {"metadata": {"game_start": ts - 60}}]
    weekly, stop = _split_batch_by_week(batch, week_start_ts, week_end_ts)
    assert len(weekly) == 2
    assert stop is False


def test_stored_v1_match_week_filter_and_stats() -> None:
    from datetime import timedelta

    week_start, week_end = current_week_bounds()
    started_at = (week_start + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    match = {
        "meta": {
            "id": "test-match",
            "mode": "Competitive",
            "started_at": started_at,
        },
        "stats": {
            "puuid": "abc",
            "score": 4000,
            "kills": 20,
            "deaths": 15,
            "assists": 5,
            "shots": {"head": 10, "body": 20, "leg": 2},
            "damage": {"made": 3200, "received": 2800},
        },
        "teams": {"red": {"rounds_won": 13}, "blue": {"rounds_won": 10}},
    }

    normalized = _normalize_stored_v1_match(match)
    weekly = filter_matches_by_week([normalized], week_start, week_end)
    assert len(weekly) == 1
    stats = aggregate_match_stats(weekly)
    assert stats.acs > 0
    assert stats.kd_ratio > 0
    assert stats.kast_percent > 0


def test_stored_v1_started_at_parsed_from_raw() -> None:
    week_start, week_end = current_week_bounds()
    from datetime import timedelta
    started_at = (week_start + timedelta(hours=3)).isoformat().replace("+03:00", "Z")
    raw = {
        "meta": {"started_at": started_at, "mode": "Competitive"},
        "stats": {"puuid": "x", "score": 2000, "kills": 10, "deaths": 8},
        "teams": {},
    }
    weekly, _ = _split_batch_by_week([raw], int(week_start.timestamp()), int(week_end.timestamp()))
    assert len(weekly) == 1
