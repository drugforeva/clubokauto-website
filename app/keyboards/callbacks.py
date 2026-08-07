"""Фабрики callback_data.

Telegram ограничивает callback_data 64 байтами, поэтому префиксы короткие,
а в полях лежат только числа и короткие коды. Никакие тексты пользователя
в callback_data не попадают: запрос поиска хранится в FSM.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    """Главное меню: home | history | stats | export | connect | help."""

    action: str


class HistoryCB(CallbackData, prefix="h"):
    """История: chats | list | open | media | versions | noop."""

    action: str
    scope: str = "deleted"
    page: int = 1
    message_id: int = 0
    chat_id: int = 0


class ExportCB(CallbackData, prefix="e"):
    """Экспорт: open | build."""

    action: str
    fmt: str = "txt"
    scope: str = "all"


class AdminCB(CallbackData, prefix="a"):
    """Админка: home | users | user | messages | message | media | versions | deleted | broadcast."""

    action: str
    page: int = 1
    user_id: int = 0
    message_id: int = 0
