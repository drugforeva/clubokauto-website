"""Конфигурация из окружения / .env через pydantic-settings.

DEFAULT_ADMIN_IDS — владелец бота, прописанный в коде. Константа
подставляется, если BOT_ADMIN_IDS отсутствует или пуст, поэтому доступ
к /admin не теряется при копировании .env.example.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# >>> ПОДСТАВЬТЕ СВОЙ TELEGRAM ID (узнать: @userinfobot) <<<
DEFAULT_ADMIN_IDS: tuple[int, ...] = (123456789,)

# Варианты срока хранения в /settings, в днях (0 — бессрочно).
RETENTION_CHOICES: tuple[int, ...] = (0, 7, 30, 90, 180, 365)


class Settings(BaseSettings):
    """Все настройки приложения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = ""
    bot_timezone: str = "Europe/Moscow"
    # Строкой, а не списком: pydantic-settings ждёт JSON для сложных типов,
    # а в .env удобнее писать «111,222».
    bot_admin_ids: str = ""

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "sohrano"
    db_password: str = "sohrano"
    db_name: str = "sohrano"
    database_url: str = ""

    redis_url: str = "redis://localhost:6379/0"

    media_root: Path = Path("media")
    export_root: Path = Path("exports")
    max_download_mb: int = 20

    throttle_rate: float = 0.7
    throttle_burst: int = 5

    retention_sweep_hours: int = 6
    history_page_size: int = 8
    admin_page_size: int = 10
    broadcast_delay: float = 0.05

    log_level: str = "INFO"
    sql_echo: bool = False

    @field_validator("bot_timezone")
    @classmethod
    def _clean_timezone(cls, value: str) -> str:
        return value.strip() or "UTC"

    @property
    def sqlalchemy_url(self) -> str:
        """DSN для SQLAlchemy: готовый DATABASE_URL или сборка из DB_*."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def admin_ids(self) -> tuple[int, ...]:
        raw = self.bot_admin_ids.replace(";", ",").replace(" ", ",")
        parsed = tuple(
            int(chunk) for chunk in raw.split(",") if chunk and chunk.lstrip("-").isdigit()
        )
        return parsed or DEFAULT_ADMIN_IDS

    @property
    def max_download_bytes(self) -> int:
        return self.max_download_mb * 1024 * 1024

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_url.startswith("sqlite")

    def is_admin(self, telegram_id: int | None) -> bool:
        return telegram_id is not None and telegram_id in self.admin_ids


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Единственный экземпляр настроек на процесс."""
    return Settings()


def reset_settings_cache() -> None:
    """Сбросить кэш — нужно run_local.py и тестам."""
    get_settings.cache_clear()
