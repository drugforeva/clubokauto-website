"""Репозиторий бизнес-подключений."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models.business_connection import BusinessConnection
from app.repositories.base import BaseRepository
from app.utils.time import utcnow


class ConnectionRepository(BaseRepository):
    async def get(self, connection_id: str) -> BusinessConnection | None:
        result = await self.session.execute(
            select(BusinessConnection).where(BusinessConnection.connection_id == connection_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        connection_id: str,
        user_id: int,
        owner_chat_id: int | None,
        is_enabled: bool,
        can_reply: bool,
    ) -> BusinessConnection:
        """Создать или обновить подключение.

        Telegram присылает business_connection повторно при любом изменении
        прав, поэтому вставка всегда идёт через upsert.
        """
        connection = await self.get(connection_id)
        if connection is None:
            connection = BusinessConnection(
                connection_id=connection_id,
                user_id=user_id,
                owner_chat_id=owner_chat_id,
                is_enabled=is_enabled,
                can_reply=can_reply,
            )
            self.session.add(connection)
            await self.session.flush()
            return connection
        connection.user_id = user_id
        connection.owner_chat_id = owner_chat_id
        connection.is_enabled = is_enabled
        connection.can_reply = can_reply
        connection.disconnected_at = None if is_enabled else utcnow()
        return connection

    async def disable(self, connection_id: str) -> BusinessConnection | None:
        connection = await self.get(connection_id)
        if connection is None:
            return None
        connection.is_enabled = False
        connection.disconnected_at = utcnow()
        return connection

    async def for_user(self, user_id: int) -> list[BusinessConnection]:
        result = await self.session.execute(
            select(BusinessConnection)
            .where(BusinessConnection.user_id == user_id)
            .order_by(BusinessConnection.connected_at.desc())
        )
        return list(result.scalars().all())

    async def count_enabled(self) -> int:
        result = await self.session.execute(
            select(func.count(BusinessConnection.id)).where(
                BusinessConnection.is_enabled.is_(True)
            )
        )
        return int(result.scalar() or 0)
