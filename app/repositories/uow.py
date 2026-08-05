"""Unit of Work: одна сессия и все репозитории на один апдейт.

Сессию создаёт middleware и кладёт UnitOfWork в data, поэтому все хендлеры
работают в одной транзакции и не могут создать рассогласованное состояние.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.chats import ChatRepository
from app.repositories.connections import ConnectionRepository
from app.repositories.deleted import DeletedMessageRepository
from app.repositories.edits import EditRepository
from app.repositories.media import MediaRepository
from app.repositories.messages import MessageRepository
from app.repositories.settings import SettingsRepository
from app.repositories.users import UserRepository


class UnitOfWork:
    """Контейнер репозиториев поверх одной сессии."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.connections = ConnectionRepository(session)
        self.chats = ChatRepository(session)
        self.messages = MessageRepository(session)
        self.media = MediaRepository(session)
        self.edits = EditRepository(session)
        self.deleted = DeletedMessageRepository(session)
        self.settings = SettingsRepository(session)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
