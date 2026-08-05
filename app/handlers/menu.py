"""Главное меню, /start и /help."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config.settings import Settings
from app.handlers.common import show
from app.keyboards.callbacks import MenuCB
from app.keyboards.menu import back_to_menu, main_menu
from app.models.user import User
from app.utils.text import escape

router = Router(name="menu")

WELCOME = (
    "🗂 <b>Сохрано</b>\n\n"
    "Привет, {name}!\n"
    "Я сохраняю вашу переписку и уведомляю, если собеседник удалил или изменил сообщение."
)

HELP = (
    "ℹ️ <b>Справка</b>\n\n"
    "<b>Команды</b>\n"
    "/start — главное меню\n"
    "/history — архив сообщений\n"
    "/search — поиск по тексту, автору и датам\n"
    "/stats — статистика\n"
    "/export — выгрузка архива файлом\n"
    "/settings — уведомления, часовой пояс, срок хранения\n\n"
    "<b>Что я сохраняю</b>\n"
    "Текст, автора, время, тип сообщения и ссылки на вложения.\n"
    "При правке сохраняю все версии текста, при удалении — присылаю копию.\n\n"
    "<b>Важные ограничения</b>\n"
    "• Сообщения до подключения бота недоступны: Telegram не отдаёт историю\n"
    "• Исчезающие и одноразовые сообщения не сохраняются\n"
    "• Архив видит только владелец подключения"
)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    user: User,
    settings: Settings,
) -> None:
    await state.clear()
    await message.answer(
        WELCOME.format(name=escape(user.display_name)),
        reply_markup=main_menu(is_admin=settings.is_admin(user.telegram_id)),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HELP, reply_markup=back_to_menu())


@router.callback_query(MenuCB.filter(F.action == "home"))
async def cb_home(
    query: CallbackQuery,
    state: FSMContext,
    user: User,
    settings: Settings,
) -> None:
    await state.clear()
    await show(
        query,
        WELCOME.format(name=escape(user.display_name)),
        main_menu(is_admin=settings.is_admin(user.telegram_id)),
    )
    await query.answer()


@router.callback_query(MenuCB.filter(F.action == "help"))
async def cb_help(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(query, HELP, back_to_menu())
    await query.answer()


def _is_noop(query: CallbackQuery) -> bool:
    """Счётчик страниц — кнопка-заглушка в любом разделе.

    Действие стоит вторым сегментом callback_data (после префикса),
    поэтому проверяем его напрямую, а не по концу строки.
    """
    parts = (query.data or "").split(":")
    return len(parts) > 1 and parts[1] == "noop"


@router.callback_query(_is_noop)
async def cb_noop(query: CallbackQuery) -> None:
    await query.answer()
