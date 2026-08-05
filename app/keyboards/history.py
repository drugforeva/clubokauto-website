
"""Клавиатуры истории и карточки сообщения."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import HistoryCB
from app.keyboards.menu import menu_button
from app.utils.formatting import short_label
from app.utils.pagination import Page
from app.utils.text import shorten


def _chat_display(chat: Any) -> str:
    username = getattr(chat, "username", None)
    if username:
        return f"@{username}"
    first = getattr(chat, "first_name", None) or ""
    last = getattr(chat, "last_name", None) or ""
    name = f"{first} {last}".strip()
    title = getattr(chat, "title", None)
    return name or title or f"chat {getattr(chat, "telegram_chat_id", "?")}"


def chats_keyboard(chats: list[Any]) -> InlineKeyboardMarkup:
    """Список собеседников для выбора."""
    builder = InlineKeyboardBuilder()
    for chat in chats:
        builder.row(
            InlineKeyboardButton(
                text=_chat_display(chat),
                callback_data=HistoryCB(
                    action="list",
                    scope="deleted",
                    page=1,
                    chat_id=int(chat.id),
                ).pack(),
            )
        )
    builder.row(menu_button())
    return builder.as_markup()


def _row_label(index: int, message: Any) -> str:
    marks = ""
    if getattr(message, "is_deleted", False):
        marks += "✓"
    if getattr(message, "edit_count", 0):
        marks += "✏️"
    body = getattr(message, "text", None) or short_label(
        getattr(message, "content_type", None)
    )
    prefix = f"{marks} " if marks else ""
    return f"{index}. {prefix}{shorten(body, 32)}".strip()


SCOPES: tuple[tuple[str, str], ...] = (
    ("deleted", "🗑 Удалённые"),
    ("edited", "✏️ Изменённые"),
    ("all", "📋 Все"),
)


def history_keyboard(
    page: Page,
    scope: str = "deleted",
    chat_id: int = 0,
) -> InlineKeyboardMarkup:
    """Список сообщений + пагинация + фильтр."""
    builder = InlineKeyboardBuilder()
    for offset, message in enumerate(page.items):
        builder.row(
            InlineKeyboardButton(
                text=_row_label(page.first_index + offset, message),
                callback_data=HistoryCB(
                    action="open",
                    scope=scope,
                    page=page.number,
                    message_id=int(message.id),
                    chat_id=chat_id,
                ).pack(),
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page.has_prev:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=HistoryCB(
                    action="list", scope=scope, page=page.number - 1, chat_id=chat_id
                ).pack(),
            )
        )
    if page.pages > 1:
        nav.append(
            InlineKeyboardButton(
                text=page.label,
                callback_data=HistoryCB(
                    action="noop", scope=scope, page=page.number, chat_id=chat_id
                ).pack(),
            )
        )
    if page.has_next:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=HistoryCB(
                    action="list", scope=scope, page=page.number + 1, chat_id=chat_id
                ).pack(),
            )
        )
    if nav:
        builder.row(*nav)

    scope_row = [
        InlineKeyboardButton(
            text=f"✅ {title}" if code == scope else title,
            callback_data=HistoryCB(
                action="list", scope=code, page=1, chat_id=chat_id
            ).pack(),
        )
        for code, title in SCOPES
    ]
    builder.row(*scope_row)

    back_row = []
    if chat_id:
        back_row.append(
            InlineKeyboardButton(
                text="← К собеседникам",
                callback_data=HistoryCB(action="chats").pack(),
            )
        )
    back_row.append(menu_button())
    builder.row(*back_row)
    return builder.as_markup()


def message_keyboard(
    message_id: int,
    *,
    has_media: bool = False,
    has_versions: bool = False,
    scope: str = "deleted",
    page: int = 1,
    chat_id: int = 0,
) -> InlineKeyboardMarkup:
    """Карточка сообщения: вложения, версии, возврат к списку."""
    builder = InlineKeyboardBuilder()
    if has_media:
        builder.button(
            text="📎 Вложения",
            callback_data=HistoryCB(
                action="media", scope=scope, page=page,
                message_id=message_id, chat_id=chat_id,
            ),
        )
    if has_versions:
        builder.button(
            text="🕒 Версии текста",
            callback_data=HistoryCB(
                action="versions", scope=scope, page=page,
                message_id=message_id, chat_id=chat_id,
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К списку",
            callback_data=HistoryCB(
                action="list", scope=scope, page=page, chat_id=chat_id
            ).pack(),
        ),
        menu_button(),
    )
    return builder.as_markup()


def notification_keyboard(message_id: int) -> InlineKeyboardMarkup:
    """Кнопка под уведомлением — открыть полную карточку."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔎 Подробнее",
                    callback_data=HistoryCB(
                        action="open", scope="deleted", page=1,
                        message_id=int(message_id),
                    ).pack(),
                )
            ]
        ]
    )
