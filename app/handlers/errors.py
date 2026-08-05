"""Обработчик неперехваченных исключений.

Пользователю никогда не показывается трейсбек: он видит короткое сообщение,
а подробности уходят в лог и в счётчик ошибок.
"""

from __future__ import annotations

from typing import Any

import structlog
from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent

from app.keyboards.menu import back_to_menu
from app.services.metrics import Metrics

logger = structlog.get_logger(__name__)

router = Router(name="errors")

APOLOGY = (
    "⚠️ Что-то сломалось на моей стороне.\n\n"
    "Архив в безопасности — сохранённые сообщения не потерялись. "
    "Попробуйте ещё раз или вернитесь в меню."
)


def _describe(event: ErrorEvent) -> dict[str, Any]:
    """Собрать безопасные для лога поля об апдейте."""
    update = event.update
    payload: dict[str, Any] = {"update_id": getattr(update, "update_id", None)}
    if update.message is not None:
        payload["kind"] = "message"
        payload["user_id"] = update.message.from_user.id if update.message.from_user else None
    elif update.callback_query is not None:
        payload["kind"] = "callback_query"
        payload["data"] = update.callback_query.data
        payload["user_id"] = update.callback_query.from_user.id
    elif update.business_message is not None:
        payload["kind"] = "business_message"
    elif update.deleted_business_messages is not None:
        payload["kind"] = "deleted_business_messages"
    else:
        payload["kind"] = "other"
    return payload


@router.errors()
async def on_error(event: ErrorEvent, **data: Any) -> bool:
    """Залогировать ошибку и по возможности ответить пользователю."""
    logger.exception("update.failed", error=str(event.exception), **_describe(event))

    metrics = data.get("metrics")
    if isinstance(metrics, Metrics):
        metrics.record_error()

    update = event.update
    try:
        if update.callback_query is not None:
            await update.callback_query.answer(
                "Что-то сломалось. Попробуйте ещё раз.", show_alert=True
            )
        elif update.message is not None:
            await update.message.answer(APOLOGY, reply_markup=back_to_menu())
    except TelegramAPIError as exc:
        # Не смогли даже извиниться — запишем и идём дальше.
        logger.warning("update.apology_failed", error=str(exc))

    # True говорит aiogram, что ошибка обработана и поллинг продолжается.
    return True
