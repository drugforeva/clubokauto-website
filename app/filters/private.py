"""Фильтр личного чата с ботом.

Команды и меню имеют смысл только в личном диалоге: в бизнес-чатах бот
ничего не отвечает и ведёт себя как невидимый архиватор.
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject


class IsPrivate(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        chat = getattr(event, "chat", None)
        if chat is None:
            # У callback_query чат лежит внутри прикреплённого сообщения.
            chat = getattr(getattr(event, "message", None), "chat", None)
        if chat is None:
            return False
        if getattr(event, "business_connection_id", None):
            return False
        return getattr(chat, "type", None) == "private"
