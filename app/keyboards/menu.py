"""Главное меню и общие кнопки навигации."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import MenuCB


def main_menu(*, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню. Админская кнопка показывается только админам."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗂 История", callback_data=MenuCB(action="history"))
    builder.button(text="📊 Статистика", callback_data=MenuCB(action="stats"))
    builder.button(text="📤 Экспорт", callback_data=MenuCB(action="export"))
    builder.button(text="❓ Помощь", callback_data=MenuCB(action="help"))
    builder.adjust(2, 2)
    if is_admin:
        builder.row(
            InlineKeyboardButton(
                text="🛠 Админ-панель",
                callback_data=MenuCB(action="admin").pack(),
            )
        )
    return builder.as_markup()


def menu_button() -> InlineKeyboardButton:
    """Кнопка «назад в меню» для встраивания в другие клавиатуры."""
    return InlineKeyboardButton(
        text="⬅️ В меню", callback_data=MenuCB(action="home").pack()
    )


def back_to_menu() -> InlineKeyboardMarkup:
    """Клавиатура из одной кнопки возврата."""
    return InlineKeyboardMarkup(inline_keyboard=[[menu_button()]])
