"""Общие фикстуры тестов.

База — sqlite в памяти, поэтому тесты не требуют ни PostgreSQL, ни Redis,
ни сети. StaticPool обязателен: без него каждое новое соединение
получает свою пустую in-memory базу и таблиц в ней не оказывается.

Переменные окружения выставляются до импорта app.*: Settings требует
токен, а его в CI нет.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from datetime import datetime

import pytest

os.environ.setdefault("BOT_TOKEN", "111:test-token")
os.environ.setdefault("BOT_ADMIN_IDS", "100100")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("LOG_LEVEL", "WARNING")

from aiogram.types import Chat as TgChat  # noqa: E402
from aiogram.types import Message as TgMessage  # noqa: E402
from aiogram.types import User as TgUser  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402, F401  — регистрация всех таблиц в Base.metadata
from app.database import Base  # noqa: E402
from app.models.settings import UserSettings  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.uow import UnitOfWork  # noqa: E402
from app.utils.time import utcnow  # noqa: E402

OWNER_ID = 100100
PARTNER_ID = 200200
CONNECTION_ID = "test-connection"


@pytest.fixture
def tg_owner() -> TgUser:
    """Владелец архива — тот, кто подключил бота к Telegram Business."""
    return TgUser(
        id=OWNER_ID,
        is_bot=False,
        first_name="Владелец",
        username="owner",
        language_code="ru",
    )


@pytest.fixture
def tg_partner() -> TgUser:
    """Собеседник, чьи сообщения сохраняются."""
    return TgUser(
        id=PARTNER_ID,
        is_bot=False,
        first_name="Марина",
        last_name="Котова",
        username="marina",
    )


@pytest.fixture
def tg_chat(tg_partner: TgUser) -> TgChat:
    return TgChat(
        id=PARTNER_ID,
        type="private",
        username=tg_partner.username,
        first_name=tg_partner.first_name,
        last_name=tg_partner.last_name,
    )


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session


@pytest.fixture
def uow(session: AsyncSession) -> UnitOfWork:
    return UnitOfWork(session)


@pytest.fixture
async def owner(uow: UnitOfWork, tg_owner: TgUser) -> User:
    user = await uow.users.get_or_create(tg_owner)
    await uow.commit()
    return user


@pytest.fixture
async def owner_settings(uow: UnitOfWork, owner: User) -> UserSettings:
    settings = await uow.settings.get_or_create(owner.id)
    await uow.commit()
    return settings


@pytest.fixture
def make_message(
    tg_chat: TgChat, tg_partner: TgUser
) -> Callable[..., TgMessage]:
    """Фабрика входящих сообщений Telegram Business."""

    def factory(
        text: str | None = "Привет",
        message_id: int = 501,
        *,
        date: datetime | None = None,
        from_user: TgUser | None = None,
        **extra: object,
    ) -> TgMessage:
        return TgMessage(
            message_id=message_id,
            date=date or utcnow(),
            chat=tg_chat,
            from_user=from_user or tg_partner,
            text=text,
            business_connection_id=CONNECTION_ID,
            **extra,
        )

    return factory
