"""MSK datetime helper tests."""

from datetime import datetime, timezone

from bot.config import MSK
from bot.utils.formatters import format_msk_datetime
from bot.utils.time_utils import as_msk, msk_now


def test_as_msk_naive_is_wall_clock() -> None:
    naive = datetime(2026, 6, 25, 14, 32)
    assert as_msk(naive).hour == 14
    assert as_msk(naive).tzinfo == MSK


def test_as_msk_converts_utc() -> None:
    utc = datetime(2026, 6, 25, 7, 26, tzinfo=timezone.utc)
    assert as_msk(utc).hour == 10


def test_format_msk_datetime_from_naive_db_value() -> None:
    assert format_msk_datetime(datetime(2026, 6, 25, 14, 32)) == "14:32"


def test_msk_now_is_naive() -> None:
    now = msk_now()
    assert now.tzinfo is None
    assert 0 <= now.hour <= 23
