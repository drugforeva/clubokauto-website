"""Спасение вложений по ответу владельца."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from aiogram.types import Chat as TgChat
from aiogram.types import Message as TgMessage
from aiogram.types import PhotoSize
from aiogram.types import User as TgUser

from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.uow import UnitOfWork
from app.services.capture import CaptureService
from app.services.notifier import SendResult
from app.services.rescue import RescueService
from app.utils.time import utcnow
from tests.conftest import CONNECTION_ID, OWNER_ID

PHOTO_ID = "AgACAgIAAxk-photo"


class FakeNotifier:
    """Запоминает отправленное вместо похода в Telegram."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.documents: list[tuple[str, bytes]] = []
        self.file_ids: list[tuple[str, str]] = []

    async def send(self, chat_id: int, text: str, keyboard: Any = None) -> SendResult:
        self.texts.append(text)
        return SendResult(ok=True)

    async def send_document(
        self, chat_id: int, filename: str, content: bytes, caption: str | None = None
    ) -> SendResult:
        self.documents.append((filename, content))
        return SendResult(ok=True)

    async def send_by_file_id(
        self, chat_id: int, media_type: str, file_id: str, caption: str | None = None
    ) -> SendResult:
        self.file_ids.append((media_type, file_id))
        return SendResult(ok=True)

    @property
    def empty(self) -> bool:
        return not (self.texts or self.documents or self.file_ids)


