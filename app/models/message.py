"""Сообщение из бизнес-диалога — центральная таблица архива."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, BigInt, JsonDict
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.chat import Chat
    from app.models.edit import MessageEdit
    from app.models.media import Media


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Защита от двойной записи: Telegram может прислать апдейт повторно.
        UniqueConstraint("owner_id", "chat_id", "telegram_message_id"),
        Index("ix_messages_owner_sent", "owner_id", "sent_at"),
        Index("ix_messages_owner_type_sent", "owner_id", "content_type", "sent_at"),
        Index("ix_messages_chat_sent", "chat_id", "sent_at"),
        Index("ix_messages_owner_deleted", "owner_id", "is_deleted"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[str | None] = mapped_column(String(128), default=None)

    telegram_message_id: Mapped[int] = mapped_column(BigInt)
    sender_id: Mapped[int | None] = mapped_column(BigInt, default=None)
    sender_username: Mapped[str | None] = mapped_column(String(64), default=None)
    sender_first_name: Mapped[str | None] = mapped_column(String(128), default=None)
    sender_last_name: Mapped[str | None] = mapped_column(String(128), default=None)
    is_outgoing: Mapped[bool] = mapped_column(default=False)

    content_type: Mapped[str] = mapped_column(String(32), default="text")
    text: Mapped[str | None] = mapped_column(Text, default=None)
    # Атрибут extra_data, колонка extra: имя extra занято в интерфейсе SQLAlchemy.
    extra_data: Mapped[dict[str, Any] | None] = mapped_column("extra", JsonDict, default=None)
    reply_to_message_id: Mapped[int | None] = mapped_column(BigInt, default=None)

    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    edit_count: Mapped[int] = mapped_column(default=0)
    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # lazy="joined"/"selectin": в асинхронном режиме ленивая догрузка при обращении
    # к атрибуту падает с MissingGreenlet, поэтому связи грузятся сразу.
    chat: Mapped[Chat] = relationship(lazy="joined")
    media: Mapped[list[Media]] = relationship(
        back_populates="message",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="Media.id",
    )
    edits: Mapped[list[MessageEdit]] = relationship(
        back_populates="message",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="MessageEdit.version",
    )
