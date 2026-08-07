"""Статистика архива."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.handlers.common import show
from app.keyboards.callbacks import MenuCB
from app.keyboards.menu import back_to_menu
from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.uow import UnitOfWork
from app.services.stats import StatsService

router = Router(name="stats")


@router.message(Command("stats"))
async def cmd_stats(
    message: Message,
    state: FSMContext,
    uow: UnitOfWork,
    user: User,
    user_settings: UserSettings,
    stats: StatsService,
) -> None:
    await state.clear()
    text = await stats.personal(uow, owner=user, settings=user_settings)
    await message.answer(text, reply_markup=back_to_menu())


@router.callback_query(MenuCB.filter(F.action == "stats"))
async def cb_stats(
    query: CallbackQuery,
    state: FSMContext,
    uow: UnitOfWork,
    user: User,
    user_settings: UserSettings,
    stats: StatsService,
) -> None:
    await state.clear()
    text = await stats.personal(uow, owner=user, settings=user_settings)
    await show(query, text, back_to_menu())
    await query.answer()
