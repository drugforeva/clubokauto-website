"""Клавиатуры настроек.

Список TOGGLES — единственное место, где описаны переключатели.
Имена полей совпадают с TOGGLE_FIELDS в репозитории настроек: так через
кнопку нельзя переключить ничего постороннего.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config.settings import RETENTION_CHOICES
from app.keyboards.callbacks import SettingsCB
from app.keyboards.menu import menu_button

TOGGLES: tuple[tuple[str, str], ...] = (
    ("notify_deletions", "🗑 Уведомлять об удалениях"),
    ("notify_edits", "✏️ Уведомлять о правках"),
    ("notify_outgoing", "📤 Уведомлять о своих сообщениях"),
    ("save_media", "📎 Сохранять вложения"),
    ("download_media", "⬇️ Скачивать файлы на диск"),
    ("rescue_replies", "🛟 Доставать медиа из ответов"),
)

RETENTION_LABELS: dict[int, str] = {
    0: "Бессрочно",
    7: "7 дней",
    30: "30 дней",
    90: "90 дней",
    180: "180 дней",
    365: "365 дней",
}


def retention_label(days: int) -> str:
    return RETENTION_LABELS.get(int(days), f"{days} дн.")


def settings_keyboard(user_settings: Any) -> InlineKeyboardMarkup:
    """Переключатели с текущим состоянием прямо на кнопках."""
    builder = InlineKeyboardBuilder()
    for field, title in TOGGLES:
        state = "🟢" if bool(getattr(user_settings, field, False)) else "⚪️"
        builder.row(
            InlineKeyboardButton(
                text=f"{state} {title}",
                callback_data=SettingsCB(action="toggle", field=field).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=f"🌍 Часовой пояс: {getattr(user_settings, 'timezone', '—')}",
            callback_data=SettingsCB(action="timezone").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"🗓 Срок хранения: {retention_label(getattr(user_settings, 'retention_days', 0))}",
            callback_data=SettingsCB(action="retention").pack(),
        )
    )
    builder.row(menu_button())
    return builder.as_markup()


def retention_keyboard(current: int = 0) -> InlineKeyboardMarkup:
    """Выбор срока автоуборки."""
    builder = InlineKeyboardBuilder()
    for days in RETENTION_CHOICES:
        title = retention_label(days)
        builder.button(
            text=f"✅ {title}" if int(days) == int(current) else title,
            callback_data=SettingsCB(action="set_retention", value=int(days)),
        )
    builder.adjust(2, 2, 2)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К настройкам",
            callback_data=SettingsCB(action="open").pack(),
        )
    )
    return builder.as_markup()


def back_to_settings() -> InlineKeyboardMarkup:
    """Отмена ввода часового пояса."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ К настройкам",
                    callback_data=SettingsCB(action="open").pack(),
                )
            ]
        ]
    )
