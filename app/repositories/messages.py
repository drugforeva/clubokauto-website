"""Репозиторий сообщений: выборки истории, поиск, статистика, уборка."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.sql import ColumnElement

from app.models.chat import Chat
from app.models.message import Message
from app.repositories.base import BaseRepository
from app.utils.time import utcnow


@dataclass(slots=True)
class MessageFilters:
    """Условия выборки. Все поля комбинируются через AND."""

    owner_id: int
    query: str | None = None
    sender: str | None = None
    chat_id: int | None = None
    content_type: str | None = None
    only_deleted: bool = False
    only_edited: bool = False
    include_outgoing: bool = True
    date_from: datetime | None = None
    date_to: datetime | None = None

    @property
    def is_active(self) -> bool:
        return any(
            (
                self.query,
                self.sender,
                self.chat_id,
                self.content_type,
                self.only_deleted,
                self.only_edited,
                not self.include_outgoing,
                self.date_from,
                self.date_to,
            )
        )

    def describe(self) -> str:
        """Сводка активных условий для экрана поиска."""
        parts: list[str] = []
        if self.query:
            parts.append(f"текст «{self.query}»")
        if self.sender:
            parts.append(f"автор {self.sender}")
        if self.content_type:
            parts.append(f"тип {self.content_type}")
        if self.only_deleted:
            parts.append("только удалённые")
        if self.only_edited:
            parts.append("только изменённые")
        if not self.include_outgoing:
            parts.append("без своих")
        if self.date_from:
            parts.append(f"с {self.date_from:%d.%m.%Y}")
        if self.date_to:
            parts.append(f"по {self.date_to:%d.%m.%Y}")
        return ", ".join(parts) if parts else "без условий"


class MessageRepository(BaseRepository):
    async def add(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.flush()
        return message

    async def get(self, owner_id: int, message_id: int) -> Message | None:
        """Получить сообщение с проверкой владельца — изоляция данных."""
        result = await self.session.execute(
            select(Message).where(Message.id == message_id, Message.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def get_any_owner(self, message_id: int) -> Message | None:
        """Без фильтра по владельцу. Вызывать только из админ-роутера."""
        result = await self.session.execute(select(Message).where(Message.id == message_id))
        return result.scalar_one_or_none()

    async def find_by_telegram_id(
        self, owner_id: int, chat_id: int, telegram_message_id: int
    ) -> Message | None:
        result = await self.session.execute(
            select(Message).where(
                Message.owner_id == owner_id,
                Message.chat_id == chat_id,
                Message.telegram_message_id == telegram_message_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_in_chat_ids(
        self, owner_id: int, chat_ids: list[int], telegram_message_ids: list[int]
    ) -> list[Message]:
        """Пачка сообщений по списку telegram-id — удаления приходят пачкой."""
        if not chat_ids or not telegram_message_ids:
            return []
        result = await self.session.execute(
            select(Message).where(
                Message.owner_id == owner_id,
                Message.chat_id.in_(chat_ids),
                Message.telegram_message_id.in_(telegram_message_ids),
            )
        )
        return list(result.scalars().all())

    def _text_condition(self, query: str) -> ColumnElement[bool]:
        """Полнотекстовый поиск на PostgreSQL, подстрока на остальных.

        Выражение совпадает с GIN-индексом из миграции символ в символ,
        иначе планировщик его не использует.
        """
        if self.is_postgres:
            return text(
                "to_tsvector('russian', coalesce(messages.text, '')) "
                "@@ plainto_tsquery('russian', :fts_query)"
            ).bindparams(fts_query=query)
        return Message.text.ilike(f"%{query}%")

    def _conditions(self, filters: MessageFilters) -> list[Any]:
        conditions: list[Any] = [Message.owner_id == filters.owner_id]
        if filters.query:
            conditions.append(self._text_condition(filters.query))
        if filters.sender:
            pattern = f"%{filters.sender.lstrip('@')}%"
            conditions.append(
                or_(
                    Message.sender_username.ilike(pattern),
                    Message.sender_first_name.ilike(pattern),
                    Message.sender_last_name.ilike(pattern),
                )
            )
        if filters.chat_id:
            conditions.append(Message.chat_id == filters.chat_id)
        if filters.content_type:
            conditions.append(Message.content_type == filters.content_type)
        if filters.only_deleted:
            conditions.append(Message.is_deleted.is_(True))
        if filters.only_edited:
            conditions.append(Message.edit_count > 0)
        if not filters.include_outgoing:
            conditions.append(Message.is_outgoing.is_(False))
        if filters.date_from:
            conditions.append(Message.sent_at >= filters.date_from)
        if filters.date_to:
            conditions.append(Message.sent_at <= filters.date_to)
        return conditions

    async def search(
        self, filters: MessageFilters, offset: int = 0, limit: int = 8
    ) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(*self._conditions(filters))
            .order_by(Message.sent_at.desc(), Message.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().unique().all())

    async def count(self, filters: MessageFilters) -> int:
        result = await self.session.execute(
            select(func.count(Message.id)).where(*self._conditions(filters))
        )
        return int(result.scalar() or 0)

    async def export_rows(self, filters: MessageFilters, limit: int = 5000) -> list[Message]:
        """Выборка для экспорта — по возрастанию даты, чтобы читалось как переписка."""
        result = await self.session.execute(
            select(Message)
            .where(*self._conditions(filters))
            .order_by(Message.sent_at.asc(), Message.id.asc())
            .limit(limit)
        )
        return list(result.scalars().unique().all())

    async def mark_deleted(self, message: Message) -> Message:
        message.is_deleted = True
        message.deleted_at = utcnow()
        return message

    async def counters(self, owner_id: int) -> dict[str, int]:
        """Счётчики для /stats: всего, удалённых, изменённых."""
        total_result = await self.session.execute(
            select(func.count(Message.id)).where(Message.owner_id == owner_id)
        )
        total = int(total_result.scalar() or 0)
        deleted_result = await self.session.execute(
            select(func.count(Message.id)).where(
                Message.owner_id == owner_id, Message.is_deleted.is_(True)
            )
        )
        edited_result = await self.session.execute(
            select(func.count(Message.id)).where(
                Message.owner_id == owner_id, Message.edit_count > 0
            )
        )
        return {
            "total": total,
            "deleted": int(deleted_result.scalar() or 0),
            "edited": int(edited_result.scalar() or 0),
        }

    async def type_breakdown(self, owner_id: int) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(Message.content_type, func.count(Message.id))
            .where(Message.owner_id == owner_id)
            .group_by(Message.content_type)
            .order_by(func.count(Message.id).desc())
        )
        return [(str(row[0]), int(row[1])) for row in result.all()]

    async def top_chats(self, owner_id: int, limit: int = 5) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(Chat, func.count(Message.id).label("item_count"))
            .join(Message, Message.chat_id == Chat.id)
            .where(Message.owner_id == owner_id)
            .group_by(Chat.id)
            .order_by(func.count(Message.id).desc())
            .limit(limit)
        )
        return [(row[0].display_name, int(row[1])) for row in result.all()]

    async def first_sent_at(self, owner_id: int) -> datetime | None:
        result = await self.session.execute(
            select(func.min(Message.sent_at)).where(Message.owner_id == owner_id)
        )
        return result.scalar()

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count(Message.id)))
        return int(result.scalar() or 0)

    async def count_since(self, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count(Message.id)).where(Message.created_at >= since)
        )
        return int(result.scalar() or 0)

    async def count_for_owner(self, owner_id: int) -> int:
        result = await self.session.execute(
            select(func.count(Message.id)).where(Message.owner_id == owner_id)
        )
        return int(result.scalar() or 0)

    async def delete_older_than(self, owner_id: int, cutoff: datetime) -> int:
        """Уборка по сроку хранения. Медиа и правки уйдут по ON DELETE CASCADE."""
        result = await self.session.execute(
            delete(Message).where(Message.owner_id == owner_id, Message.sent_at < cutoff)
        )
        return int(result.rowcount or 0)
