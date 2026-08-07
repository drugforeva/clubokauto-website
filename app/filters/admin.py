"""Фильтр админа.

Список админов берётся из контекста (его кладёт ServicesMiddleware), а если
фильтр вызван вне обычного потока — из настроек напрямую.
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.config.settings import Settings, get_settings


class IsAdmin(BaseFilter):
    async def __call__(
        self, event: TelegramObject, settings: Settings | None = None
    ) -> bool:
        user = getattr(event, "from_user", None)
        telegram_id = getattr(user, "id", None)
        if telegram_id is None:
            return False
        config = settings or get_settings()
        return config.is_admin(int(telegram_id))
