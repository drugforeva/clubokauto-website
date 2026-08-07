"""Сердце бота: апдейты Telegram Business.

Четыре типа апдейтов:
  business_connection        — подключение/отключение бота к аккаунту;
  business_message           — новое сообщение в переписке владельца;
  edited_business_message    — сообщение отредактировано;
  deleted_business_messages  — сообщения удалены (пачкой, без текста — только id).

Владелец определяется только по business_connection_id: from_user в бизнес-чате —
это автор сообщения (чаще собеседник), а не хозяин архива.
Архив ведётся всегда, а настройки влияют только на уведомления и медиа.
"""

from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message

from app.config.settings import Settings
from app.keyboards.history import notification_keyboard
from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.uow import UnitOfWork
from app.services.capture import CaptureService
from app.services.metrics import Metrics
from app.services.notifier import NotificationService
from app.services.rescue import RescueService

logger = structlog.get_logger(__name__)

router = Router(name="business")


def _can_reply(event: BusinessConnection) -> bool:
    """Совместимость с Bot API: было can_reply, стало rights.can_reply."""
    if getattr(event, "can_reply", None) is not None:
        return bool(event.can_reply)
    rights = getattr(event, "rights", None)
    return bool(getattr(rights, "can_reply", False))


async def _resolve(
    uow: UnitOfWork, connection_id: str | None
) -> tuple[User, UserSettings, int] | None:
    """Найти владельца, его настройки и чат для уведомлений."""
    if not connection_id:
        return None
    connection = await uow.connections.get(connection_id)
    if connection is None or not connection.is_enabled:
        # Апдейт по неизвестному подключению — сохранять его некуда.
        logger.info("business.unknown_connection", connection_id=connection_id)
        return None
    owner = await uow.users.get(connection.user_id)
    if owner is None:
        return None
    owner_settings = await uow.settings.get_or_create(owner.id)
    owner_chat_id = int(connection.owner_chat_id or owner.telegram_id)
    return owner, owner_settings, owner_chat_id


def _notify_allowed(owner_settings: UserSettings, is_outgoing: bool) -> bool:
    """Свои сообщения беспокоят владельца только по его желанию."""
    return owner_settings.notify_outgoing if is_outgoing else True


@router.business_connection()
async def on_business_connection(
    event: BusinessConnection,
    uow: UnitOfWork,
    settings: Settings,
    notifier: NotificationService,
) -> None:
    """Подключение бота к аккаунту или изменение его прав."""
    owner = await uow.users.get_or_create(event.user)
    owner_settings = await uow.settings.get_or_create(owner.id, settings.bot_timezone)
    owner_chat_id = int(getattr(event, "user_chat_id", 0) or owner.telegram_id)
    is_enabled = bool(getattr(event, "is_enabled", True))

    await uow.connections.upsert(
        connection_id=event.id,
        user_id=owner.id,
        owner_chat_id=owner_chat_id,
        is_enabled=is_enabled,
        can_reply=_can_reply(event),
    )
    logger.info(
        "business.connection",
        owner_id=owner.id,
        connection_id=event.id,
        enabled=is_enabled,
    )

    if is_enabled:
        text = (
            "🟢 <b>Архив включён</b>\n\n"
            "Теперь я сохраняю вашу переписку и предупреждаю, если собеседник "
            "удалит или отредактирует сообщение.\n\n"
            "Что дальше: /history — архив, /help — как это работает."
        )
    else:
        text = (
            "⚪️ <b>Архив остановлен</b>\n\n"
            "Подключение отключено, новые сообщения больше не сохраняются.\n"
            "Уже собранный архив на месте — он доступен через /history."
        )
    _ = owner_settings
    # Фиксируем подключение до отправки: если Telegram ответит ошибкой,
    # запись о подключении всё равно должна остаться в базе.
    await uow.commit()
    await notifier.send(owner_chat_id, text)


