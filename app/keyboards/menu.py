"""Клавиатуры главного меню."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import AdminCB, MenuCB


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню. Админская строка — только для админов."""
    builder = InlineKeyboardBuilder()
    builder.button(text="\U0001f5c2 История", callback_data=MenuCB(action="history"))
    builder.button(text="\U0001f4ca Статистика", callback_data=MenuCB(action="stats"))
    builder.button(text="\U0001f4e6 Экспорт", callback_data=MenuCB(action="export"))
    builder.button(text="\U0001f50c Подключение", callback_data=MenuCB(action="connect"))
    builder.button(text="\u2753 Помощь", callback_data=MenuCB(action="help"))
    builder.adjust(2, 2, 1)
    if is_admin:
        builder.row(
            InlineKeyboardButton(
                text="\u2699\ufe0f Админ-панель",
                callback_data=AdminCB(action="home").pack(),
            )
        )
    return builder.as_markup()


def menu_button() -> InlineKeyboardMarkup:
    """Одна кнопка возврата в меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="\u25c0\ufe0f В меню", callback_data=MenuCB(action="home"))
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    """Синоним menu_button — оставлен ради старых вызовов."""
    return menu_button()


def guide_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура под гайдом по подключению."""
    builder = InlineKeyboardBuilder()
    builder.button(text="\u2753 Помощь", callback_data=MenuCB(action="help"))
    builder.button(text="\u25c0\ufe0f В меню", callback_data=MenuCB(action="home"))
    builder.adjust(2)
    return builder.as_markup()
