"""Пользователь бота (владелец бизнес-аккаунта)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, BigInt
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.business_connection import BusinessConnection
    from app.models.settings import UserSettings


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInt, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), default=None)
    first_name: Mapped[str | None] = mapped_column(String(128), default=None)
    last_name: Mapped[str | None] = mapped_column(String(128), default=None)
    language_code: Mapped[str | None] = mapped_column(String(16), default=None)
    is_premium: Mapped[bool] = mapped_column(default=False)
    # Заблокировал бота: рассылка таких пропускает.
    is_blocked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    settings: Mapped[UserSettings | None] = relationship(
        back_populates="user",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    connections: Mapped[list[BusinessConnection]] = relationship(
        back_populates="user",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def display_name(self) -> str:
        if self.username:
            return f"@{self.username}"
        name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return name or f"id{self.telegram_id}"
