"""Доставка уведомлений владельцу архива.

Здесь собрана вся работа с ошибками Telegram, чтобы роутеры о них не думали:

* пользователь заблокировал бота — это не авария, а факт (SendResult.blocked);
* требование подождать (flood control) — ждём и пробуем ещё раз;
* слишком длинный текст — обрезаем до лимита Telegram до отправки.
"""

from __future__ import annotations

import asyncio
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


class NotificationService:
    """Тонкая обёртка над Bot API для исходящих сообщений бота."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot

    async def send(
        self,
        chat_id: int,
        text: str,
        keyboard: InlineKeyboardMarkup | None = None,
    ) -> SendResult:
        """Отправить текст, никогда не выбрасывая исключение наружу."""
        payload = clip(text)
        for attempt in range(1, MAX_ATTEMPTS + 1):
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
