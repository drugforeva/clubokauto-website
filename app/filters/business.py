"""Фильтр апдейтов из бизнес-чатов.

У таких сообщений всегда есть business_connection_id — именно по нему
бот отличает переписку владельца от сообщений в своём личном чате.
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject


class IsBusiness(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        return bool(getattr(event, "business_connection_id", None))
