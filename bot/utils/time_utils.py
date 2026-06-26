"""MSK week boundaries and datetime helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from bot.config import MSK


def msk_now() -> datetime:
    """Naive MSK wall clock for MySQL DATETIME (no tz in column)."""
    return datetime.now(tz=MSK).replace(tzinfo=None)


def as_msk(value: datetime) -> datetime:
    """Normalize to MSK. Naive values from MySQL are MSK wall clock."""
    if value.tzinfo is None:
        return value.replace(tzinfo=MSK)
    return value.astimezone(MSK)


def current_week_start(today: date | None = None) -> date:
    today = today or datetime.now(tz=MSK).date()
    return today - timedelta(days=today.weekday())


def current_week_end(week_start: date | None = None) -> date:
    week_start = week_start or current_week_start()
    return week_start + timedelta(days=6)


def parse_week_argument(text: str) -> date:
    """Parse YYYY-MM-DD and return Monday of that calendar week."""
    parsed = date.fromisoformat(text.strip())
    return parsed - timedelta(days=parsed.weekday())
