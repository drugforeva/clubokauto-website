"""Репозиторий событий удаления."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.models.deleted_message import DeletedMessage
from app.repositories.base import BaseRepository


class DeletedMessageRepository(BaseRepository):
    async def add(
        self,
        *,
        owner_id: int,
        message_id: int | None,
        chat_id: int | None,
        telegram_message_id: int | None,
        notified: bool,
    ) -> DeletedMessage:
        record = DeletedMessage(
            owner_id=owner_id,
            message_id=message_id,
            chat_id=chat_id,
            telegram_message_id=telegram_message_id,
            notified=notified,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def recent(self, owner_id: int, limit: int = 10) -> list[DeletedMessage]:
        result = await self.session.execute(
            select(DeletedMessage)
            .where(DeletedMessage.owner_id == owner_id)
            .order_by(DeletedMessage.detected_at.desc(), DeletedMessage.id.desc())
            .limit(limit)
        )
        return list(result.scalars().unique().all())

    async def recent_any_owner(self, limit: int = 10) -> list[DeletedMessage]:
        """События всех владельцев.

        Сознательно обходит изоляцию по owner_id, поэтому вызывается только из
        админ-роутера, закрытого фильтром IsAdmin.
        """
        result = await self.session.execute(
            select(DeletedMessage)
            .order_by(DeletedMessage.detected_at.desc(), DeletedMessage.id.desc())
            .limit(limit)
        )
        return list(result.scalars().unique().all())

    async def count_for_owner(self, owner_id: int) -> int:
        result = await self.session.execute(
            select(func.count(DeletedMessage.id)).where(DeletedMessage.owner_id == owner_id)
        )
        return int(result.scalar() or 0)

    async def count_since(self, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count(DeletedMessage.id)).where(DeletedMessage.detected_at >= since)
        )
        return int(result.scalar() or 0)

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count(DeletedMessage.id)))
        return int(result.scalar() or 0)
