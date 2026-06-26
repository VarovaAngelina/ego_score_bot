"""Config loading tests."""

import os

import pytest

from bot.config import Settings


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("DISCORD_GUILD_ID", "123456789")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("ANNOUNCE_CHANNEL_ID", "")

    settings = Settings()

    assert settings.discord_token == "test-token"
    assert settings.discord_guild_id == 123456789
    assert settings.announce_channel_id == 0
    assert settings.cache_ttl_minutes == 30
