"""Диалог бизнес-аккаунта."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, BigInt
from app.utils.time import utcnow


class Chat(Base):
    __tablename__ = "chats"
    # Один и тот же человек может писать разным владельцам — диалоги разные.
    __table_args__ = (UniqueConstraint("owner_id", "telegram_chat_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInt)
    type: Mapped[str] = mapped_column(String(32), default="private")
    title: Mapped[str | None] = mapped_column(String(256), default=None)
    username: Mapped[str | None] = mapped_column(String(64), default=None)
    first_name: Mapped[str | None] = mapped_column(String(128), default=None)
    last_name: Mapped[str | None] = mapped_column(String(128), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    @property
    def display_name(self) -> str:
        if self.username:
            return f"@{self.username}"
        name = self.title or f"{self.first_name or ''} {self.last_name or ''}".strip()
        return name or f"chat {self.telegram_chat_id}"
