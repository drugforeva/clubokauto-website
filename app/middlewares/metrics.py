"""Счётчики апдейтов и ошибок.

Ставится самым внешним слоем, чтобы видеть все апдейты, включая те,
где падение случилось до обработчика.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.services.metrics import Metrics


class MetricsMiddleware(BaseMiddleware):
    def __init__(self, metrics: Metrics) -> None:
        self.metrics = metrics

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        kind = "unknown"
        if isinstance(event, Update):
            kind = event.event_type
        self.metrics.record_update(kind)
        try:
            return await handler(event, data)
        except Exception:
            self.metrics.record_error(kind)
            raise
