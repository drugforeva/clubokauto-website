"""Репозиторий диалогов."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.models.chat import Chat
from app.repositories.base import BaseRepository


class ChatRepository(BaseRepository):
    async def get(self, chat_id: int) -> Chat | None:
        return await self.session.get(Chat, chat_id)

    async def find(self, owner_id: int, telegram_chat_id: int) -> Chat | None:
        result = await self.session.execute(
            select(Chat).where(
                Chat.owner_id == owner_id,
                Chat.telegram_chat_id == telegram_chat_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, owner_id: int, chat: Any) -> Chat:
        """Найти диалог или создать и освежить подписи."""
        telegram_chat_id = int(getattr(chat, "id", 0) or 0)
        record = await self.find(owner_id, telegram_chat_id)
        chat_type = getattr(chat, "type", None)
        # aiogram отдаёт type строкой-enum, поэтому приводим к str.
        chat_type = str(chat_type) if chat_type else "private"
        title = getattr(chat, "title", None)
        username = getattr(chat, "username", None)
        first_name = getattr(chat, "first_name", None)
        last_name = getattr(chat, "last_name", None)
        if record is None:
            record = Chat(
                owner_id=owner_id,
                telegram_chat_id=telegram_chat_id,
                type=chat_type,
                title=title,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            self.session.add(record)
            await self.session.flush()
            return record
        record.type = chat_type
        record.title = title
        record.username = username
        record.first_name = first_name
        record.last_name = last_name
        return record

    async def for_owner(self, owner_id: int, limit: int = 50) -> list[Chat]:
        result = await self.session.execute(
            select(Chat)
            .where(Chat.owner_id == owner_id)
            .order_by(Chat.updated_at.desc(), Chat.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_for_owner(self, owner_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Chat.id)).where(Chat.owner_id == owner_id)
        )
        return int(result.scalar() or 0)

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(Chat.id)))
        return int(result.scalar() or 0)
