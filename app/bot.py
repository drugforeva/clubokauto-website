"""Сборка бота: сервисы, middleware, роутеры, список команд.

Файл намеренно не запускает поллинг: тесты и run_local.py собирают тот же
Dispatcher без сети. Запуском занимается app/main.py.
"""

from __future__ import annotations

from typing import Any

import structlog
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import business
from app.config import Settings
from app.filters import IsPrivate
from app.handlers import PRIVATE_ROUTERS, errors
from app.middlewares import (
    DatabaseMiddleware,
    MetricsMiddleware,
    ServicesMiddleware,
    SubscriptionMiddleware,
    ThrottlingMiddleware,
    UserMiddleware,
)
from app.services import (
    BroadcastService,
    CaptureService,
    ExportService,
    FileDownloader,
    MediaStorage,
    Metrics,
    NotificationService,
    RescueService,
    RetentionService,
    StatsService,
)

logger = structlog.get_logger(__name__)

#: Без бизнес-апдейтов в этом списке Telegram их просто не пришлёт.
ALLOWED_UPDATES: tuple[str, ...] = (
    "message",
    "edited_message",
    "callback_query",
    "my_chat_member",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
)

COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Меню"),
    BotCommand(command="connect", description="Как подключить бота"),
    BotCommand(command="history", description="Архив сообщений"),
    BotCommand(command="stats", description="Статистика"),
    BotCommand(command="export", description="Выгрузить файлом"),
    BotCommand(command="help", description="Как это работает"),
)

ADMIN_COMMANDS: tuple[BotCommand, ...] = (
    *COMMANDS,
    BotCommand(command="admin", description="Админ-панель"),
)


def build_bot(settings: Settings) -> Bot:
    """Клиент Telegram с HTML-разметкой по умолчанию."""
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )


def build_services(
    *,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    metrics: Metrics | None = None,
) -> dict[str, Any]:
    """Собрать все сервисы один раз за жизнь процесса.

    Ключи словаря — это имена аргументов в обработчиках: aiogram подставит
    их по совпадению имени.
    """
    metrics = metrics or Metrics()
    storage = MediaStorage(settings.media_root)
    downloader = FileDownloader(
        bot,
        storage,
        settings.max_download_bytes,
        max_concurrency=settings.download_concurrency,
    )
    notifier = NotificationService(
        bot,
        rate=settings.send_rate,
        chat_interval=settings.send_chat_interval,
    )
    capture = CaptureService(downloader=downloader)
    return {
        "settings": settings,
        "metrics": metrics,
        "storage": storage,
        "downloader": downloader,
        "notifier": notifier,
        "capture": capture,
        # Спасение по ответу пишет в тот же архив и шлёт файл владельцу.
        "rescue": RescueService(capture, notifier),
        "export_service": ExportService(),
        "stats": StatsService(),
        "broadcast": BroadcastService(notifier, delay=settings.broadcast_delay),
        "retention": RetentionService(
            session_factory,
            storage,
            sweep_hours=settings.retention_sweep_hours,
            batch_size=settings.retention_batch_size,
        ),
    }


def build_private_router(settings: Settings) -> Router:
    """Роутер личного диалога.

    UserMiddleware и троттлинг вешаются именно здесь, а не на весь
    Dispatcher: в бизнес-чате from_user — собеседник, и регистрировать его
    как владельца нельзя, а архивацию нельзя тормозить троттлингом.
    """
    router = Router(name="private")
    router.message.filter(IsPrivate())
    router.callback_query.filter(IsPrivate())

    # Канал обязательной подписки берётся из настроек, а не из константы в коде.
    sub = SubscriptionMiddleware(settings)
    router.message.middleware(sub)
    router.callback_query.middleware(sub)
    router.message.middleware(UserMiddleware())
    router.callback_query.middleware(UserMiddleware())
    router.message.middleware(ThrottlingMiddleware(rate=settings.throttle_rate))
    router.callback_query.middleware(ThrottlingMiddleware(rate=settings.throttle_rate))

    router.include_routers(*PRIVATE_ROUTERS)
    return router


def build_dispatcher(
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    services: dict[str, Any],
    storage: BaseStorage | None = None,
) -> Dispatcher:
    """Собрать Dispatcher со всей обвязкой."""
    dispatcher = Dispatcher(storage=storage or MemoryStorage())

    # Самый внешний слой — метрики: они видят даже апдейты, упавшие до хендлера.
    dispatcher.update.outer_middleware(MetricsMiddleware(services["metrics"]))
    dispatcher.update.outer_middleware(DatabaseMiddleware(session_factory))
    dispatcher.update.outer_middleware(ServicesMiddleware(services))

    # Бизнес-роутер выше личного: его апдейты никогда не должны ждать очереди.
    dispatcher.include_router(business.router)
    dispatcher.include_router(build_private_router(settings))
    dispatcher.include_router(errors.router)

    dispatcher["settings"] = settings
    return dispatcher


async def setup_commands(bot: Bot, settings: Settings) -> None:
    """Зарегистрировать меню команд: общее и расширенное для админов."""
    await bot.set_my_commands(list(COMMANDS))
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(
                list(ADMIN_COMMANDS), scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception as exc:  # noqa: BLE001 - админ мог не начать диалог с ботом
            logger.warning("commands.admin_failed", admin_id=admin_id, error=str(exc))
