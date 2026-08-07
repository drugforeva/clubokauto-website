"""Общий родитель репозиториев."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Доступ к сессии и определение диалекта.

    Диалект нужен для поиска: на PostgreSQL используется полнотекстовый
    to_tsvector/plainto_tsquery, на остальных (sqlite в тестах) — подстрока.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @property
    def dialect(self) -> str:
        bind = getattr(self.session, "bind", None)
        dialect = getattr(bind, "dialect", None)
        return str(getattr(dialect, "name", "") or "")

    @property
    def is_postgres(self) -> bool:
        return self.dialect.startswith("postgres")
