"""ScoreService unit tests."""

import pytest

from bot.database.models import PlayerStats
from bot.services.score_service import FALLBACK_BOUNDS, ScoreService, STAT_ACS


@pytest.fixture
def scorer() -> ScoreService:
    return ScoreService()


def test_normalize_midpoint(scorer: ScoreService) -> None:
    assert scorer.normalize(200.0, 50.0, 350.0) == pytest.approx(0.5)


def test_normalize_clamped_range(scorer: ScoreService) -> None:
    assert scorer.normalize(50.0, 50.0, 350.0) == pytest.approx(0.0)
    assert scorer.normalize(400.0, 50.0, 350.0) == pytest.approx(1.166, rel=1e-2)


def test_normalize_equal_bounds_returns_half(scorer: ScoreService) -> None:
    assert scorer.normalize(100.0, 100.0, 100.0) == 0.5


def test_all_minimums_score_zero(scorer: ScoreService) -> None:
    stats = PlayerStats(
        acs=50.0,
        kd_ratio=0.3,
        damage_delta=-80.0,
        hs_percent=10.0,
        kast_percent=90.0,
    )
    result = scorer.calculate(stats)
    assert result.ego_score == 0.0


def test_all_maximums_score(scorer: ScoreService) -> None:
    stats = PlayerStats(
        acs=350.0,
        kd_ratio=3.0,
        damage_delta=120.0,
        hs_percent=45.0,
        kast_percent=30.0,
    )
    result = scorer.calculate(stats)
    # 0.30 + 0.25 + 0.20 + 0.15 - 0 = 0.90 -> 90.0
    assert result.ego_score == 90.0
    assert result.contrib_acs == 30.0
    assert result.contrib_kast == 0.0


def test_high_kast_reduces_score(scorer: ScoreService) -> None:
    low_kast = PlayerStats(200.0, 1.5, 20.0, 25.0, 40.0)
    high_kast = PlayerStats(200.0, 1.5, 20.0, 25.0, 90.0)
    assert scorer.calculate(low_kast).ego_score > scorer.calculate(high_kast).ego_score


def test_negative_damage_delta(scorer: ScoreService) -> None:
    stats = PlayerStats(acs=150.0, kd_ratio=1.0, damage_delta=-40.0, hs_percent=20.0, kast_percent=70.0)
    result = scorer.calculate(stats)
    assert 0.0 <= result.ego_score <= 100.0
    assert result.contrib_dd < scorer.calculate(
        PlayerStats(150.0, 1.0, 120.0, 20.0, 70.0)
    ).contrib_dd


def test_clip_prevents_above_100(scorer: ScoreService) -> None:
    stats = PlayerStats(acs=500.0, kd_ratio=5.0, damage_delta=200.0, hs_percent=60.0, kast_percent=10.0)
    result = scorer.calculate(stats)
    assert result.ego_score == 100.0


def test_expand_bounds(scorer: ScoreService) -> None:
    stats = PlayerStats(400.0, 1.0, 0.0, 25.0, 70.0)
    bounds = dict(FALLBACK_BOUNDS)
    expanded = scorer.expand_bounds(stats, bounds)
    assert expanded[STAT_ACS].max_val == 400.0


def test_needs_bounds_update(scorer: ScoreService) -> None:
    stats = PlayerStats(400.0, 1.0, 0.0, 25.0, 70.0)
    assert scorer.needs_bounds_update(stats) is True
    assert scorer.needs_bounds_update(
        PlayerStats(200.0, 1.5, 20.0, 25.0, 70.0)
    ) is False
