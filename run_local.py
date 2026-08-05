"""Локальный запуск без Postgres и Redis.

База — sqlite в файле рядом с проектом, FSM — fakeredis в памяти.
Нужен только BOT_TOKEN: из файла .env в корне проекта либо из переменной
окружения. Схема создаётся напрямую, без alembic — для боевого запуска
этот файл не годится.

    python run_local.py

Грабля: проверять токен через os.environ нельзя — в .env он есть, а в окружении
его нет. Фаи́л .env читает pydantic-settings, поэтому проверка идёт по Settings.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./sohrano_local.db")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("MEDIA_ROOT", "media_local")
os.environ.setdefault("LOG_LEVEL", "INFO")

import app.models  # noqa: E402, F401 - регистрация моделей в Base.metadata
from app.config import Settings, get_settings, reset_settings_cache  # noqa: E402
from app.database import Base, build_engine  # noqa: E402

TOKEN_HELP = """Нужен BOT_TOKEN — бот без токена не запустится.

Вариант 1 — файл .env в корне проекта, одна строка без кавычек и без пробелов:
    BOT_TOKEN=123456:AA...
Проверьте, что файл называется именно .env, а не .env.txt.

Вариант 2 — переменная окружения:
    macOS / Linux:  BOT_TOKEN=123456:AA... python run_local.py
    PowerShell:     $env:BOT_TOKEN="123456:AA..."; python run_local.py
    cmd.exe:        set BOT_TOKEN=123456:AA... && python run_local.py"""


def load_settings() -> Settings:
    """Прочитать настройки и понятно объяснить, чего не хватает."""
    reset_settings_cache()
    settings = get_settings()
    if settings.bot_token.strip():
        return settings

    env_file = Path(".env")
    lines = [TOKEN_HELP, "", f"Рабочая папка: {Path.cwd()}"]
    if env_file.exists():
        lines.append(f"Файл .env найден ({env_file.resolve()}), но BOT_TOKEN в нём пуст.")
    else:
        lines.append(
            f"Файл .env в этой папке не найден. Запускать надо из корня проекта "
            f"(там лежат app/ и pyproject.toml)."
        )
    raise SystemExit("\n".join(lines))


async def prepare_schema(settings: Settings) -> None:
    """Создать таблицы, если их ещё нет."""
    engine = build_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print(f"База готова: {settings.sqlalchemy_url}")


def main() -> None:
    settings = load_settings()
    asyncio.run(prepare_schema(settings))

    from app.main import main as run_bot

    run_bot()


if __name__ == "__main__":
    main()
