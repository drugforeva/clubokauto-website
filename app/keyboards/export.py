"""Клавиатура экспорта.

Сначала выбирается объём (всё / только удалённые / только изменённые),
потом формат. Состояние хранится в callback_data — FSM здесь не нужен.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards.callbacks import ExportCB
from app.keyboards.menu import menu_button
from app.services.export import FORMAT_LABELS, FORMATS

SCOPES: tuple[tuple[str, str], ...] = (
    ("all", "Всё"),
    ("deleted", "🗑 Удалённые"),
    ("edited", "✏️ Изменённые"),
)


def export_menu(scope: str = "all") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        *[
            InlineKeyboardButton(
                text=f"✅ {title}" if code == scope else title,
                callback_data=ExportCB(action="open", scope=code).pack(),
            )
            for code, title in SCOPES
        ]
    )
    for fmt in FORMATS:
        builder.button(
            text=FORMAT_LABELS.get(fmt, fmt.upper()),
            callback_data=ExportCB(action="build", fmt=fmt, scope=scope),
        )
    builder.adjust(3, 2, 2)
    builder.row(menu_button())
    return builder.as_markup()
