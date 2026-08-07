"""Тесты репозиториев и фильтров поиска.

Проверяется главное требование к данным: каждый запрос ограничен owner_id,
чтобы архив одного владельца не протекал в чужой.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from aiogram.types import Chat as TgChat
from aiogram.types import Message as TgMessage
from aiogram.types import User as TgUser

from app.models.message import Message
from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.messages import MessageFilters
from app.repositories.uow import UnitOfWork
from app.services.capture import CaptureService
from app.utils.time import utcnow


async def _message(
    uow: UnitOfWork,
    owner: User,
    chat_id: int,
    *,
    telegram_message_id: int,
    text: str | None = "текст",
    content_type: str = "text",
    is_outgoing: bool = False,
    is_deleted: bool = False,
    edit_count: int = 0,
    days_back: int = 0,
    sender_username: str | None = "marina",
) -> Message:
    record = Message(
        owner_id=owner.id,
        chat_id=chat_id,
        telegram_message_id=telegram_message_id,
        sender_id=200200,
        sender_username=sender_username,
        sender_first_name="Марина",
        is_outgoing=is_outgoing,
        content_type=content_type,
        text=text,
        is_deleted=is_deleted,
        edit_count=edit_count,
        sent_at=utcnow() - timedelta(days=days_back),
    )
    await uow.messages.add(record)
    return record


async def test_users_get_or_create_is_stable(uow: UnitOfWork, tg_owner: TgUser) -> None:
    first = await uow.users.get_or_create(tg_owner)
    second = await uow.users.get_or_create(tg_owner)
    await uow.commit()

    assert first.id == second.id
    assert first.telegram_id == tg_owner.id
    assert await uow.users.count() == 1


async def test_users_mark_blocked(uow: UnitOfWork, owner: User) -> None:
    await uow.users.mark_blocked(owner.id)
    await uow.commit()

    fresh = await uow.users.get_by_telegram_id(owner.telegram_id)

    assert fresh is not None
    assert fresh.is_blocked is True
    assert await uow.users.count_active() == 0


async def test_settings_defaults_and_toggle(
    uow: UnitOfWork, owner_settings: UserSettings
) -> None:
    assert owner_settings.notify_deletions is True
    assert owner_settings.notify_outgoing is False
    assert owner_settings.save_media is True
    assert owner_settings.download_media is False
    assert owner_settings.timezone == "Europe/Moscow"
    assert owner_settings.retention_days == 0

    await uow.settings.toggle(owner_settings, "notify_edits")
    await uow.commit()

    assert owner_settings.notify_edits is False


async def test_chats_are_unique_per_owner(
    uow: UnitOfWork, owner: User, tg_chat: TgChat
) -> None:
    first = await uow.chats.get_or_create(owner.id, tg_chat)
    second = await uow.chats.get_or_create(owner.id, tg_chat)
    await uow.commit()

    assert first.id == second.id
    assert first.telegram_chat_id == tg_chat.id
    assert await uow.chats.count_for_owner(owner.id) == 1


async def test_message_search_by_text_and_type(
    uow: UnitOfWork, owner: User, tg_chat: TgChat
) -> None:
    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    await _message(uow, owner, chat.id, telegram_message_id=1, text="Встреча в пятницу")
    await _message(uow, owner, chat.id, telegram_message_id=2, text="Счёт на оплату")
    await _message(
        uow, owner, chat.id, telegram_message_id=3, text=None, content_type="photo"
    )
    await uow.commit()

    found = await uow.messages.search(MessageFilters(owner_id=owner.id, query="встреча"))
    photos = await uow.messages.search(
        MessageFilters(owner_id=owner.id, content_type="photo")
    )

    assert [item.telegram_message_id for item in found] == [1]
    assert [item.telegram_message_id for item in photos] == [3]
    assert await uow.messages.count(MessageFilters(owner_id=owner.id)) == 3


async def test_message_filters_exclude_outgoing_and_pick_deleted(
    uow: UnitOfWork, owner: User, tg_chat: TgChat
) -> None:
    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    await _message(uow, owner, chat.id, telegram_message_id=1)
    await _message(uow, owner, chat.id, telegram_message_id=2, is_outgoing=True)
    await _message(uow, owner, chat.id, telegram_message_id=3, is_deleted=True)
    await _message(uow, owner, chat.id, telegram_message_id=4, edit_count=2)
    await uow.commit()

    incoming = await uow.messages.search(
        MessageFilters(owner_id=owner.id, include_outgoing=False)
    )
    deleted = await uow.messages.search(
        MessageFilters(owner_id=owner.id, only_deleted=True)
    )
    edited = await uow.messages.search(MessageFilters(owner_id=owner.id, only_edited=True))

    assert 2 not in [item.telegram_message_id for item in incoming]
    assert [item.telegram_message_id for item in deleted] == [3]
    assert [item.telegram_message_id for item in edited] == [4]


async def test_message_filters_by_date_range(
    uow: UnitOfWork, owner: User, tg_chat: TgChat
) -> None:
    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    await _message(uow, owner, chat.id, telegram_message_id=1, days_back=0)
    await _message(uow, owner, chat.id, telegram_message_id=2, days_back=30)
    await uow.commit()

    recent = await uow.messages.search(
        MessageFilters(owner_id=owner.id, date_from=utcnow() - timedelta(days=7))
    )

    assert [item.telegram_message_id for item in recent] == [1]


async def test_message_search_is_owner_scoped(
    uow: UnitOfWork, owner: User, tg_chat: TgChat, tg_partner: TgUser
) -> None:
    """Архив другого владельца не должен попадать в выборку."""
    stranger = await uow.users.get_or_create(tg_partner)
    await uow.commit()

    own_chat = await uow.chats.get_or_create(owner.id, tg_chat)
    other_chat = await uow.chats.get_or_create(stranger.id, tg_chat)
    await _message(uow, owner, own_chat.id, telegram_message_id=1, text="моё")
    await _message(uow, stranger, other_chat.id, telegram_message_id=1, text="чужое")
    await uow.commit()

    mine = await uow.messages.search(MessageFilters(owner_id=owner.id))

    assert [item.text for item in mine] == ["моё"]
    assert await uow.messages.count_for_owner(stranger.id) == 1


async def test_message_counters_and_breakdown(
    uow: UnitOfWork, owner: User, tg_chat: TgChat
) -> None:
    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    await _message(uow, owner, chat.id, telegram_message_id=1)
    await _message(uow, owner, chat.id, telegram_message_id=2, is_deleted=True)
    await _message(uow, owner, chat.id, telegram_message_id=3, edit_count=1)
    await _message(
        uow, owner, chat.id, telegram_message_id=4, content_type="photo", text=None
    )
    await uow.commit()

    counters = await uow.messages.counters(owner.id)
    breakdown = dict(await uow.messages.type_breakdown(owner.id))

    assert counters["total"] == 4
    assert counters["deleted"] == 1
    assert counters["edited"] == 1
    assert breakdown["text"] == 3
    assert breakdown["photo"] == 1


async def test_edits_versions_increment(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    make_message: Callable[..., TgMessage],
) -> None:
    record = await CaptureService().capture_message(
        uow, owner=owner, settings=owner_settings, message=make_message(text="первый")
    )
    await uow.commit()

    assert await uow.edits.next_version(record.id) == 1

    await uow.edits.add(
        message_id=record.id, version=1, text="первый", edited_at=utcnow()
    )
    await uow.commit()

    assert await uow.edits.next_version(record.id) == 2
    assert await uow.edits.count_for_message(record.id) == 1


async def test_deleted_messages_log(uow: UnitOfWork, owner: User, tg_chat: TgChat) -> None:
    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    record = await _message(uow, owner, chat.id, telegram_message_id=7, is_deleted=True)
    await uow.commit()

    await uow.deleted.add(
        owner_id=owner.id,
        message_id=record.id,
        chat_id=chat.id,
        telegram_message_id=7,
        notified=True,
    )
    await uow.commit()

    recent = await uow.deleted.recent(owner.id, limit=5)

    assert len(recent) == 1
    assert recent[0].telegram_message_id == 7
    assert await uow.deleted.count_for_owner(owner.id) == 1


async def test_message_retention_delete_older_than(
    uow: UnitOfWork, owner: User, tg_chat: TgChat
) -> None:
    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    await _message(uow, owner, chat.id, telegram_message_id=1, days_back=0)
    await _message(uow, owner, chat.id, telegram_message_id=2, days_back=100)
    await uow.commit()

    removed = await uow.messages.delete_older_than(owner.id, utcnow() - timedelta(days=30))
    await uow.commit()

    assert removed == 1
    assert await uow.messages.count_for_owner(owner.id) == 1


def test_message_filters_describe() -> None:
    empty = MessageFilters(owner_id=1)
    filled = MessageFilters(owner_id=1, query="счёт", only_deleted=True)

    assert empty.is_active is False
    assert filled.is_active is True
    assert "счёт" in filled.describe()
