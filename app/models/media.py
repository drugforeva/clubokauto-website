"""Вложение сообщения: file_id всегда, путь на диске — опционально."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, BigInt
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.message import Message


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    media_type: Mapped[str] = mapped_column(String(32), default="document")
    # file_id действителен, пока файл жив на серверах Telegram.
    file_id: Mapped[str] = mapped_column(String(256))
    file_unique_id: Mapped[str | None] = mapped_column(String(128), default=None)
    file_name: Mapped[str | None] = mapped_column(String(256), default=None)
    mime_type: Mapped[str | None] = mapped_column(String(128), default=None)
    file_size: Mapped[int | None] = mapped_column(BigInt, default=None)
    duration: Mapped[int | None] = mapped_column(default=None)
    # Заполняется, только если у владельца включено скачивание медиа.
    local_path: Mapped[str | None] = mapped_column(String(512), default=None)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    message: Mapped[Message] = relationship(back_populates="media")
