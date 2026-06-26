"""Environment loading (.env), constants, MSK timezone configuration."""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MSK = ZoneInfo("Europe/Moscow")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_token: str
    discord_guild_id: int
    announce_channel_id: int = 0
    guide_channel_id: int = 0
    top_channel_id: int = 0

    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "ego_score_db"
    db_user: str = "ego_bot"
    db_password: str

    cache_ttl_minutes: int = 30
    batch_size: int = 10
    request_delay_min: float = 2.0
    request_delay_max: float = 5.0
    henrik_api_key: str = ""
    top_limit: int = 10

    tz: str = "Europe/Moscow"
    log_level: str = "INFO"

    @field_validator("announce_channel_id", mode="before")
    @classmethod
    def empty_announce_to_zero(cls, value: object) -> object:
        if value == "" or value is None:
            return 0
        return value

    @field_validator("guide_channel_id", mode="before")
    @classmethod
    def empty_guide_to_zero(cls, value: object) -> object:
        if value == "" or value is None:
            return 0
        return value

    @field_validator("top_channel_id", mode="before")
    @classmethod
    def empty_top_to_zero(cls, value: object) -> object:
        if value == "" or value is None:
            return 0
        return value

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def announce_enabled(self) -> bool:
        return self.announce_channel_id > 0

    @property
    def guide_enabled(self) -> bool:
        return self.guide_channel_id > 0

    @property
    def live_top_enabled(self) -> bool:
        return self.top_channel_id > 0 or self.announce_channel_id > 0


@lru_cache
def get_settings() -> Settings:
    return Settings()
