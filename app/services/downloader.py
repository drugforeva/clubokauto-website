"""Скачивание вложений на диск.

Включается только флагом download_media в /settings: file_id живёт, пока файл
есть на серверах Telegram, а диск забивается моментально.
Лимит Bot API на getFile — 20 МБ, поэтому большие файлы просто пропускаем.
"""

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.business.extractor import MediaPayload
    from app.services.storage import MediaStorage

logger = structlog.get_logger(__name__)


#: Сколько вложений скачиваем одновременно.
DEFAULT_CONCURRENCY = 4


class FileDownloader:
    def __init__(self, bot: Any, storage: MediaStorage, max_bytes: int, max_concurrency: int = DEFAULT_CONCURRENCY) -> None:
        self.bot = bot
        self.storage = storage
        self.max_bytes = max_bytes
        self._semaphore = asyncio.Semaphore(max(max_concurrency, 1))

    async def download(
        self, *, owner_telegram_id: int, payload: MediaPayload
    ) -> str | None:
        """Скачать файл. Ошибка не должна ломать захват сообщения."""
        async with self._semaphore:
                    if not payload.file_id:
                        return None
                    size = payload.file_size or 0
                    if size and size > self.max_bytes:
                        logger.info(
                            "media.skip_oversized",
                            media_type=payload.media_type,
                            file_size=size,
                            limit=self.max_bytes,
                        )
                        return None
                    try:
                        file = await self.bot.get_file(payload.file_id)
                        remote_size = int(getattr(file, "file_size", 0) or 0)
                        if remote_size and remote_size > self.max_bytes:
                            return None
                        destination = self.storage.build_path(
                            owner_telegram_id=owner_telegram_id,
                            media_type=payload.media_type,
                            file_unique_id=payload.file_unique_id,
                            file_name=payload.file_name,
                        )
                        await self.bot.download_file(file.file_path, destination=destination)
                    except Exception as error:  # noqa: BLE001 - сеть и диск непредсказуемы
                        logger.warning(
                            "media.download_failed",
                            media_type=payload.media_type,
                            error=str(error),
                        )
                        return None
                    return str(destination)
