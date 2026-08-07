"""Меню, приветствие и гайд по подключению.

Гайд с картинкой доступен тремя путями: автоматически после подтверждения
подписки, кнопкой «Подключение» в меню и командой /connect.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.config.settings import Settings
from app.keyboards.callbacks import MenuCB
from app.keyboards.menu import guide_keyboard, main_menu
from app.middlewares.subscription import CHECK_CALLBACK

logger = structlog.get_logger(__name__)

router = Router(name="menu")

WELCOME = (
    "\U0001f44b <b>Сохрано</b> — архив вашей переписки в Telegram.\n\n"
    "Я сохраняю сообщения из чатов, подключённых через Telegram Business, "
    "и присылаю уведомление, если собеседник удалил или отредактировал "
    "сообщение."
)

SUBSCRIBED = (
    "\u2705 <b>Подписка подтверждена</b>\n\nТеперь можно подключать бота."
)

# Важно: этот текст идёт подписью к фото, а у подписи лимит 1024 символа.
CONNECT_GUIDE = (
    "\U0001f50c <b>Как подключить бота</b>\n\n"
    "Нужен Telegram Premium — без него раздела для бизнеса в настройках нет.\n\n"
    "1\ufe0f\u20e3 Настройки \u2192 <b>Telegram для бизнеса</b>\n"
    "2\ufe0f\u20e3 Раздел <b>Чат-боты</b>\n"
    "3\ufe0f\u20e3 Впишите <code>@Sohrano_bot</code>\n"
    "4\ufe0f\u20e3 Включите <b>«Отвечать на сообщения»</b>\n\n"
    "Готово. Дальше я молча веду архив и предупреждаю об удалениях и правках."
)

HELP = (
    "\u2753 <b>Как это работает</b>\n\n"
    "После подключения через Telegram Business я сохраняю сообщения "
    "ваших чатов и слежу за ними.\n\n"
    "• Собеседник удалил сообщение — пришлю его текст и вложения.\n"
    "• Отредактировал — покажу «было \u2192 стало».\n"
    "• Одноразовое фото — ответьте на него любым сообщением, и я его заберу.\n\n"
    "<b>Команды</b>\n"
    "/connect — инструкция по подключению\n"
    "/history — архив сообщений\n"
    "/stats — статистика\n"
    "/export — выгрузить архив файлом"
)


async def send_connect_guide(message: Message, settings: Settings) -> None:
    """Отправить гайд картинкой, а если не вышло — текстом."""
    path = Path(settings.guide_image)
    if path.is_file():
        try:
            await message.answer_photo(
                FSInputFile(path),
                caption=CONNECT_GUIDE,
                reply_markup=guide_keyboard(),
            )
            return
        except TelegramAPIError as error:
            logger.warning("guide.photo_failed", error=str(error))
    else:
        logger.info("guide.image_missing", path=str(path))
    await message.answer(CONNECT_GUIDE, reply_markup=guide_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message, settings: Settings) -> None:
    """Приветствие, меню и сразу же инструкция."""
    is_admin = settings.is_admin(message.from_user.id) if message.from_user else False
    await message.answer(WELCOME, reply_markup=main_menu(is_admin=is_admin))
    await send_connect_guide(message, settings)


@router.message(Command("connect"))
async def cmd_connect(message: Message, settings: Settings) -> None:
    await send_connect_guide(message, settings)


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    is_admin = settings.is_admin(message.from_user.id) if message.from_user else False
    await message.answer(HELP, reply_markup=main_menu(is_admin=is_admin))


@router.callback_query(F.data == CHECK_CALLBACK)
async def cb_check_sub(query: CallbackQuery, settings: Settings) -> None:
    """Сюда попадаем, только если подписка уже подтверждена."""
    await query.answer("Подписка подтверждена \u2705")
    message = query.message
    if message is None:
        return
    try:
        await message.edit_text(SUBSCRIBED)
    except TelegramAPIError:
        # Сообщение могли уже отредактировать — это не повод падать.
        pass
    await send_connect_guide(message, settings)
    is_admin = settings.is_admin(query.from_user.id) if query.from_user else False
    await message.answer(WELCOME, reply_markup=main_menu(is_admin=is_admin))


@router.callback_query(MenuCB.filter(F.action == "connect"))
async def cb_connect(query: CallbackQuery, settings: Settings) -> None:
    await query.answer()
    if query.message is not None:
        await send_connect_guide(query.message, settings)


@router.callback_query(MenuCB.filter(F.action == "home"))
async def cb_home(query: CallbackQuery, settings: Settings) -> None:
    await query.answer()
    if query.message is None:
        return
    is_admin = settings.is_admin(query.from_user.id) if query.from_user else False
    try:
        await query.message.edit_text(WELCOME, reply_markup=main_menu(is_admin=is_admin))
    except TelegramAPIError:
        # У сообщения с фото нет текста — править нечего, шлём новое.
        await query.message.answer(WELCOME, reply_markup=main_menu(is_admin=is_admin))


@router.callback_query(MenuCB.filter(F.action == "help"))
async def cb_help(query: CallbackQuery, settings: Settings) -> None:
    await query.answer()
    if query.message is None:
        return
    is_admin = settings.is_admin(query.from_user.id) if query.from_user else False
    try:
        await query.message.edit_text(HELP, reply_markup=main_menu(is_admin=is_admin))
    except TelegramAPIError:
        await query.message.answer(HELP, reply_markup=main_menu(is_admin=is_admin))
