"""Настройки конкретного пользователя: уведомления, медиа, срок хранения."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.user import User


class UserSettings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    notify_deletions: Mapped[bool] = mapped_column(default=True)
    notify_edits: Mapped[bool] = mapped_column(default=True)
    # Свои же сообщения в архиве хранятся всегда, а вот уведомлять о них
    # по умолчанию не нужно: владелец сам видит, что удалил.
    notify_outgoing: Mapped[bool] = mapped_column(default=False)
    save_media: Mapped[bool] = mapped_column(default=True)
    # Скачивание файлов на диск — отдельный тумблер: file_id живёт, пока
    # сообщение не удалено у всех, а диск тратиться моментально.
    download_media: Mapped[bool] = mapped_column(default=False)
    # Ответ владельца на сообщение, которого нет в архиве, — команда боту
    # достать оригинал из цитаты и прислать вложение в чат с ботом.
    rescue_replies: Mapped[bool] = mapped_column(default=True)

    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    # 0 — хранить бессрочно.
    retention_days: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="settings", lazy="selectin")
