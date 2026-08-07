"""Захват событий бизнес-чата: новое сообщение, правка, удаление.

Главная тонкость — set_committed_value. Связи media/edits/chat грузятся
стратегией selectin/joined, но у только что созданного объекта они не заполнены:
обращение к message.media сразу после flush вызывает ленивую догрузку и падает
с MissingGreenlet в asyncio. set_committed_value кладёт значение в обход загрузчика,
поэтому уведомления формируются без лишних запросов.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.orm.attributes import set_committed_value

from app.business.extractor import extract
from app.models.media import Media
from app.models.message import Message
from app.utils.time import as_datetime, utcnow

if TYPE_CHECKING:
    from app.models.chat import Chat
    from app.models.edit import MessageEdit
    from app.models.settings import UserSettings
    from app.models.user import User
    from app.repositories.uow import UnitOfWork
    from app.services.downloader import FileDownloader

logger = structlog.get_logger(__name__)


def _media_rows(message_id: int, payloads: list[Any]) -> list[Media]:
    """Строки вложений — один формат для записи и для достройки."""
    return [
        Media(
            message_id=message_id,
            media_type=payload.media_type,
            file_id=payload.file_id,
            file_unique_id=payload.file_unique_id,
            file_name=payload.file_name,
            mime_type=payload.mime_type,
            file_size=payload.file_size,
            duration=payload.duration,
        )
        for payload in payloads
    ]


class CaptureService:
    """Вся запись в архив идёт через этот сервис."""

    def __init__(self, downloader: FileDownloader | None = None) -> None:
        self.downloader = downloader

    async def capture_message(
        self,
        uow: UnitOfWork,
        *,
        owner: User,
        settings: UserSettings,
        message: Any,
        connection_id: str | None = None,
        is_outgoing: bool = False,
        force_download: bool = False,
    ) -> Message:
        """Сохранить сообщение. Повторный апдейт возвращает уже сохранённую запись."""
        chat = await uow.chats.get_or_create(owner.id, message.chat)
        telegram_message_id = int(getattr(message, "message_id", 0) or 0)
        existing = await uow.messages.find_by_telegram_id(
            owner.id, chat.id, telegram_message_id
        )
        if existing is not None:
            return existing

        parsed = extract(message)
        sender = getattr(message, "from_user", None)
        reply_to = getattr(message, "reply_to_message", None)
        record = Message(
            owner_id=owner.id,
            chat_id=chat.id,
            connection_id=connection_id,
            telegram_message_id=telegram_message_id,
            sender_id=getattr(sender, "id", None),
            sender_username=getattr(sender, "username", None),
            sender_first_name=getattr(sender, "first_name", None),
            sender_last_name=getattr(sender, "last_name", None),
            is_outgoing=is_outgoing,
            content_type=parsed.content_type,
            text=parsed.text,
            extra_data=parsed.extra,
            reply_to_message_id=getattr(reply_to, "message_id", None),
            sent_at=as_datetime(getattr(message, "date", None)) or utcnow(),
        )
        await uow.messages.add(record)

        media_rows: list[Media] = []
        if settings.save_media and parsed.media:
            media_rows = _media_rows(record.id, parsed.media)
            await uow.media.add_many(media_rows)
            # Одноразовое медиа живёт секунды: file_id умирает вместе с сообщением,
            # поэтому такой файл тянем сразу, даже если автозагрузка выключена.
            ephemeral = bool((parsed.extra or {}).get("ephemeral"))
            if ephemeral:
                logger.warning(
                    "capture.ephemeral",
                    owner_id=owner.id,
                    content_type=parsed.content_type,
                    fields=sorted((parsed.extra or {}).get("ephemeral_fields", {})),
                )
            wanted = settings.download_media or ephemeral or force_download
            if wanted and self.downloader is not None:
                await self._download_all(owner, parsed.media, media_rows)

        # Связи заполняются вручную — см. комментарий в начале модуля.
        set_committed_value(record, "media", media_rows)
        set_committed_value(record, "edits", [])
        set_committed_value(record, "chat", chat)
        logger.debug(
            "capture.message",
            owner_id=owner.id,
            content_type=record.content_type,
            media=len(media_rows),
        )
        return record

    async def _download_all(
        self, owner: User, payloads: list[Any], rows: list[Media]
    ) -> None:
        """Скачать вложения и запомнить пути."""
        if self.downloader is None:
            return
        for payload, row in zip(payloads, rows, strict=False):
            local_path = await self.downloader.download(
                owner_telegram_id=owner.telegram_id, payload=payload
            )
            if local_path:
                row.local_path = local_path
                row.downloaded_at = utcnow()

    async def attach_media(
        self,
        uow: UnitOfWork,
        *,
        owner: User,
        settings: UserSettings,
        record: Message,
        message: Any,
    ) -> list[Media]:
        """Дописать вложения к сообщению, сохранённому без них.

        Одноразовое фото приходит в business_message пустым конвертом, зато в
        цитате ответа file_id уже есть: тогда запись достраивается, а файл
        скачивается сразу, не спрашивая настройку автозагрузки.
        """
        parsed = extract(message)
        if not parsed.media or not settings.save_media:
            return []
        if await uow.media.for_message(record.id):
            return []

        rows = _media_rows(record.id, parsed.media)
        await uow.media.add_many(rows)
        await self._download_all(owner, parsed.media, rows)
        if record.content_type in {"unknown", "text"}:
            record.content_type = parsed.content_type
        if not record.text and parsed.text:
            record.text = parsed.text
        set_committed_value(record, "media", rows)
        logger.info("capture.attach_media", owner_id=owner.id, media=len(rows))
        return rows

    async def capture_edit(
        self,
        uow: UnitOfWork,
        *,
        owner: User,
        settings: UserSettings,
        message: Any,
        connection_id: str | None = None,
        is_outgoing: bool = False,
    ) -> tuple[Message, list[MessageEdit]]:
        """Записать правку и вернуть все версии текста.

        Если сообщения нет в архиве (пришло до подключения), сохраняем его
        как новое: версий у такого сообщения ещё нет.
        """
        chat = await uow.chats.get_or_create(owner.id, message.chat)
        telegram_message_id = int(getattr(message, "message_id", 0) or 0)
        record = await uow.messages.find_by_telegram_id(owner.id, chat.id, telegram_message_id)
        if record is None:
            created = await self.capture_message(
                uow,
                owner=owner,
                settings=settings,
                message=message,
                connection_id=connection_id,
                is_outgoing=is_outgoing,
            )
            return created, []

        edited_at = as_datetime(getattr(message, "edit_date", None)) or utcnow()
        versions = await uow.edits.for_message(record.id)
        if not versions:
            # Версия 1 — текст до правки. Без неё исходник был бы потерян.
            first = await uow.edits.add(
                message_id=record.id,
                version=1,
                text=record.text,
                edited_at=record.sent_at,
            )
            versions = [first]

        parsed = extract(message)
        next_version = await uow.edits.next_version(record.id)
        latest = await uow.edits.add(
            message_id=record.id,
            version=next_version,
            text=parsed.text,
            edited_at=edited_at,
        )
        versions = [*versions, latest]

        record.text = parsed.text
        record.extra_data = parsed.extra
        record.edited_at = edited_at
        record.edit_count = max(len(versions) - 1, 1)

        set_committed_value(record, "edits", versions)
        set_committed_value(record, "chat", chat)
        logger.debug("capture.edit", owner_id=owner.id, versions=len(versions))
        return record, versions

    async def capture_deletions(
        self,
        uow: UnitOfWork,
        *,
        owner: User,
        settings: UserSettings,
        chat: Any,
        telegram_message_ids: list[int],
    ) -> tuple[list[Message], int]:
        """Отметить удалённые сообщения.

        Возвращает найденные записи и число удалений, которых в архиве не было:
        Telegram присылает удаления пачкой и по старым сообщениям тоже.
        """
        chat_record: Chat = await uow.chats.get_or_create(owner.id, chat)
        ids = [int(item) for item in telegram_message_ids or []]
        found = await uow.messages.find_in_chat_ids(owner.id, [chat_record.id], ids)
        found_ids = {record.telegram_message_id for record in found}

        for record in found:
            await uow.messages.mark_deleted(record)
            await uow.deleted.add(
                owner_id=owner.id,
                message_id=record.id,
                chat_id=chat_record.id,
                telegram_message_id=record.telegram_message_id,
                notified=settings.notify_deletions,
            )
            set_committed_value(record, "chat", chat_record)

        unknown = [item for item in ids if item not in found_ids]
        for telegram_message_id in unknown:
            await uow.deleted.add(
                owner_id=owner.id,
                message_id=None,
                chat_id=chat_record.id,
                telegram_message_id=telegram_message_id,
                notified=False,
            )
        logger.debug(
            "capture.deletions",
            owner_id=owner.id,
            found=len(found),
            unknown=len(unknown),
        )
        return found, len(unknown)
