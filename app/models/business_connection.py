"""Подключение бизнес-аккаунта к боту."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, BigInt
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.user import User


class BusinessConnection(Base):
    __tablename__ = "business_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Идентификатор от Telegram — приходит в каждом бизнес-апдейте.
    connection_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Чат владельца с ботом: куда отправлять уведомления.
    owner_chat_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    is_enabled: Mapped[bool] = mapped_column(default=True)
    can_reply: Mapped[bool] = mapped_column(default=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    user: Mapped[User] = relationship(back_populates="connections", lazy="selectin")