class FakeDownloader:
    """Отдаёт заранее подготовленный путь — сети в тестах нет."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.calls = 0

    async def download(self, *, owner_telegram_id: int, payload: Any) -> str:
        self.calls += 1
        return str(self.path)


def _photo_message(
    chat: TgChat, sender: TgUser, message_id: int = 777
) -> TgMessage:
    """Цитата с фото — то, что Telegram кладёт в reply_to_message."""
    photo = PhotoSize(
        file_id=PHOTO_ID,
        file_unique_id="uniq-photo",
        width=1280,
        height=720,
        file_size=2048,
    )
    return TgMessage(
        message_id=message_id,
        date=utcnow(),
        chat=chat,
        from_user=sender,
        photo=[photo],
        business_connection_id=CONNECTION_ID,
    )


async def _rescue(
    service: RescueService,
    uow: UnitOfWork,
    owner: User,
    settings: UserSettings,
    reply: TgMessage,
) -> bool:
    return await service.rescue_from_reply(
        uow,
        owner=owner,
        settings=settings,
        message=reply,
        owner_chat_id=OWNER_ID,
        connection_id=CONNECTION_ID,
    )


async def test_reply_rescues_photo_missing_from_archive(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    tg_chat: TgChat,
    tg_partner: TgUser,
    tg_owner: TgUser,
    make_message: Callable[..., TgMessage],
) -> None:
    quoted = _photo_message(tg_chat, tg_partner)
    reply = make_message(
        text="что это?", message_id=778, from_user=tg_owner, reply_to_message=quoted
    )
    notifier = FakeNotifier()
    service = RescueService(CaptureService(), notifier)

    assert await _rescue(service, uow, owner, owner_settings, reply) is True

    # Загрузчика нет — файл ушёл пересылкой по file_id.
    assert notifier.file_ids == [("photo", PHOTO_ID)]
    assert notifier.texts and "Спасено" in notifier.texts[0]

    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    saved = await uow.messages.find_by_telegram_id(owner.id, chat.id, 777)
    assert saved is not None
    assert saved.content_type == "photo"


async def test_rescued_file_is_downloaded_and_sent_as_document(
    tmp_path: Path,
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    tg_chat: TgChat,
    tg_partner: TgUser,
    tg_owner: TgUser,
    make_message: Callable[..., TgMessage],
) -> None:
    stored = tmp_path / "photo.jpg"
    stored.write_bytes(b"binary-photo")
    downloader = FakeDownloader(stored)
    quoted = _photo_message(tg_chat, tg_partner, message_id=779)
    reply = make_message(
        text="ого", message_id=780, from_user=tg_owner, reply_to_message=quoted
    )
    notifier = FakeNotifier()
    service = RescueService(CaptureService(downloader=downloader), notifier)

    assert await _rescue(service, uow, owner, owner_settings, reply) is True

    # Автозагрузка выключена, но спасение качает файл принудительно.
    assert owner_settings.download_media is False
    assert downloader.calls == 1
    assert notifier.documents == [("photo.jpg", b"binary-photo")]
    assert not notifier.file_ids


async def test_reply_to_known_message_is_ignored(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    tg_chat: TgChat,
    tg_partner: TgUser,
    tg_owner: TgUser,
    make_message: Callable[..., TgMessage],
) -> None:
    capture = CaptureService()
    quoted = _photo_message(tg_chat, tg_partner, message_id=781)
    await capture.capture_message(
        uow,
        owner=owner,
        settings=owner_settings,
        message=quoted,
        connection_id=CONNECTION_ID,
    )
    reply = make_message(
        text="помню", message_id=782, from_user=tg_owner, reply_to_message=quoted
    )
    notifier = FakeNotifier()

    rescued = await _rescue(
        RescueService(capture, notifier), uow, owner, owner_settings, reply
    )

    # Сообщение уже в архиве — спама быть не должно.
    assert rescued is False
    assert notifier.empty


async def test_empty_envelope_gets_media_from_quote(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    tg_chat: TgChat,
    tg_partner: TgUser,
    tg_owner: TgUser,
    make_message: Callable[..., TgMessage],
) -> None:
    capture = CaptureService()
    envelope = TgMessage(
        message_id=783,
        date=utcnow(),
        chat=tg_chat,
        from_user=tg_partner,
        business_connection_id=CONNECTION_ID,
    )
    await capture.capture_message(
        uow,
        owner=owner,
        settings=owner_settings,
        message=envelope,
        connection_id=CONNECTION_ID,
    )
    quoted = _photo_message(tg_chat, tg_partner, message_id=783)
    reply = make_message(
        text="а что там было?",
        message_id=784,
        from_user=tg_owner,
        reply_to_message=quoted,
    )
    notifier = FakeNotifier()

    rescued = await _rescue(
        RescueService(capture, notifier), uow, owner, owner_settings, reply
    )

    assert rescued is True
    assert notifier.file_ids == [("photo", PHOTO_ID)]

    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    saved = await uow.messages.find_by_telegram_id(owner.id, chat.id, 783)
    assert saved is not None
    assert saved.content_type == "photo"
    assert await uow.media.for_message(saved.id)


async def test_quote_without_message_id_is_delivered_without_archive(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    tg_chat: TgChat,
    tg_partner: TgUser,
    tg_owner: TgUser,
    make_message: Callable[..., TgMessage],
) -> None:
    # У одноразовых сообщений Bot API присылает message_id = 0.
    quoted = _photo_message(tg_chat, tg_partner, message_id=0)
    reply = make_message(
        text="!", message_id=785, from_user=tg_owner, reply_to_message=quoted
    )
    notifier = FakeNotifier()

    rescued = await _rescue(
        RescueService(CaptureService(), notifier), uow, owner, owner_settings, reply
    )

    assert rescued is True
    assert notifier.file_ids == [("photo", PHOTO_ID)]


async def test_reply_to_text_only_quote_saves_it_silently(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    tg_chat: TgChat,
    tg_owner: TgUser,
    make_message: Callable[..., TgMessage],
) -> None:
    quoted = make_message(text="старое сообщение", message_id=786)
    reply = make_message(
        text="отвечаю", message_id=787, from_user=tg_owner, reply_to_message=quoted
    )
    notifier = FakeNotifier()

    rescued = await _rescue(
        RescueService(CaptureService(), notifier), uow, owner, owner_settings, reply
    )

    # Спасать нечего, но текст всё равно оказывается в архиве.
    assert rescued is False
    assert notifier.empty

    chat = await uow.chats.get_or_create(owner.id, tg_chat)
    saved = await uow.messages.find_by_telegram_id(owner.id, chat.id, 786)
    assert saved is not None
    assert saved.text == "старое сообщение"


async def test_setting_disables_rescue(
    uow: UnitOfWork,
    owner: User,
    owner_settings: UserSettings,
    tg_chat: TgChat,
    tg_partner: TgUser,
    tg_owner: TgUser,
    make_message: Callable[..., TgMessage],
) -> None:
    owner_settings.rescue_replies = False
    quoted = _photo_message(tg_chat, tg_partner, message_id=788)
    reply = make_message(
        text="молчи", message_id=789, from_user=tg_owner, reply_to_message=quoted
    )
    notifier = FakeNotifier()

    rescued = await _rescue(
        RescueService(CaptureService(), notifier), uow, owner, owner_settings, reply
    )

    assert rescued is False
    assert notifier.empty
