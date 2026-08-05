"""Клавиатуры поиска.

Фильтры собираются по шагам и хранятся в FSM, а не в callback_data:
текст запроса легко переваливает лимит 64 байта.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import SearchCB
from app.keyboards.menu import menu_button
from app.utils.formatting import short_label
from app.utils.pagination import Page
from app.utils.text import shorten


def search_menu(state_data: dict[str, Any] | None = None) -> InlineKeyboardMarkup:
    """Меню поиска с галками на заполненных фильтрах."""
    data = state_data or {}
    mark = lambda key, title: f"✅ {title}" if data.get(key) else title  # noqa: E731

    builder = InlineKeyboardBuilder()
    builder.button(text=mark("query", "🔤 Текст"), callback_data=SearchCB(action="query"))
    builder.button(text=mark("sender", "👤 Автор"), callback_data=SearchCB(action="sender"))
    builder.button(
        text=mark("date_from", "📅 С даты"), callback_data=SearchCB(action="date_from")
    )
    builder.button(
        text=mark("date_to", "📅 По дату"), callback_data=SearchCB(action="date_to")
    )
    builder.button(
        text=("✅ С удалёнными" if data.get("only_deleted") else "🗑 Только удалённые"),
        callback_data=SearchCB(action="only_deleted"),
    )
    builder.button(
        text=("✅ Со своими" if data.get("include_outgoing") else "📤 Со своими"),
        callback_data=SearchCB(action="include_outgoing"),
    )
    builder.adjust(2, 2, 2)
    builder.row(
        InlineKeyboardButton(
            text="🔍 Найти", callback_data=SearchCB(action="run", page=1).pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="♻️ Сбросить", callback_data=SearchCB(action="reset").pack()
        ),
        menu_button(),
    )
    return builder.as_markup()


def cancel_input() -> InlineKeyboardMarkup:
    """Отмена ввода значения."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к поиску",
                    callback_data=SearchCB(action="open").pack(),
                )
            ]
        ]
    )


def results_keyboard(page: Page[Any]) -> InlineKeyboardMarkup:
    """Результаты поиска с пагинацией."""
    builder = InlineKeyboardBuilder()
    for offset, message in enumerate(page.items):
        body = getattr(message, "text", None) or short_label(
            getattr(message, "content_type", None)
        )
        builder.row(
            InlineKeyboardButton(
                text=f"{page.first_index + offset}. {shorten(body, 30)}",
                callback_data=SearchCB(
                    action="show", page=page.number, message_id=int(message.id)
                ).pack(),
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page.has_prev:
        nav.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=SearchCB(action="run", page=page.number - 1).pack(),
            )
        )
    if page.pages > 1:
        nav.append(
            InlineKeyboardButton(
                text=page.label,
                callback_data=SearchCB(action="noop", page=page.number).pack(),
            )
        )
    if page.has_next:
        nav.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=SearchCB(action="run", page=page.number + 1).pack(),
            )
        )
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="⚙️ Фильтры", callback_data=SearchCB(action="open").pack()
        ),
        menu_button(),
    )
    return builder.as_markup()


def result_card_keyboard(page: int) -> InlineKeyboardMarkup:
    """Карточка найденного сообщения."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ К результатам",
                    callback_data=SearchCB(action="run", page=page).pack(),
                ),
                menu_button(),
            ]
        ]
    )
