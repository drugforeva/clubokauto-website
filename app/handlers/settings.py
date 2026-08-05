"""Настройки владельца: уведомления, вложения, часовой пояс, срок хранения."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config.settings import RETENTION_CHOICES
from app.handlers.common import show
from app.keyboards.callbacks import MenuCB, SettingsCB
from app.keyboards.settings import (
    back_to_settings,
    retention_keyboard,
    retention_label,
    settings_keyboard,
)
from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.settings import TOGGLE_FIELDS
from app.repositories.uow import UnitOfWork
from app.utils.states import SettingsStates
from app.utils.text import escape
from app.utils.time import is_known_zone

router = Router(name="settings")

SCREEN = (
    "⚙️ <b>Настройки</b>\n\n"
    "Каждый переключатель применяется сразу.\n\n"
    "🟢 — включено, ⚪️ — выключено.\n"
    "<i>Загрузка файлов на диск занимает место, зато файл останется доступен\n"
    "даже после того, как автор его удалит.</i>"
)

TIMEZONE_PROMPT = (
    "🌍 <b>Часовой пояс</b>\n\n"
    "Пришлите название в формате IANA, например:\n"
    "<code>Europe/Moscow</code>, <code>Asia/Almaty</code>, <code>UTC</code>.\n\n"
    "От пояса зависят все даты в архиве, поиске и экспорте."
)

RETENTION_SCREEN = (
    "🗓 <b>Срок хранения</b>\n\n"
    "Сообщения старше выбранного срока будут удаляться автоматически\n"
    "вместе со скачанными файлами. Уборка работает в фоне и необратима.\n\n"
    "Текущий выбор: <b>{current}</b>"
)


@router.message(Command("settings"))
async def cmd_settings(
    message: Message,
    state: FSMContext,
    user_settings: UserSettings,
) -> None:
    await state.clear()
    await message.answer(SCREEN, reply_markup=settings_keyboard(user_settings))


@router.callback_query(MenuCB.filter(F.action == "settings"))
async def cb_settings_entry(
    query: CallbackQuery,
    state: FSMContext,
    user_settings: UserSettings,
) -> None:
    await state.clear()
    await show(query, SCREEN, settings_keyboard(user_settings))
    await query.answer()


@router.callback_query(SettingsCB.filter(F.action == "open"))
async def cb_settings_open(
    query: CallbackQuery,
    state: FSMContext,
    user_settings: UserSettings,
) -> None:
    await state.set_state(None)
    await show(query, SCREEN, settings_keyboard(user_settings))
    await query.answer()


@router.callback_query(SettingsCB.filter(F.action == "toggle"))
async def cb_settings_toggle(
    query: CallbackQuery,
    callback_data: SettingsCB,
    uow: UnitOfWork,
    user_settings: UserSettings,
) -> None:
    """Переключить флаг из белого списка."""
    if callback_data.field not in TOGGLE_FIELDS:
        await query.answer("Неизвестная настройка", show_alert=True)
        return
    value = await uow.settings.toggle(user_settings, callback_data.field)
    await uow.commit()
    await show(query, SCREEN, settings_keyboard(user_settings))
    await query.answer("Включено" if value else "Выключено")


@router.callback_query(SettingsCB.filter(F.action == "retention"))
async def cb_settings_retention(
    query: CallbackQuery,
    user_settings: UserSettings,
) -> None:
    await show(
        query,
        RETENTION_SCREEN.format(current=retention_label(user_settings.retention_days)),
        retention_keyboard(user_settings.retention_days),
    )
    await query.answer()


@router.callback_query(SettingsCB.filter(F.action == "set_retention"))
async def cb_settings_set_retention(
    query: CallbackQuery,
    callback_data: SettingsCB,
    uow: UnitOfWork,
    user_settings: UserSettings,
) -> None:
    if callback_data.value not in RETENTION_CHOICES:
        await query.answer("Такого варианта нет", show_alert=True)
        return
    await uow.settings.update(user_settings, retention_days=int(callback_data.value))
    await uow.commit()
    await show(query, SCREEN, settings_keyboard(user_settings))
    await query.answer(f"Срок хранения: {retention_label(callback_data.value)}")


@router.callback_query(SettingsCB.filter(F.action == "timezone"))
async def cb_settings_timezone(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsStates.waiting_timezone)
    await show(query, TIMEZONE_PROMPT, back_to_settings())
    await query.answer()


@router.message(Command("timezone"))
async def cmd_timezone(message: Message, state: FSMContext) -> None:
    await state.set_state(SettingsStates.waiting_timezone)
    await message.answer(TIMEZONE_PROMPT, reply_markup=back_to_settings())


@router.message(SettingsStates.waiting_timezone, F.text)
async def on_timezone_input(
    message: Message,
    state: FSMContext,
    uow: UnitOfWork,
    user_settings: UserSettings,
) -> None:
    """Принять название пояса и проверить его по базе IANA."""
    raw = (message.text or "").strip()
    if not is_known_zone(raw):
        await message.answer(
            "Не знаю такого пояса. Примеры: <code>Europe/Moscow</code>, "
            "<code>Asia/Almaty</code>, <code>UTC</code>.",
            reply_markup=back_to_settings(),
        )
        return
    await uow.settings.update(user_settings, timezone=raw)
    await uow.commit()
    await state.set_state(None)
    await message.answer(
        f"🌍 Часовой пояс теперь <b>{escape(raw)}</b>.",
        reply_markup=settings_keyboard(user_settings),
    )


@router.message(SettingsStates.waiting_timezone)
async def on_timezone_wrong(message: Message) -> None:
    await message.answer(
        "Нужен текст с названием пояса, например <code>Europe/Moscow</code>.",
        reply_markup=back_to_settings(),
    )