@router.business_message()
async def on_business_message(
    message: Message,
    uow: UnitOfWork,
    capture: CaptureService,
    rescue: RescueService,
    metrics: Metrics,
) -> None:
    """Новое сообщение в бизнес-чате — молча сохраняем."""
    resolved = await _resolve(uow, message.business_connection_id)
    if resolved is None:
        return
    owner, owner_settings, owner_chat_id = resolved

    sender_id = getattr(message.from_user, "id", None)
    is_outgoing = sender_id is not None and int(sender_id) == int(owner.telegram_id)

    await capture.capture_message(
        uow,
        owner=owner,
        settings=owner_settings,
        message=message,
        connection_id=message.business_connection_id,
        is_outgoing=is_outgoing,
    )
    metrics.record_capture("message")

    # Фиксируем сохранённое сообщение сразу: дальше идёт работа с сетью,
    # и держать ради неё открытую транзакцию незачем.
    await uow.commit()

    # Ответ на сообщение — единственный способ достать вложение, которого
    # Telegram не показал в самом апдейте (например, одноразовое фото).
    rescued = await rescue.rescue_from_reply(
        uow,
        owner=owner,
        settings=owner_settings,
        message=message,
        owner_chat_id=owner_chat_id,
        connection_id=message.business_connection_id,
    )
    if rescued:
        metrics.record_capture("rescue")


@router.edited_business_message()
async def on_edited_business_message(
    message: Message,
    uow: UnitOfWork,
    capture: CaptureService,
    notifier: NotificationService,
    metrics: Metrics,
) -> None:
    """Правка: сохраняем версию и показываем владельцу «было → стало»."""
    resolved = await _resolve(uow, message.business_connection_id)
    if resolved is None:
        return
    owner, owner_settings, owner_chat_id = resolved

    sender_id = getattr(message.from_user, "id", None)
    is_outgoing = sender_id is not None and int(sender_id) == int(owner.telegram_id)

    record, versions = await capture.capture_edit(
        uow,
        owner=owner,
        settings=owner_settings,
        message=message,
        connection_id=message.business_connection_id,
        is_outgoing=is_outgoing,
    )
    metrics.record_capture("edit")

    if not versions or not owner_settings.notify_edits:
        return
    if not _notify_allowed(owner_settings, bool(record.is_outgoing)):
        return
    # Сначала база, потом сеть: отправка может занять секунды, и всё это
    # время открытая транзакция держала бы соединение с базой.
    await uow.commit()
    await notifier.notify_edit(
        owner_chat_id, record, versions, notification_keyboard(record.id)
    )


@router.deleted_business_messages()
async def on_deleted_business_messages(
    event: BusinessMessagesDeleted,
    uow: UnitOfWork,
    capture: CaptureService,
    notifier: NotificationService,
    metrics: Metrics,
) -> None:
    """Удаление: Telegram даёт только id, текст берём из своего архива."""
    resolved = await _resolve(uow, event.business_connection_id)
    if resolved is None:
        return
    owner, owner_settings, owner_chat_id = resolved

    found, unknown = await capture.capture_deletions(
        uow,
        owner=owner,
        settings=owner_settings,
        chat=event.chat,
        telegram_message_ids=list(event.message_ids or []),
    )
    metrics.record_capture("deletion")

    if not owner_settings.notify_deletions:
        return

    to_notify = [
        record
        for record in found
        if _notify_allowed(owner_settings, bool(record.is_outgoing))
    ]

    # Сначала база, потом сеть: чистка переписки на стороне собеседника
    # приходит одним апдейтом на сотни сообщений.
    await uow.commit()

    if to_notify:
        # Пачка удалений сворачивается в общий список вместо сотни
        # отдельных уведомлений — иначе Telegram включит flood control.
        await notifier.notify_deletions(
            owner_chat_id, to_notify, keyboard_factory=notification_keyboard
        )

    if unknown:
        # Сообщения до подключения бота в архиве отсутствуют — честно говорим об этом.
        await notifier.notify_unknown_deletions(owner_chat_id, unknown)
