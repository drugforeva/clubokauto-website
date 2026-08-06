"""Версия текста сообщения.

Версия 1 — исходный текст до первой правки, дальше по записи на каждую
правку. Без этого первоначальный текст терялся бы при первом же редактировании.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.message import Message


class MessageEdit(Base):
    __tablename__ = "edits"
    __table_args__ = (UniqueConstraint("message_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(default=1)
    text: Mapped[str | None] = mapped_column(Text, default=None)
    edited_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    message: Mapped[Message] = relationship(back_populates="edits")
