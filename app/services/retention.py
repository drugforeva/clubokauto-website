"""Автоматическая уборка архива по сроку хранения.

Фоновая задача запускается при старте бота. Свою сессию берёт из фабрики,
а не из middleware: у фоновой задачи нет апдейта и нет чужой транзакции.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.settings import UserSettings
from app.repositories.uow import UnitOfWork
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.services.storage import MediaStorage

logger = structlog.get_logger(__name__)

#: Сколько файлов удалять за один шаг.
DEFAULT_BATCH_SIZE = 200


class RetentionService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: MediaStorage,
        sweep_hours: int = 6,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage
        self.sweep_hours = max(sweep_hours, 1)
        self.batch_size = max(batch_size, 1)

    def _remove_files(self, paths: list[str]) -> None:
        """Синхронное удаление — выполняется в отдельном потоке."""
        for path in paths:
            self.storage.remove(path)

    async def _remove_chunk(self, paths: list[str]) -> None:
        """Удалить пачку файлов, не блокируя цикл событий."""
        if paths:
            await asyncio.to_thread(self._remove_files, paths)

    async def sweep(self) -> int:
        """Один проход уборки. Возвращает число удалённых сообщений."""
        removed = 0
        async with self.session_factory() as session:
            uow = UnitOfWork(session)
            result = await session.execute(
                select(UserSettings).where(UserSettings.retention_days > 0)
            )
            for record in result.scalars().all():
                cutoff = utcnow() - timedelta(days=record.retention_days)
                # Сначала собираем пути: после DELETE строки media уже не найти.
                paths = await uow.media.downloaded_paths_before(record.user_id, cutoff)
                deleted = await uow.messages.delete_older_than(record.user_id, cutoff)
                # Коммит после каждого владельца: один общий на весь проход
                # держал блокировки всё время уборки.
                await session.commit()
                for start in range(0, len(paths), self.batch_size):
                    await self._remove_chunk(paths[start : start + self.batch_size])
                removed += deleted
            if session.in_transaction():
                await session.commit()
        if removed:
            logger.info("retention.sweep", removed=removed)
        return removed

    async def run_forever(self) -> None:
        """Цикл уборки. Ошибка одного прохода не должна гасить задачу."""
        interval = self.sweep_hours * 3600
        while True:
            try:
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - фоновая задача должна жить
                logger.warning("retention.sweep_failed", error=str(error))
            await asyncio.sleep(interval)
