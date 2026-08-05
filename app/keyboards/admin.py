"""Клавиатуры админ-панели."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import AdminCB
from app.keyboards.menu import menu_button
from app.utils.formatting import short_label
from app.utils.pagination import Page
from app.utils.text import shorten


def admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Пользователи", callback_data=AdminCB(action="users", page=1))
    builder.button(text="🗑 Удаления", callback_data=AdminCB(action="deleted"))
    builder.button(text="📣 Рассылка", callback_data=AdminCB(action="broadcast"))
    builder.button(text="♻️ Обновить", callback_data=AdminCB(action="home"))
    builder.adjust(2, 2)
    builder.row(menu_button())
    return builder.as_markup()


def _nav_row(page: Page[Any], action: str, **extra: int) -> list[InlineKeyboardButton]:
    """Общая строка пагинации для админских списков."""
    row: list[InlineKeyboardButton] = []
    if page.has_prev:
        row.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=AdminCB(action=action, page=page.number - 1, **extra).pack(),
            )
        )
    if page.pages > 1:
        row.append(
            InlineKeyboardButton(
                text=page.label,
                callback_data=AdminCB(action="noop", page=page.number, **extra).pack(),
            )
        )
    if page.has_next:
        row.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=AdminCB(action=action, page=page.number + 1, **extra).pack(),
            )
        )
    return row


def users_keyboard(page: Page[Any]) -> InlineKeyboardMarkup:
    """Список пользователей бота."""
    builder = InlineKeyboardBuilder()
    for user in page.items:
        mark = "🚫 " if getattr(user, "is_blocked", False) else ""
        username = f" @{user.username}" if getattr(user, "username", None) else ""
        builder.row(
            InlineKeyboardButton(
                text=shorten(f"{mark}{user.display_name}{username}", 40),
                callback_data=AdminCB(
                    action="user", page=page.number, user_id=int(user.id)
                ).pack(),
            )
        )
    nav = _nav_row(page, "users")
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Админ-панель", callback_data=AdminCB(action="home").pack()
        )
    )
    return builder.as_markup()


def user_card_keyboard(user_id: int, page: int = 1) -> InlineKeyboardMarkup:
    """Карточка пользователя."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="💬 Сообщения",
            callback_data=AdminCB(action="messages", page=1, user_id=user_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К списку", callback_data=AdminCB(action="users", page=page).pack()
        ),
        menu_button(),
    )
    return builder.as_markup()


def user_messages_keyboard(page: Page[Any], user_id: int) -> InlineKeyboardMarkup:
    """Сообщения конкретного владельца глазами админа."""
    builder = InlineKeyboardBuilder()
    for offset, message in enumerate(page.items):
        marks = ""
        if getattr(message, "is_deleted", False):
            marks += "🗑"
        if getattr(message, "edit_count", 0):
            marks += "✏️"
        body = getattr(message, "text", None) or short_label(
            getattr(message, "content_type", None)
        )
        builder.row(
            InlineKeyboardButton(
                text=f"{page.first_index + offset}. {marks}{shorten(body, 28)}",
                callback_data=AdminCB(
                    action="message",
                    page=page.number,
                    user_id=user_id,
                    message_id=int(message.id),
                ).pack(),
            )
        )
    nav = _nav_row(page, "messages", user_id=user_id)
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К пользователю",
            callback_data=AdminCB(action="user", page=1, user_id=user_id).pack(),
        ),
        menu_button(),
    )
    return builder.as_markup()


def admin_message_keyboard(
    message_id: int,
    user_id: int,
    *,
    page: int = 1,
    has_media: bool = False,
    has_versions: bool = False,
) -> InlineKeyboardMarkup:
    """Карточка сообщения в админке."""
    builder = InlineKeyboardBuilder()
    if has_media:
        builder.button(
            text="📎 Вложения",
            callback_data=AdminCB(
                action="media", page=page, user_id=user_id, message_id=message_id
            ),
        )
    if has_versions:
        builder.button(
            text="🕒 Версии",
            callback_data=AdminCB(
                action="versions", page=page, user_id=user_id, message_id=message_id
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К сообщениям",
            callback_data=AdminCB(action="messages", page=page, user_id=user_id).pack(),
        ),
        menu_button(),
    )
    return builder.as_markup()


def back_to_admin() -> InlineKeyboardMarkup:
    """Возврат в админ-панель (и отмена рассылки)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Админ-панель",
                    callback_data=AdminCB(action="home").pack(),
                )
            ]
        ]
    )
