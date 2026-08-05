"""Создание асинхронного движка и фабрики сессий."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from app.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Движок по DSN из настроек. sqlite нужен только тестам."""
    url = settings.sqlalchemy_url
    kwargs: dict[str, Any] = {"echo": settings.sql_echo, "future": True}
    if not url.startswith("sqlite"):
        kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
    return create_async_engine(url, **kwargs)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий. expire_on_commit=False — объекты живут после commit."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
