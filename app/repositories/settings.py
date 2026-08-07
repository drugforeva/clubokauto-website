"""Репозиторий настроек пользователя."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.settings import UserSettings
from app.repositories.base import BaseRepository

# Флаги, которые разрешено переключать из интерфейса — белый список вместо setattr
# по произвольному имени из callback-данных.
TOGGLE_FIELDS: frozenset[str] = frozenset(
    {
        "notify_deletions",
        "notify_edits",
        "notify_outgoing",
        "save_media",
        "download_media",
        "rescue_replies",
    }
)


class SettingsRepository(BaseRepository):
    async def get(self, user_id: int) -> UserSettings | None:
        result = await self.session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: int, timezone: str | None = None) -> UserSettings:
        record = await self.get(user_id)
        if record is not None:
            return record
        record = UserSettings(user_id=user_id)
        if timezone:
            record.timezone = timezone
        self.session.add(record)
        await self.session.flush()
        return record

    async def toggle(self, settings: UserSettings, field: str) -> bool:
        """Переключить флаг из белого списка. Возвращает новое значение."""
        if field not in TOGGLE_FIELDS:
            raise ValueError(f"Недопустимый флаг настроек: {field}")
        value = not bool(getattr(settings, field))
        setattr(settings, field, value)
        return value

    async def update(self, settings: UserSettings, **values: Any) -> UserSettings:
        allowed = TOGGLE_FIELDS | {"timezone", "retention_days"}
        for key, value in values.items():
            if key in allowed:
                setattr(settings, key, value)
        return settings
