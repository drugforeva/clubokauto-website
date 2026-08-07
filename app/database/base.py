"""Базовые классы и общие типы ORM."""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Integer, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

# Именование ограничений: без него alembic генерирует безымянные индексы.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# JSONB на PostgreSQL, обычный JSON на остальных (sqlite в тестах).
JsonDict = JSON().with_variant(JSONB(), "postgresql")

# Telegram ID не влезает в int4, но sqlite автоинкрементирует только INTEGER,
# поэтому для внешних идентификаторов — вариантный тип.
BigInt = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    """Общий родитель всех моделей."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:  # pragma: no cover - только для отладки
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} id={pk}>"
