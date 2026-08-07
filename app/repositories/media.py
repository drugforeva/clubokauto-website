"""Репозиторий вложений."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.models.media import Media
from app.models.message import Message
from app.repositories.base import BaseRepository
from app.utils.time import utcnow


class MediaRepository(BaseRepository):
    async def add_many(self, items: list[Media]) -> list[Media]:
        if not items:
            return []
        self.session.add_all(items)
        await self.session.flush()
        return items

    async def for_message(self, message_id: int) -> list[Media]:
        result = await self.session.execute(
            select(Media).where(Media.message_id == message_id).order_by(Media.id)
        )
        return list(result.scalars().all())

    async def get(self, media_id: int) -> Media | None:
        return await self.session.get(Media, media_id)

    async def mark_downloaded(self, media: Media, local_path: str) -> Media:
        media.local_path = local_path
        media.downloaded_at = utcnow()
        return media

    async def count_for_owner(self, owner_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Media.id))
            .join(Message, Message.id == Media.message_id)
            .where(Message.owner_id == owner_id)
        )
        return int(result.scalar() or 0)

    async def stored_bytes(self, owner_id: int) -> int:
        """Суммарный размер скачанных файлов — только тех, что лежат на диске."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(Media.file_size), 0))
            .join(Message, Message.id == Media.message_id)
            .where(Message.owner_id == owner_id, Media.local_path.is_not(None))
        )
        return int(result.scalar() or 0)

    async def downloaded_paths_before(self, owner_id: int, cutoff: datetime) -> list[str]:
        """Пути файлов, которые пора удалить вместе с сообщениями владельца."""
        result = await self.session.execute(
            select(Media.local_path)
            .join(Message, Message.id == Media.message_id)
            .where(
                Media.local_path.is_not(None),
                Message.owner_id == owner_id,
                Message.sent_at < cutoff,
            )
        )
        return [str(row[0]) for row in result.all() if row[0]]

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count(Media.id)))
        return int(result.scalar() or 0)
