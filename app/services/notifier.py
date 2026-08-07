"""Доставка уведомлений владельцу архива.

Здесь собрана вся работа с ошибками Telegram, чтобы роутеры о них не думали:

* пользователь заблокировал бота — это не авария, а факт (SendResult.blocked);
* требование подождать (flood control) — ждём и пробуем ещё раз;
* слишком длинный текст — обрезаем до лимита Telegram до отправки.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

from app.utils.formatting import deletion_notice, edit_notice, unknown_deletion_notice

logger = structlog.get_logger(__name__)

MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024
MAX_ATTEMPTS = 2
MAX_WAIT_SECONDS = 30

#: Лимиты Telegram: около 30 сообщений в секунду на бота и примерно
#: одно в секунду в один чат. Берём с запасом.
DEFAULT_RATE = 25.0
DEFAULT_CHAT_INTERVAL = 0.35

#: Потолок таблицы чатов в лимитере.
MAX_TRACKED_CHATS = 10_000

#: Сколько вложений максимум шлём при массовом удалении.
MAX_BATCH_MEDIA = 20

SEPARATOR = "\n\n"

#: Как отправить файл, зная только file_id: метод Bot API, имя
#: аргумента и поддерживает ли метод подпись.
FILE_METHODS: dict[str, tuple[str, str, bool]] = {
    "photo": ("send_photo", "photo", True),
    "video": ("send_video", "video", True),
    "animation": ("send_animation", "animation", True),
    "audio": ("send_audio", "audio", True),
    "voice": ("send_voice", "voice", True),
    "document": ("send_document", "document", True),
    "video_note": ("send_video_note", "video_note", False),
    "sticker": ("send_sticker", "sticker", False),
}
DEFAULT_FILE_METHOD = ("send_document", "document", True)


@dataclass(slots=True)
class SendResult:
    """Итог отправки: дошло ли и не заблокирован ли бот."""

    ok: bool = False
    blocked: bool = False


def clip(text: str, limit: int = MESSAGE_LIMIT) -> str:
    """Обрезать тем до лимита Telegram.

    Длинные сообщения реально бывают, а ошибка «message is too long» съедает
    уведомление целиком, поэтому лучше доставить усечённый текст.
    """
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


def pack(blocks: list[str], header: str = "", limit: int = MESSAGE_LIMIT) -> list[str]:
    """Сложить куски текста в минимальное число сообщений."""
    chunks: list[str] = []
    current = header
    for block in blocks:
        piece = clip(block, limit)
        candidate = current + SEPARATOR + piece if current else piece
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = piece
    if current:
        chunks.append(current)
    return chunks


class RateLimiter:
    """Очередь отправки: общий лимит на бота плюс лимит на каждый чат."""

    def __init__(
        self,
        rate: float = DEFAULT_RATE,
        chat_interval: float = DEFAULT_CHAT_INTERVAL,
    ) -> None:
        self.interval = 1.0 / rate if rate > 0 else 0.0
        self.chat_interval = max(chat_interval, 0.0)
        self._lock = asyncio.Lock()
        self._next_global = 0.0
        self._next_chat: OrderedDict[int, float] = OrderedDict()

    async def acquire(self, chat_id: int) -> None:
        """Дождаться своей очереди. Сон — вне замка, иначе очередь встанет."""
        if self.interval <= 0 and self.chat_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            planned = max(now, self._next_global, self._next_chat.get(chat_id, 0.0))
            self._next_global = planned + self.interval
            if self.chat_interval:
                self._next_chat[chat_id] = planned + self.chat_interval
                self._next_chat.move_to_end(chat_id)
                while len(self._next_chat) > MAX_TRACKED_CHATS:
                    self._next_chat.popitem(last=False)
            delay = planned - now
        if delay > 0:
            await asyncio.sleep(delay)


class NotificationService:
    """Тонкая обёртка над Bot API для исходящих сообщений бота."""

    def __init__(
        self,
        bot: Any,
        rate: float = DEFAULT_RATE,
        chat_interval: float = DEFAULT_CHAT_INTERVAL,
    ) -> None:
        self.bot = bot
        self.limiter = RateLimiter(rate, chat_interval)

    async def send(
        self,
        chat_id: int,
        text: str,
        keyboard: InlineKeyboardMarkup | None = None,
    ) -> SendResult:
        """Отправить текст, никогда не выбрасывая исключение наружу."""
        payload = clip(text)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            # Свой лимитер дешевле, чем ловить flood control постфактум.
            await self.limiter.acquire(chat_id)
            try:
                await self.bot.send_message(
                    chat_id, payload, reply_markup=keyboard
                )
                return SendResult(ok=True)
            except TelegramForbiddenError:
                logger.info("notify.blocked", chat_id=chat_id)
                return SendResult(ok=False, blocked=True)
            except TelegramRetryAfter as error:
                if attempt >= MAX_ATTEMPTS:
                    logger.warning("notify.flood", chat_id=chat_id)
                    return SendResult(ok=False)
                await asyncio.sleep(min(error.retry_after + 1, MAX_WAIT_SECONDS))
            except TelegramAPIError as error:
                logger.warning("notify.failed", chat_id=chat_id, error=str(error))
                return SendResult(ok=False)
        return SendResult(ok=False)

    async def send_document(
        self,
        chat_id: int,
        filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> SendResult:
        """Отправить готовый файл из памяти (экспорт архива)."""
        document = BufferedInputFile(content, filename=filename)
        await self.limiter.acquire(chat_id)
        try:
            await self.bot.send_document(
                chat_id,
                document,
                caption=clip(caption, CAPTION_LIMIT) if caption else None,
            )
        except TelegramForbiddenError:
            logger.info("notify.blocked", chat_id=chat_id)
            return SendResult(ok=False, blocked=True)
        except TelegramAPIError as error:
            logger.warning("notify.document_failed", chat_id=chat_id, error=str(error))
            return SendResult(ok=False)
        return SendResult(ok=True)

    async def send_by_file_id(
        self,
        chat_id: int,
        media_type: str,
        file_id: str,
        caption: str | None = None,
        keyboard: InlineKeyboardMarkup | None = None,
    ) -> SendResult:
        """Переслать вложение по file_id, не скачивая его на диск.

        file_id живёт, пока живо исходное сообщение, поэтому способ хорош
        как запасной: основной путь — отправка уже скачанного файла.
        """
        method_name, field, supports_caption = FILE_METHODS.get(
            media_type, DEFAULT_FILE_METHOD
        )
        sender = getattr(self.bot, method_name, None)
        if sender is None:
            method_name, field, supports_caption = DEFAULT_FILE_METHOD
            sender = self.bot.send_document
        kwargs: dict[str, Any] = {"chat_id": chat_id, field: file_id}
        if caption and supports_caption:
            kwargs["caption"] = clip(caption, CAPTION_LIMIT)
        if keyboard:
            kwargs["reply_markup"] = keyboard
        await self.limiter.acquire(chat_id)
        try:
            await sender(**kwargs)
        except TelegramForbiddenError:
            logger.info("notify.blocked", chat_id=chat_id)
            return SendResult(ok=False, blocked=True)
        except TelegramAPIError as error:
            logger.warning(
                "notify.file_failed",
                chat_id=chat_id,
                media_type=media_type,
                error=str(error),
            )
            return SendResult(ok=False)
        return SendResult(ok=True)

    async def notify_deletion(
        self,
        chat_id: int,
        message: Any,
        media: list[Any] | None = None,
        keyboard: InlineKeyboardMarkup | None = None,
    ) -> SendResult:
        """Главный сценарий: собеседник удалил сообщение.

        Если у сообщения есть вложения — отправляем само фото/видео/голос
        с текстом удаления как подписью. Так пользователь сразу видит медиа,
        а не получает текст + отдельный файл.
        """
        notice = deletion_notice(message, media)
        if media:
            first, *rest = media
            result = await self.send_by_file_id(
                chat_id,
                first.media_type,
                first.file_id,
                caption=notice,
                keyboard=keyboard,
            )
            for item in rest:
                await self.send_by_file_id(chat_id, item.media_type, item.file_id)
            return result
        return await self.send(chat_id, notice, keyboard)

    async def notify_deletions(
        self,
        chat_id: int,
        records: list[Any],
        keyboard_factory: Callable[[int], Any] | None = None,
        media_limit: int = MAX_BATCH_MEDIA,
    ) -> SendResult:
        """Пачка удалений — одним списком вместо сотни уведомлений."""
        if not records:
            return SendResult(ok=True)

        if len(records) == 1:
            record = records[0]
            keyboard = keyboard_factory(record.id) if keyboard_factory else None
            return await self.notify_deletion(
                chat_id, record, list(record.media or []), keyboard
            )

        blocks = [
            deletion_notice(record, list(record.media or [])) for record in records
        ]
        header = "\U0001f5d1 <b>Удалено сообщений: " + str(len(records)) + "</b>"
        result = SendResult(ok=True)
        for chunk in pack(blocks, header=header):
            result = await self.send(chat_id, chunk)
            if not result.ok:
                return result

        # Вложения досылаем отдельно и с потолком: выгружать сотню файлов
        # одним залпом бессмысленно — остальное есть в /history.
        sent = 0
        for record in records:
            for item in record.media or []:
                if sent >= media_limit:
                    logger.info(
                        "notify.media_truncated", chat_id=chat_id, limit=media_limit
                    )
                    return result
                media_type = getattr(item, "media_type", None)
                file_id = getattr(item, "file_id", None)
                if not media_type or not file_id:
                    continue
                await self.send_by_file_id(chat_id, media_type, file_id)
                sent += 1
        return result

    async def notify_edit(
        self,
        chat_id: int,
        message: Any,
        versions: list[Any] | None = None,
        keyboard: InlineKeyboardMarkup | None = None,
    ) -> SendResult:
        """Сообщение отредактировано: показываем все версии текста."""
        return await self.send(chat_id, edit_notice(message, versions), keyboard)

    async def notify_unknown_deletions(self, chat_id: int, count: int) -> SendResult:
        """Удаления без записи в архиве — честно предупреждаем владельца."""
        if count <= 0:
            return SendResult(ok=True)
        return await self.send(chat_id, unknown_deletion_notice(count))
