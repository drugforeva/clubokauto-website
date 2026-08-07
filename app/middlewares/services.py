"""Проброс сервисов в обработчики.

Объекты создаются один раз при старте бота и дальше просто кладутся в data:
обработчики получают их аргументами и ничего не импортируют глобально.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ServicesMiddleware(BaseMiddleware):
    def __init__(self, services: dict[str, Any]) -> None:
        self.services = services

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data.update(self.services)
        return await handler(event, data)
