"""Защита от частых нажатий.

Ключ — telegram_id, храним время последнего действия в памяти процесса.
Этого достаточно для одного экземпляра бота: цель — не дать одному
человеку заспамить базу десятком нажатий в секунду, а не глобальный rate limit.
На бизнес-апдейты не ставится: архив не имеет права терять сообщения.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

MAX_KEYS = 10_000


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: float = 0.4) -> None:
        self.rate = rate
        self._seen: OrderedDict[int, float] = OrderedDict()

    def _is_throttled(self, telegram_id: int) -> bool:
        now = time.monotonic()
        last = self._seen.get(telegram_id)
        self._seen[telegram_id] = now
        self._seen.move_to_end(telegram_id)
        while len(self._seen) > MAX_KEYS:
            self._seen.popitem(last=False)
        return last is not None and (now - last) < self.rate

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = data.get("event_from_user")
        telegram_id = getattr(from_user, "id", None)
        if telegram_id is None or not self._is_throttled(int(telegram_id)):
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            # Ответить обязательно, иначе на кнопке останется вечный часик.
            await event.answer("Не так быстро 🙂")
        return None
