"""Tracker-style aggregation tests."""

import pytest

from bot.services.stats_utils import (
    aggregate_match_stats,
    dedupe_matches,
    filter_competitive_matches,
    filter_swiftplay_matches,
    is_ranked_player,
    prepare_weekly_scored_matches,
)


def _norm_match(
    *,
    rounds: int,
    acs: float,
    kills: int,
    deaths: int,
    dd: float,
    hs: float,
    kast: float,
    mode: str = "Competitive",
    match_id: str = "m1",
) -> dict:
    return {
        "meta": {"id": match_id, "mode": mode, "rounds_played": rounds},
        "metadata": {"rounds_played": rounds, "game_start": 1},
        "stats": {
            "scorePerRound": {"value": acs},
            "kills": {"value": kills},
            "deaths": {"value": deaths},
            "damageDeltaPerRound": {"value": dd},
            "headshotPercentage": {"value": hs},
            "kAST": {"value": kast},
        },
    }


TRACKER_WEEK = [
    _norm_match(rounds=19, acs=222, kills=17, deaths=13, dd=22, hs=45, kast=80, match_id="a"),
    _norm_match(rounds=20, acs=178, kills=12, deaths=11, dd=-8, hs=17, kast=70, match_id="b"),
    _norm_match(rounds=19, acs=317, kills=22, deaths=16, dd=45, hs=31, kast=90, match_id="c"),
    _norm_match(rounds=26, acs=165, kills=12, deaths=18, dd=-20, hs=24, kast=65, match_id="d"),
]


def test_tracker_weekly_aggregation() -> None:
    stats = aggregate_match_stats(TRACKER_WEEK)
    assert len(TRACKER_WEEK) == 4
    assert stats.acs == pytest.approx(215.4, abs=0.5)
    assert stats.kd_ratio == pytest.approx(1.09, abs=0.02)
    assert stats.hs_percent == pytest.approx(29.2, abs=0.3)
    assert stats.damage_delta == pytest.approx(7.1, abs=0.3)


def test_competitive_filter_excludes_other_modes() -> None:
    raw = TRACKER_WEEK + [
        {
            "meta": {"id": "dm1", "mode": "Deathmatch", "rounds_played": 20},
            "metadata": {"rounds_played": 20},
            "stats": {"scorePerRound": {"value": 999}},
        },
    ]
    competitive = filter_competitive_matches(raw)
    assert len(competitive) == 4


def test_dedupe_matches() -> None:
    duped = TRACKER_WEEK + [TRACKER_WEEK[0]]
    assert len(dedupe_matches(duped)) == 4


def test_prepare_weekly_scored_matches_ranked_uses_competitive_only() -> None:
    raw = TRACKER_WEEK + [
        _norm_match(
            rounds=20,
            acs=300,
            kills=20,
            deaths=10,
            dd=30,
            hs=40,
            kast=85,
            mode="Swiftplay",
            match_id="sp1",
        ),
    ]
    scored = prepare_weekly_scored_matches(raw, ranked=True)
    assert len(scored) == 4
    assert all(m["meta"]["mode"] == "Competitive" for m in scored)


def test_prepare_weekly_scored_matches_unranked_uses_swiftplay_only() -> None:
    swiftplay = [
        _norm_match(
            rounds=13,
            acs=210,
            kills=15,
            deaths=12,
            dd=10,
            hs=30,
            kast=75,
            mode="Swiftplay",
            match_id="sp1",
        ),
        _norm_match(
            rounds=13,
            acs=180,
            kills=12,
            deaths=14,
            dd=-5,
            hs=22,
            kast=70,
            mode="Swiftplay",
            match_id="sp2",
        ),
    ]
    other = [
        {
            "meta": {"id": "dm1", "mode": "Deathmatch", "rounds_played": 20},
            "metadata": {"rounds_played": 20},
            "stats": {"scorePerRound": {"value": 999}},
        },
    ]
    scored = prepare_weekly_scored_matches(TRACKER_WEEK + swiftplay + other, ranked=False)
    assert len(scored) == 2
    assert all(m["meta"]["mode"] == "Swiftplay" for m in scored)


def test_is_ranked_player() -> None:
    assert is_ranked_player("Gold 1") is True
    assert is_ranked_player("Unranked") is False
    assert is_ranked_player(None) is False
    assert is_ranked_player("0") is False
