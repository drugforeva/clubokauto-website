"""Тесты сохранения сообщений, правок и удалений.

Это ядро бота: если сломается что-то здесь, архив перестанет быть архивом.
Никаких запросов к Telegram нет: downloader не передаётся, а download_media выключен.
"""

from __future__ import annotations

from collections.abc import Callable

from aiogram.types import Chat as TgChat
from aiogram.types import Message as TgMessage
from aiogram.types import PhotoSize

from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.uow import UnitOfWork
from app.services.capture import CaptureService
from app.utils.time import utcnow

CONNECTION_ID = "test-connection"


async def test_capture_message_saves_text(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    make_message: Callable[..., TgMessage],
) -> None:
    record = await CaptureService().capture_message(
        uow,
        owner=owner,
        settings=owner_settings,
        message=make_message(text="Привет, мир"),
        connection_id=CONNECTION_ID,
    )
    await uow.commit()

    assert record.id is not None
    assert record.content_type == "text"
    assert record.text == "Привет, мир"
    assert record.telegram_message_id == 501
    assert record.owner_id == owner.id
    assert record.is_outgoing is False
    assert record.is_deleted is False
    assert record.connection_id == CONNECTION_ID
    assert record.sender_username == "marina"


async def test_capture_message_is_idempotent(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    make_message: Callable[..., TgMessage],
) -> None:
    """Telegram может прислать один и тот же апдейт дважды."""
    capture = CaptureService()
    message = make_message(text="Дубль")

    first = await capture.capture_message(
        uow, owner=owner, settings=owner_settings, message=message
    )
    second = await capture.capture_message(
        uow, owner=owner, settings=owner_settings, message=message
    )
    await uow.commit()

    assert first.id == second.id
    assert await uow.messages.count_for_owner(owner.id) == 1


async def test_capture_message_saves_media_rows(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    make_message: Callable[..., TgMessage],
) -> None:
    photo = [
        PhotoSize(file_id="small", file_unique_id="u1", width=90, height=60, file_size=1024),
        PhotoSize(
            file_id="large", file_unique_id="u2", width=1280, height=720, file_size=204800
        ),
    ]
    record = await CaptureService().capture_message(
        uow,
        owner=owner,
        settings=owner_settings,
        message=make_message(text=None, photo=photo, caption="На даче"),
    )
    await uow.commit()

    media = await uow.media.for_message(record.id)

    assert record.content_type == "photo"
    assert record.text == "На даче"
    assert len(media) == 1
    assert media[0].file_id == "large"
    assert media[0].local_path is None  # download_media выключен по умолчанию


async def test_capture_message_respects_save_media_off(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    make_message: Callable[..., TgMessage],
) -> None:
    owner_settings.save_media = False
    await uow.commit()

    photo = [PhotoSize(file_id="one", file_unique_id="u1", width=90, height=60)]
    record = await CaptureService().capture_message(
        uow, owner=owner, settings=owner_settings, message=make_message(text=None, photo=photo)
    )
    await uow.commit()

    assert record.content_type == "photo"
    assert await uow.media.for_message(record.id) == []


async def test_capture_edit_keeps_original_version(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    make_message: Callable[..., TgMessage],
) -> None:
    capture = CaptureService()
    await capture.capture_message(
        uow, owner=owner, settings=owner_settings, message=make_message(text="было")
    )
    await uow.commit()

    edited = make_message(text="стало")
    record, versions = await capture.capture_edit(
        uow, owner=owner, settings=owner_settings, message=edited
    )
    await uow.commit()

    assert record.text == "стало"
    assert record.edit_count == 1
    assert record.edited_at is not None
    assert [item.version for item in versions] == [1, 2]
    assert [item.text for item in versions] == ["было", "стало"]


async def test_capture_edit_ignores_same_text(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    make_message: Callable[..., TgMessage],
) -> None:
    """Правка без изменения текста (например, пришла превью ссылки)."""
    capture = CaptureService()
    await capture.capture_message(
        uow, owner=owner, settings=owner_settings, message=make_message(text="одинаково")
    )
    await uow.commit()

    record, versions = await capture.capture_edit(
        uow, owner=owner, settings=owner_settings, message=make_message(text="одинаково")
    )
    await uow.commit()

    assert record.edit_count == 0
    assert versions == []


async def test_capture_deletions_marks_known_and_counts_unknown(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    make_message: Callable[..., TgMessage],
    tg_chat: TgChat,
) -> None:
    capture = CaptureService()
    saved = await capture.capture_message(
        uow,
        owner=owner,
        settings=owner_settings,
        message=make_message(text="удалят", message_id=501, date=utcnow()),
    )
    await uow.commit()

    removed, unknown = await capture.capture_deletions(
        uow,
        owner=owner,
        settings=owner_settings,
        chat=tg_chat,
        telegram_message_ids=[501, 999],
    )
    await uow.commit()

    assert [item.id for item in removed] == [saved.id]
    assert removed[0].is_deleted is True
    assert removed[0].deleted_at is not None
    assert unknown == 1  # 999 пришло до подключения бота
    assert await uow.deleted.count_for_owner(owner.id) >= 1
