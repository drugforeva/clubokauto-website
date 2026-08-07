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

# Варианты срока хранения архива, в днях (0 — бессрочно).
RETENTION_CHOICES: tuple[int, ...] = (0, 7, 30, 90, 180, 365)

# Домен ссылок Telegram — из него собирается ссылка на канал подписки.
TELEGRAM_HOST = "t.me"


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

    # Обязательная подписка. Пусто — проверка выключена, бот работает для всех.
    # Здесь должен быть КАНАЛ (@name или -100…), а не юзернейм самого бота,
    # и бот обязан быть администратором этого канала.
    required_channel: str = ""
    # Ссылка для кнопки «Подписаться». Для публичного канала собирается сама,
    # для закрытого (числовой id) её нужно указать вручную.
    channel_url: str = ""
    # Картинка гайда по подключению. Файла нет — гайд придёт текстом.
    guide_image: Path = Path("app/assets/connect_guide.png")

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "sohrano"
    db_password: str = "sohrano"
    db_name: str = "sohrano"
    database_url: str = ""

    # Пул подключений. Если он меньше числа одновременных апдейтов,
    # на пиках обработчики встанут в очередь за свободным соединением.
    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_timeout: int = 60
    db_pool_recycle: int = 1800

    redis_url: str = "redis://localhost:6379/0"

    media_root: Path = Path("media")
    export_root: Path = Path("exports")
    max_download_mb: int = 20
    # Сколько вложений скачиваем одновременно.
    download_concurrency: int = 4

    throttle_rate: float = 0.7
    throttle_burst: int = 5

    retention_sweep_hours: int = 6
    # Размер пачки при уборке архива.
    retention_batch_size: int = 200
    history_page_size: int = 8
    admin_page_size: int = 10
    broadcast_delay: float = 0.05

    # Ограничители исходящих. Лимиты Telegram — около 30 сообщений
    # в секунду на бота и примерно одно в секунду в один чат.
    send_rate: float = 25.0
    send_chat_interval: float = 0.35

    log_level: str = "INFO"
    sql_echo: bool = False

    @field_validator("bot_timezone")
    @classmethod
    def _clean_timezone(cls, value: str) -> str:
        return value.strip() or "UTC"

    @field_validator("required_channel")
    @classmethod
    def _clean_channel(cls, value: str) -> str:
        """Принять @name, name, t.me/name или полную ссылку — сохранить @name."""
        channel = value.strip().rstrip("/")
        if not channel:
            return ""
        if "/" in channel:
            channel = channel.rsplit("/", 1)[-1]
        if channel.startswith(("-", "@")):
            return channel
        return "@" + channel

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
    def subscription_enabled(self) -> bool:
        """Пустой канал = проверка выключена."""
        return bool(self.required_channel)

    @property
    def channel_link(self) -> str:
        """Ссылка на канал. У закрытого канала её нет — вернём пустую строку."""
        if self.channel_url:
            return self.channel_url.strip()
        channel = self.required_channel
        if channel.startswith("@"):
            return "https://" + TELEGRAM_HOST + "/" + channel[1:]
        return ""

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
