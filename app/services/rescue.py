"""Спасение сообщений по ответу владельца.

Одноразовое фото Bot API боту не отдаёт: в business_message оно приходит либо
пустым конвертом, либо не приходит вовсе. Но когда владелец отвечает на такое
сообщение, Telegram кладёт оригинал в reply_to_message — вместе с file_id
вложения. Этот сервис ловит цитату и:

* дописывает пропущенное сообщение в архив (или достраивает пустой конверт);
* скачивает файл, даже если автозагрузка выключена;
* присылает вложение владельцу в чат с ботом.

Приём работает не только с одноразовыми: так же спасается любое сообщение,
которого нет в архиве, — например, присланное до подключения бота.
Если в цитате нет вложения, сообщение просто молча сохраняется: лишние
карточки на каждый ответ владельцу не нужны.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from app.business.extractor import extract
from app.utils.formatting import content_label, message_card

if TYPE_CHECKING:
    from app.models.settings import UserSettings
    from app.models.user import User
    from app.repositories.uow import UnitOfWork
    from app.services.capture import CaptureService
    from app.services.notifier import NotificationService

logger = structlog.get_logger(__name__)

RESCUE_HEADER = "🛟 <b>Спасено из ответа</b>"

#: Расширение по типу вложения — имя файла Telegram отдаёт не всегда.
EXTENSIONS: dict[str, str] = {
    "photo": ".jpg",
    "video": ".mp4",
    "animation": ".mp4",
    "video_note": ".mp4",
    "voice": ".ogg",
    "audio": ".mp3",
    "sticker": ".webp",
}


@dataclass(slots=True)
class RescuedFile:
    """Файл, который нужно вернуть владельцу."""

    media_type: str
    file_id: str
    file_name: str | None = None
    local_path: str | None = None


def _read(path: str | None) -> bytes | None:
    """Прочитать скачанный файл. Нет файла — не беда, отправим по file_id."""
    if not path:
        return None
    try:
        content = Path(path).read_bytes()
    except OSError as error:  # файл могла унести автоуборка
        logger.warning("rescue.read_failed", path=path, error=str(error))
        return None
    return content or None


def _filename(item: RescuedFile) -> str:
    """Имя файла для отправки документом."""
    if item.file_name:
        return item.file_name
    if item.local_path:
        name = Path(item.local_path).name
        if name:
            return name
    return f"{item.media_type}{EXTENSIONS.get(item.media_type, '.bin')}"


class RescueService:
    """Достаёт из цитаты то, чего не оказалось в архиве."""

    def __init__(self, capture: CaptureService, notifier: NotificationService) -> None:
        self.capture = capture
        self.notifier = notifier

    async def rescue_from_reply(
        self,
        uow: UnitOfWork,
        *,
        owner: User,
        settings: UserSettings,
        message: Any,
        owner_chat_id: int,
        connection_id: str | None = None,
    ) -> bool:
        """Разобрать ответ и вернуть True, если вложение отправлено владельцу.

        Сообщение из цитаты сохраняется в архив в любом случае; False значит
        лишь то, что отправлять было нечего (текст или уже сохранённое медиа).
        """
        if not getattr(settings, "rescue_replies", True):
            return False
        reply = getattr(message, "reply_to_message", None)
        if reply is None:
            return False

        telegram_message_id = int(getattr(reply, "message_id", 0) or 0)
        if telegram_message_id <= 0:
            # Одноразовые сообщения приходят с message_id = 0: в архиве такую
            # запись не отличить от следующей такой же, поэтому только отдаём файл.
            return await self._rescue_without_archive(
                owner=owner, reply=reply, owner_chat_id=owner_chat_id
            )

        chat = getattr(reply, "chat", None) or getattr(message, "chat", None)
        if chat is None:
            return False
        chat_record = await uow.chats.get_or_create(owner.id, chat)
        record = await uow.messages.find_by_telegram_id(
            owner.id, chat_record.id, telegram_message_id
        )

        if record is None:
            sender = getattr(reply, "from_user", None)
            sender_id = getattr(sender, "id", None)
            is_outgoing = sender_id is not None and int(sender_id) == int(owner.telegram_id)
            record = await self.capture.capture_message(
                uow,
                owner=owner,
                settings=settings,
                message=reply,
                connection_id=connection_id,
                is_outgoing=is_outgoing,
                force_download=True,
            )
            media = list(record.media or [])
        else:
            # Запись есть, но пустая: Telegram прислал конверт без вложения,
            # а в цитате file_id оказался на месте.
            media = await self.capture.attach_media(
                uow, owner=owner, settings=settings, record=record, message=reply
            )

        if not media:
            return False

        files = [
            RescuedFile(
                media_type=row.media_type,
                file_id=row.file_id,
                file_name=row.file_name,
                local_path=row.local_path,
            )
            for row in media
        ]
        logger.info(
            "rescue.reply",
            owner_id=owner.id,
            telegram_message_id=telegram_message_id,
            files=len(files),
        )
        await self._deliver(
            owner_chat_id,
            f"{RESCUE_HEADER}\n\n{message_card(record, media)}",
            files,
        )
        return True

    async def _rescue_without_archive(
        self, *, owner: User, reply: Any, owner_chat_id: int
    ) -> bool:
        """Отдать вложение из цитаты, которую нельзя положить в архив."""
        parsed = extract(reply)
        if not parsed.media:
            return False

        downloader = getattr(self.capture, "downloader", None)
        files: list[RescuedFile] = []
        for payload in parsed.media:
            local_path = None
            if downloader is not None:
                local_path = await downloader.download(
                    owner_telegram_id=owner.telegram_id, payload=payload
                )
            files.append(
                RescuedFile(
                    media_type=payload.media_type,
                    file_id=payload.file_id,
                    file_name=payload.file_name,
                    local_path=local_path,
                )
            )

        logger.info("rescue.ephemeral_reply", owner_id=owner.id, files=len(files))
        text = (
            f"{RESCUE_HEADER}\n\n"
            f"{content_label(parsed.content_type)} из цитаты. Telegram прислал "
            "сообщение без номера — в архив оно не попало, файл ниже."
        )
        await self._deliver(owner_chat_id, text, files)
        return True

    async def _deliver(self, chat_id: int, text: str, files: list[RescuedFile]) -> None:
        """Шлём медиа с текстом как подписью. Для video_note/стикера подпись
        не поддерживается — там сначала текст, потом файл.
        """
        from app.services.notifier import CAPTION_LIMIT, FILE_METHODS, clip  # local import
        if not files:
            await self.notifier.send(chat_id, text)
            return
        first, *rest = files
        _, _, supports_caption = FILE_METHODS.get(first.media_type, (None, None, True))
        caption = clip(text, CAPTION_LIMIT) if supports_caption else None
        if not supports_caption:
            await self.notifier.send(chat_id, text)
        content = _read(first.local_path)
        if content is not None:
            await self.notifier.send_document(chat_id, _filename(first), content,
                                              caption=caption)
        else:
            await self.notifier.send_by_file_id(
                chat_id, first.media_type, first.file_id, caption=caption
            )
        for item in rest:
            content = _read(item.local_path)
            if content is not None:
                await self.notifier.send_document(chat_id, _filename(item), content)
            else:
                await self.notifier.send_by_file_id(chat_id, item.media_type, item.file_id)
