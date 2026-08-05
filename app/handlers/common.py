"""Общие помощники обработчиков."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

from app.repositories.messages import MessageFilters

SCOPE_TITLES: dict[str, str] = {
    "all": "все сообщения",
    "deleted": "удалённые",
    "edited": "изменённые",
}


async def show(
    query: CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    """Перерисовать экран под кнопкой.

    Повторное нажатие той же кнопки даёт тот же текст, а Telegram на это отвечает
    ошибкой «message is not modified». Для пользователя это не ошибка, поэтому
    глотаем только её, а остальные проблемы прокидываем выше.
    """
    message = query.message
    if message is None:
        return
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


def scope_filters(owner_id: int, scope: str = "all") -> MessageFilters:
    """Фильтры для быстрых режимов истории и экспорта."""
    return MessageFilters(
        owner_id=owner_id,
        only_deleted=scope == "deleted",
        only_edited=scope == "edited",
    )


def scope_title(scope: str) -> str:
    return SCOPE_TITLES.get(scope, SCOPE_TITLES["all"])
