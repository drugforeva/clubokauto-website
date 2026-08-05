"""Сквозная проверка без Telegram и без сети.

Сценарий повторяет жизнь бота: владелец → входящее сообщение → правка →
удаление → поиск → статистика → экспорт. База — sqlite в памяти.

    python smoke_e2e.py
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("BOT_TOKEN", "0:smoke")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "memory://")

from aiogram.types import Chat as TgChat  # noqa: E402
from aiogram.types import Message as TgMessage  # noqa: E402
from aiogram.types import User as TgUser  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.config import get_settings, reset_settings_cache  # noqa: E402
from app.database import Base, build_engine  # noqa: E402
from app.repositories.messages import MessageFilters  # noqa: E402
from app.repositories.uow import UnitOfWork  # noqa: E402
from app.services import CaptureService, ExportService, StatsService  # noqa: E402
from app.utils.time import utcnow  # noqa: E402

OWNER = TgUser(id=100100, is_bot=False, first_name="Владелец", username="owner")
PARTNER = TgUser(id=200200, is_bot=False, first_name="Собеседник", username="partner")
CHAT = TgChat(id=200200, type="private", first_name="Собеседник", username="partner")
CONNECTION_ID = "smoke-connection"


def _message(text: str, *, message_id: int = 9001) -> TgMessage:
    """Минимально достаточное бизнес-сообщение."""
    return TgMessage(
        message_id=message_id,
        date=utcnow(),
        chat=CHAT,
        from_user=PARTNER,
        text=text,
        business_connection_id=CONNECTION_ID,
    )


def _check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"Проверка не прошла: {label}")
    print(f"  ✓ {label}")


async def run() -> None:
    reset_settings_cache()
    settings = get_settings()
    engine = build_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine, expire_on_commit=False, autoflush=False
    )
    capture = CaptureService()
    export_service = ExportService()
    stats = StatsService()

    async with session_factory() as session:
        uow = UnitOfWork(session)

        print("1. Регистрация владельца")
        owner = await uow.users.get_or_create(OWNER)
        owner_settings = await uow.settings.get_or_create(owner.id)
        await uow.commit()
        _check(owner.telegram_id == OWNER.id, "владелец создан")
        _check(owner_settings.notify_deletions is True, "уведомления включены по умолчанию")

        print("2. Архивация сообщения")
        record = await capture.capture_message(
            uow,
            owner=owner,
            settings=owner_settings,
            message=_message("Привет, это первое сообщение"),
            connection_id=CONNECTION_ID,
        )
        await uow.commit()
        _check(record.text == "Привет, это первое сообщение", "текст сохранён")
        _check(record.is_deleted is False, "сообщение живое")

        print("3. Правка текста")
        edited, versions = await capture.capture_edit(
            uow,
            owner=owner,
            settings=owner_settings,
            message=_message("Привет, теперь текст другой"),
            connection_id=CONNECTION_ID,
        )
        await uow.commit()
        _check(edited.id == record.id, "правка попала в ту же запись")
        _check(len(versions) >= 2, "сохранены обе версии текста")
        _check(edited.edit_count >= 1, "счётчик правок вырос")

        print("4. Удаление собеседником")
        found, unknown = await capture.capture_deletions(
            uow,
            owner=owner,
            settings=owner_settings,
            chat=CHAT,
            telegram_message_ids=[9001, 9999],
        )
        await uow.commit()
        _check(len(found) == 1, "найдено одно знакомое удаление")
        _check(unknown == 1, "неизвестное удаление посчитано отдельно")
        _check(found[0].is_deleted is True, "запись помечена удалённой")
        _check(found[0].text == "Привет, теперь текст другой", "текст остался в архиве")

        print("5. Поиск")
        by_word = await uow.messages.search(
            MessageFilters(owner_id=owner.id, query="текст")
        )
        only_deleted = await uow.messages.search(
            MessageFilters(owner_id=owner.id, only_deleted=True)
        )
        _check(len(by_word) == 1, "поиск по слову работает")
        _check(len(only_deleted) == 1, "фильтр «только удалённые» работает")

        print("6. Статистика")
        summary = await stats.personal(uow, owner=owner, settings=owner_settings)
        _check("Сообщений в архиве" in summary, "сводка собрана")

        print("7. Экспорт")
        for fmt in ("txt", "csv", "json", "html"):
            filename, content, count = await export_service.build(
                uow,
                owner=owner,
                filters=MessageFilters(owner_id=owner.id),
                fmt=fmt,
                timezone=owner_settings.timezone,
            )
            _check(count == 1, f"{fmt}: одна строка")
            _check(filename.endswith(f".{fmt}"), f"{fmt}: имя файла")
            _check(len(content) > 0, f"{fmt}: файл не пустой")

    await engine.dispose()
    print("\nВсё прошло. Сквозной сценарий работает.")


if __name__ == "__main__":
    asyncio.run(run())
