"""Rank delta unit tests."""

from bot.services.rank_delta import (
    compute_rank_delta,
    compute_rank_deltas_since_last_refresh,
)


def test_compute_rank_delta_improved() -> None:
    assert compute_rank_delta(10, 7) == 3


def test_compute_rank_delta_declined() -> None:
    assert compute_rank_delta(3, 8) == -5


def test_compute_rank_delta_no_reference() -> None:
    assert compute_rank_delta(None, 1) == 0


def test_compute_rank_deltas_since_last_refresh_first_run() -> None:
    deltas, refs = compute_rank_deltas_since_last_refresh({}, [1, 2, 3])
    assert deltas == {1: 0, 2: 0, 3: 0}
    assert refs == {1: 1, 2: 2, 3: 3}


def test_compute_rank_deltas_since_last_refresh_second_run() -> None:
    reference = {1: 1, 2: 2, 3: 3}
    order = [2, 1, 3]
    deltas, refs = compute_rank_deltas_since_last_refresh(reference, order)
    assert deltas[1] == -1
    assert deltas[2] == 1
    assert deltas[3] == 0
    assert refs == {1: 2, 2: 1, 3: 3}
