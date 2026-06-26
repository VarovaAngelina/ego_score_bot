"""Sample match payloads for tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from bot.config import MSK


def _ts(days_ago: int = 0, hour: int = 12) -> str:
    dt = datetime.now(tz=MSK) - timedelta(days=days_ago)
    dt = dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    return dt.isoformat()


SAMPLE_MATCHES = [
    {
        "metadata": {"timestamp": _ts(1)},
        "stats": {
            "scorePerRound": {"value": 250.0},
            "kDRatio": {"value": 1.5},
            "damageDelta": {"value": 35.0},
            "headshotsPercentage": {"value": 24.0},
            "kAST": {"value": 72.0},
        },
    },
    {
        "metadata": {"timestamp": _ts(2)},
        "stats": {
            "scorePerRound": {"value": 210.0},
            "kills": {"value": 18},
            "deaths": {"value": 16},
            "damage": {"value": 4200},
            "damageReceived": {"value": 3900},
            "headshots": {"value": 40},
            "shotsFired": {"value": 180},
            "kAST": {"value": 68.0},
        },
    },
]
