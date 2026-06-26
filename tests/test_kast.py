"""KAST calculation tests."""

import pytest

from bot.services.kast import (
    calculate_kast_from_match,
    estimate_kast_from_totals,
    resolve_kast_percent,
)


def test_estimate_kast_zero_rounds() -> None:
    assert estimate_kast_from_totals(0, 10, 5, 2) == 0.0


def test_estimate_kast_low_activity() -> None:
    # 5K / 15D / 1A / 20R — many death rounds without impact
    kast = estimate_kast_from_totals(20, 5, 15, 1)
    assert 35 <= kast <= 55


def test_estimate_kast_average_duelist() -> None:
    kast = estimate_kast_from_totals(20, 12, 12, 3)
    assert 72 <= kast <= 86


def test_estimate_kast_high_fragger() -> None:
    kast = estimate_kast_from_totals(23, 17, 13, 5)
    assert 88 <= kast <= 98


def test_estimate_kast_perfect_survival_no_deaths() -> None:
    kast = estimate_kast_from_totals(13, 0, 0, 0)
    assert kast == 100.0


def test_estimate_kast_all_deaths_no_ka() -> None:
    kast = estimate_kast_from_totals(20, 0, 20, 0)
    assert kast == 0.0


def test_estimate_kast_assists_enable_trades() -> None:
    low = estimate_kast_from_totals(20, 4, 14, 0)
    high = estimate_kast_from_totals(20, 4, 14, 6)
    assert high > low


@pytest.mark.parametrize(
    ("rounds", "kills", "deaths", "assists", "low", "high"),
    [
        (24, 8, 16, 2, 55, 72),
        (22, 14, 10, 4, 82, 98),
        (26, 20, 18, 8, 85, 98),
        (18, 3, 12, 1, 45, 58),
    ],
)
def test_estimate_kast_scenarios(
    rounds: int,
    kills: int,
    deaths: int,
    assists: int,
    low: float,
    high: float,
) -> None:
    kast = estimate_kast_from_totals(rounds, kills, deaths, assists)
    assert low <= kast <= high, f"got {kast} for {kills}/{deaths}/{assists} in {rounds}R"


def test_calculate_kast_from_rounds_kill_and_survive() -> None:
    puuid = "player-1"
    match = {
        "roundResults": [
            {
                "roundNum": 0,
                "playerStats": [
                    {
                        "subject": puuid,
                        "kills": [
                            {"killer": puuid, "victim": "enemy-1", "assistants": [], "roundTime": 1000},
                        ],
                    }
                ],
            },
            {
                "roundNum": 1,
                "playerStats": [
                    {
                        "subject": puuid,
                        "kills": [
                            {"killer": "enemy-2", "victim": puuid, "assistants": [], "roundTime": 2000},
                        ],
                    }
                ],
            },
            {
                "roundNum": 2,
                "playerStats": [
                    {
                        "subject": puuid,
                        "kills": [],
                    }
                ],
            },
        ]
    }
    assert calculate_kast_from_match(match, puuid) == 66.7


def test_calculate_kast_trade_within_five_seconds() -> None:
    puuid = "player-1"
    match = {
        "roundResults": [
            {
                "roundNum": 0,
                "playerStats": [
                    {
                        "subject": puuid,
                        "kills": [
                            {
                                "killer": "enemy-1",
                                "victim": puuid,
                                "assistants": [],
                                "roundTime": 5000,
                            },
                            {
                                "killer": "player-2",
                                "victim": "enemy-1",
                                "assistants": [],
                                "roundTime": 7000,
                            },
                        ],
                    }
                ],
            },
        ]
    }
    assert calculate_kast_from_match(match, puuid) == 100.0


def test_resolve_kast_prefers_explicit() -> None:
    value = resolve_kast_percent(
        {},
        "x",
        rounds=20,
        kills=10,
        deaths=10,
        assists=2,
        explicit=72.5,
    )
    assert value == 72.5


def test_resolve_kast_stored_estimate() -> None:
    match = {
        "meta": {"mode": "Competitive"},
        "stats": {"puuid": "abc", "kills": 8, "deaths": 16, "assists": 2},
        "teams": {"red": {"rounds_won": 13}, "blue": {"rounds_won": 10}},
    }
    value = resolve_kast_percent(
        match,
        "abc",
        rounds=23,
        kills=8,
        deaths=16,
        assists=2,
    )
    assert 54 <= value <= 72
