"""Факт удаления сообщения.

Отдельная таблица, а не только флаг в messages: Telegram присылает удаления
пачками и иногда по сообщениям, которых нет в архиве (пришли до подключения).
Такие события всё равно нужно видеть в статистике.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, BigInt
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.message import Message


class DeletedMessage(Base):
    __tablename__ = "deleted_messages"
    __table_args__ = (Index("ix_deleted_messages_owner_detected", "owner_id", "detected_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), default=None, index=True
    )
    chat_id: Mapped[int | None] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), default=None
    )
    telegram_message_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    # False, если владелец отключил уведомления: событие записано, но не отправлено.
    notified: Mapped[bool] = mapped_column(default=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    message: Mapped[Message | None] = relationship(lazy="selectin")
