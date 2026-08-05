"""Репозиторий пользователей."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update

from app.models.user import User
from app.repositories.base import BaseRepository
from app.utils.time import utcnow


class UserRepository(BaseRepository):
    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_or_create(self, from_user: Any) -> User:
        """Найти по telegram_id или создать; по пути освежить имя и username."""
        telegram_id = int(getattr(from_user, "id", 0) or 0)
        user = await self.get_by_telegram_id(telegram_id)
        username = getattr(from_user, "username", None)
        first_name = getattr(from_user, "first_name", None)
        last_name = getattr(from_user, "last_name", None)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code=getattr(from_user, "language_code", None),
                is_premium=bool(getattr(from_user, "is_premium", False)),
            )
            self.session.add(user)
            await self.session.flush()
            return user
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.last_seen_at = utcnow()
        user.is_blocked = False
        return user

    async def mark_blocked(self, user_id: int, blocked: bool = True) -> None:
        """Пометить, что бот заблокирован — рассылка больше не трогает таких."""
        await self.session.execute(
            update(User).where(User.id == user_id).values(is_blocked=blocked)
        )

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(User.id)))
        return int(result.scalar() or 0)

    async def count_active(self) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.is_blocked.is_(False))
        )
        return int(result.scalar() or 0)

    async def page(self, offset: int, limit: int) -> list[User]:
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def all_recipients(self) -> list[User]:
        """Получатели рассылки."""
        result = await self.session.execute(
            select(User).where(User.is_blocked.is_(False)).order_by(User.id)
        )
        return list(result.scalars().all())

    async def created_since(self, since: Any) -> int:
        result = await self.session.execute(
            select(func.count(User.id)).where(User.created_at >= since)
        )
        return int(result.scalar() or 0)
