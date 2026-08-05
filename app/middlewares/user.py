"""Регистрация владельца и его настроек.

Ставится только на личные апдейты. В бизнес-чате from_user — это собеседник,
а не владелец аккаунта, и создавать для него пользователя нельзя: владелец
вычисляется по business_connection_id в бизнес-роутере.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.utils.time import utcnow


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        uow = data.get("uow")
        from_user = data.get("event_from_user")
        if uow is None or from_user is None or getattr(from_user, "is_bot", False):
            return await handler(event, data)

        user = await uow.users.get_or_create(from_user)
        user.last_seen_at = utcnow()
        if user.is_blocked:
            # Человек вернулся и сам нам пишет — снимаем метку блокировки.
            user.is_blocked = False

        settings = data.get("settings")
        default_timezone = getattr(settings, "bot_timezone", None)
        user_settings = await uow.settings.get_or_create(user.id, default_timezone)

        data["user"] = user
        data["user_settings"] = user_settings
        return await handler(event, data)
