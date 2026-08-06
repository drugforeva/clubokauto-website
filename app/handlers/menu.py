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
    "\U0001f5c2 \u0421\u043e\u0445\u0440\u0430\u043d\u043e \n\n"
    "\u041f\u0440\u0438\u0432\u0435\u0442, {name}!\n"
    "\u042f \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e \u0432\u0430\u0448\u0443 \u043f\u0435\u0440\u0435\u043f\u0438\u0441\u043a\u0443 \u0438 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u044f\u044e, \u0435\u0441\u043b\u0438 \u0441\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a \u0443\u0434\u0430\u043b\u0438\u043b \u0438\u043b\u0438 \u0438\u0437\u043c\u0435\u043d\u0438\u043b \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435."
)

HELP = (
    "\u2139\ufe0f \u0421\u043f\u0440\u0430\u0432\u043a\u0430 \n\n"
    " \u041a\u043e\u043c\u0430\u043d\u0434\u044b \n"
    "/start \u2014 \u0433\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e\n"
    "/history \u2014 \u0430\u0440\u0445\u0438\u0432 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439\n"
    "/search \u2014 \u043f\u043e\u0438\u0441\u043a \u043f\u043e \u0442\u0435\u043a\u0441\u0442\u0443, \u0430\u0432\u0442\u043e\u0440\u0443 \u0438 \u0434\u0430\u0442\u0430\u043c\n"
    "/stats \u2014 \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430\n"
    "/export \u2014 \u0432\u044b\u0433\u0440\u0443\u0437\u043a\u0430 \u0430\u0440\u0445\u0438\u0432\u0430 \u0444\u0430\u0439\u043b\u043e\u043c\n"
    "/settings \u2014 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u044f, \u0447\u0430\u0441\u043e\u0432\u043e\u0439 \u043f\u043e\u044f\u0441, \u0441\u0440\u043e\u043a \u0445\u0440\u0430\u043d\u0435\u043d\u0438\u044f\n\n"
    " \u0427\u0442\u043e \u044f \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e \n"
    "\u0422\u0435\u043a\u0441\u0442, \u0430\u0432\u0442\u043e\u0440\u0430, \u0432\u0440\u0435\u043c\u044f, \u0442\u0438\u043f \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u0438 \u0441\u0441\u044b\u043b\u043a\u0438 \u043d\u0430 \u0432\u043b\u043e\u0436\u0435\u043d\u0438\u044f.\n"
    "\u041f\u0440\u0438 \u043f\u0440\u0430\u0432\u043a\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e \u0432\u0441\u0435 \u0432\u0435\u0440\u0441\u0438\u0438 \u0442\u0435\u043a\u0441\u0442\u0430, \u043f\u0440\u0438 \u0443\u0434\u0430\u043b\u0435\u043d\u0438\u0438 \u2014 \u043f\u0440\u0438\u0441\u044b\u043b\u0430\u044e \u043a\u043e\u043f\u0438\u044e.\n\n"
    " \u0412\u0430\u0436\u043d\u044b\u0435 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f \n"
    "\u2022 \u0421\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u0434\u043e \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f \u0431\u043e\u0442\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b: Telegram \u043d\u0435 \u043e\u0442\u0434\u0430\u0451\u0442 \u0438\u0441\u0442\u043e\u0440\u0438\u044e\n"
    "\u2022 \u0418\u0441\u0447\u0435\u0437\u0430\u044e\u0449\u0438\u0435 \u0438 \u043e\u0434\u043d\u043e\u0440\u0430\u0437\u043e\u0432\u044b\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u043d\u0435 \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e\u0442\u0441\u044f\n"
    "\u2022 \u0410\u0440\u0445\u0438\u0432 \u0432\u0438\u0434\u0438\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u0432\u043b\u0430\u0434\u0435\u043b\u0435\u0446 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f"
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


# -----------------------------------------------------------------
# Обработчик проверки подписки (после прохождения SubscriptionMiddleware)
# -----------------------------------------------------------------
@router.callback_query(F.data == "check_sub")
async def cb_check_sub(
    query: CallbackQuery,
    state: FSMContext,
    user: User,
    settings: Settings,
) -> None:
    """Пользователь подписался и нажал «Гото» — здесь они уже подписаны,
    потому что SubscriptionMiddleware пропустила запрос. Показываем главное меню.
    Если пользователь ещё не подписан, middleware заблокирует запрос раньше и сюда не доходим.
    """
    await state.clear()
    await query.answer("\u2705 \u041fодписка подтверждена!")
    await show(
        query,
        WELCOME.format(name=escape(user.display_name)),
        main_menu(is_admin=settings.is_admin(user.telegram_id)),
    )


def _is_noop(query: CallbackQuery) -> bool:
    """\u0421\u0447\u0451\u0442\u0447\u0438\u043a \u0441\u0442\u0440\u0430\u043d\u0438\u0446 \u2014 \u043a\u043d\u043e\u043f\u043a\u0430-\u0437\u0430\u0433\u043b\u0443\u0448\u043a\u0430 \u0432 \u043b\u044e\u0431\u043e\u043c \u0440\u0430\u0437\u0434\u0435\u043b\u0435.

    \u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u0441\u0442\u043e\u0438\u0442 \u0432\u0442\u043e\u0440\u044b\u043c \u0441\u0435\u0433\u043c\u0435\u043d\u0442\u043e\u043c callback_data (\u043f\u043e\u0441\u043b\u0435 \u043f\u0440\u0435\u0444\u0438\u043a\u0441\u0430),
    \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u043c \u0435\u0433\u043e \u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e, \u0430 \u043d\u0435 \u043f\u043e \u043a\u043e\u043d\u0446\u0443 \u0441\u0442\u0440\u043e\u043a\u0438.
    """
    parts = (query.data or "").split(":")
    return len(parts) > 1 and parts[1] == "noop"


@router.callback_query(_is_noop)
async def cb_noop(query: CallbackQuery) -> None:
    await query.answer()
