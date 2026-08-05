"""Тесты экспорта архива.

В файлах даты есть и сразу в поясе владельца — это единственное место,
где время показывается человеку.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from aiogram.types import Chat as TgChat

from app.models.message import Message
from app.models.user import User
from app.repositories.messages import MessageFilters
from app.repositories.uow import UnitOfWork
from app.services.export import FORMAT_LABELS, FORMATS, ExportService

TIMEZONE = "Europe/Moscow"


async def _fill(uow: UnitOfWork, owner: User, tg_chat: TgChat) -> None:
    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    await uow.messages.add(
        Message(
            owner_id=owner.id,
            chat_id=chat.id,
            telegram_message_id=1,
            sender_id=200200,
            sender_username="marina",
            content_type="text",
            text="Встреча в пятницу",
            sent_at=datetime(2026, 8, 4, 21, 0),
        )
    )
    await uow.messages.add(
        Message(
            owner_id=owner.id,
            chat_id=chat.id,
            telegram_message_id=2,
            sender_id=200200,
            sender_username="marina",
            content_type="photo",
            text=None,
            is_deleted=True,
            sent_at=datetime(2026, 8, 4, 22, 0),
        )
    )
    await uow.commit()


async def test_export_txt(uow: UnitOfWork, owner: User, tg_chat: TgChat) -> None:
    await _fill(uow, owner, tg_chat)

    filename, content, count = await ExportService().build(
        uow,
        owner=owner,
        filters=MessageFilters(owner_id=owner.id),
        fmt="txt",
        timezone=TIMEZONE,
    )
    body = content.decode("utf-8")

    assert count == 2
    assert filename.startswith(f"sohrano_{owner.telegram_id}_")
    assert filename.endswith(".txt")
    assert "Встреча в пятницу" in body
    assert "05.08.2026 00:00" in body  # 21:00 UTC → московская полночь


async def test_export_csv_has_header(uow: UnitOfWork, owner: User, tg_chat: TgChat) -> None:
    await _fill(uow, owner, tg_chat)

    filename, content, count = await ExportService().build(
        uow,
        owner=owner,
        filters=MessageFilters(owner_id=owner.id),
        fmt="csv",
        timezone=TIMEZONE,
    )
    lines = content.decode("utf-8").splitlines()

    assert filename.endswith(".csv")
    assert count == 2
    assert len(lines) >= 3  # шапка и две строки


async def test_export_json_is_parseable(uow: UnitOfWork, owner: User, tg_chat: TgChat) -> None:
    await _fill(uow, owner, tg_chat)

    filename, content, count = await ExportService().build(
        uow,
        owner=owner,
        filters=MessageFilters(owner_id=owner.id),
        fmt="json",
        timezone=TIMEZONE,
    )
    parsed = json.loads(content.decode("utf-8"))

    assert filename.endswith(".json")
    assert count == 2
    assert parsed  # структура валидна и не пуста
    assert "Встреча в пятницу" in content.decode("utf-8")


async def test_export_html_escapes_text(uow: UnitOfWork, owner: User, tg_chat: TgChat) -> None:
    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    await uow.messages.add(
        Message(
            owner_id=owner.id,
            chat_id=chat.id,
            telegram_message_id=1,
            sender_username="marina",
            content_type="text",
            text="<script>alert(1)</script>",
            sent_at=datetime(2026, 8, 4, 21, 0),
        )
    )
    await uow.commit()

    _, content, _ = await ExportService().build(
        uow,
        owner=owner,
        filters=MessageFilters(owner_id=owner.id),
        fmt="html",
        timezone=TIMEZONE,
    )
    body = content.decode("utf-8")

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


async def test_export_respects_filters(uow: UnitOfWork, owner: User, tg_chat: TgChat) -> None:
    await _fill(uow, owner, tg_chat)

    _, content, count = await ExportService().build(
        uow,
        owner=owner,
        filters=MessageFilters(owner_id=owner.id, only_deleted=True),
        fmt="txt",
        timezone=TIMEZONE,
    )

    assert count == 1
    assert "Встреча в пятницу" not in content.decode("utf-8")


async def test_export_empty_archive(uow: UnitOfWork, owner: User) -> None:
    _, content, count = await ExportService().build(
        uow,
        owner=owner,
        filters=MessageFilters(owner_id=owner.id),
        fmt="txt",
        timezone=TIMEZONE,
    )

    assert count == 0
    assert content  # файл всё равно с шапкой, а не пустой


async def test_export_rejects_unknown_format(uow: UnitOfWork, owner: User) -> None:
    with pytest.raises(ValueError):
        await ExportService().build(
            uow,
            owner=owner,
            filters=MessageFilters(owner_id=owner.id),
            fmt="pdf",
            timezone=TIMEZONE,
        )


def test_all_formats_have_labels() -> None:
    assert set(FORMATS) == set(FORMAT_LABELS)
