"""Точка входа: логи, база, Redis, поллинг и фоновая уборка.

Запуск: `python -m app`.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
from contextlib import suppress
from typing import Any

import structlog
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot import (
    ALLOWED_UPDATES,
    build_bot,
    build_dispatcher,
    build_services,
    setup_commands,
)
from app.config import Settings, get_settings
from app.database import build_engine, build_redis, build_session_factory, ping
from app.services import RetentionService

logger = structlog.get_logger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """Один формат логов для structlog и стандартного logging."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric)
    # aiogram слишком болтлив на DEBUG — его логгер держим на INFO.
    logging.getLogger("aiogram.event").setLevel(max(numeric, logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        cache_logger_on_first_use=True,
    )


async def build_storage(settings: Settings) -> tuple[BaseStorage, Any]:
    """FSM-хранилище. Без живого Redis бот всё равно должен запуститься."""
    redis = build_redis(settings)
    if await ping(redis):
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage(redis=redis), redis
    logger.warning("redis.unavailable", url=settings.redis_url)
    return MemoryStorage(), redis


async def _close(client: Any) -> None:
    """Аккуратно закрыть клиент Redis любой версии."""
    closer = getattr(client, "aclose", None) or getattr(client, "close", None)
    if closer is None:
        return
    with suppress(Exception):
        result = closer()
        if inspect.isawaitable(result):
            await result


async def run() -> None:
    """Собрать всё и начать поллинг до остановки."""
    settings = get_settings()
    setup_logging(settings.log_level)

    settings.media_root.mkdir(parents=True, exist_ok=True)

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    storage, redis = await build_storage(settings)

    bot = build_bot(settings)
    services = build_services(
        bot=bot, settings=settings, session_factory=session_factory
    )
    dispatcher = build_dispatcher(
        settings=settings,
        session_factory=session_factory,
        services=services,
        storage=storage,
    )

    retention: RetentionService = services["retention"]
    sweeper = asyncio.create_task(retention.run_forever(), name="retention")

    try:
        me = await bot.get_me()
        logger.info(
            "bot.starting",
            username=me.username,
            admins=len(settings.admin_ids),
            timezone=settings.bot_timezone,
        )
        await setup_commands(bot, settings)
        # Очередь не сбрасываем: за время рестарта могли прийти удаления,
        # а ради них бот и существует. Telegram хранит апдейты сутки.
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot, allowed_updates=list(ALLOWED_UPDATES))
    finally:
        sweeper.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper
        await bot.session.close()
        await engine.dispose()
        await _close(redis)
        logger.info("bot.stopped")


def main() -> None:
    """Синхронная обёртка для консоли и Docker."""
    with suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(run())


if __name__ == "__main__":
    main()
