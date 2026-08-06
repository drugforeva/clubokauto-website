"""Репозиторий версий текста."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.models.edit import MessageEdit
from app.repositories.base import BaseRepository


class EditRepository(BaseRepository):
    async def add(
        self,
        *,
        message_id: int,
        version: int,
        text: str | None,
        edited_at: datetime,
    ) -> MessageEdit:
        record = MessageEdit(
            message_id=message_id,
            version=version,
            text=text,
            edited_at=edited_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def for_message(self, message_id: int) -> list[MessageEdit]:
        result = await self.session.execute(
            select(MessageEdit)
            .where(MessageEdit.message_id == message_id)
            .order_by(MessageEdit.version)
        )
        return list(result.scalars().all())

    async def next_version(self, message_id: int) -> int:
        """Номер следующей версии (версия 1 — исходный текст)."""
        result = await self.session.execute(
            select(func.coalesce(func.max(MessageEdit.version), 0)).where(
                MessageEdit.message_id == message_id
            )
        )
        return int(result.scalar() or 0) + 1

    async def count_for_message(self, message_id: int) -> int:
        result = await self.session.execute(
            select(func.count(MessageEdit.id)).where(MessageEdit.message_id == message_id)
        )
        return int(result.scalar() or 0)
