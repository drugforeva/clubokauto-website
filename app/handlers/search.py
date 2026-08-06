"""Поиск по архиву.

Фильтры собираются в FSM по шагам: текст запроса не влезает в 64 байта
callback_data, да и уточнять условия по одному удобнее.
"""

from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config.settings import Settings
from app.handlers.common import show
from app.keyboards.callbacks import MenuCB, SearchCB
from app.keyboards.search import (
    cancel_input,
    result_card_keyboard,
    results_keyboard,
    search_menu,
)
from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.messages import MessageFilters
from app.repositories.uow import UnitOfWork
from app.utils.formatting import message_card, message_row
from app.utils.pagination import Page, normalize_page, offset_for
from app.utils.states import SearchStates
from app.utils.text import escape, shorten
from app.utils.time import day_end, fmt_datetime, parse_user_date

router = Router(name="search")

DATE_HINT = "Формат даты: <code>05.08.2026</code> или <code>2026-08-05</code>"

PROMPTS: dict[str, str] = {
    "query": "🔤 Пришлите слово или фразу для поиска по тексту сообщений.",
    "sender": "👤 Пришлите имя или @username автора.",
    "date_from": f"📅 С какой даты искать?\n{DATE_HINT}",
    "date_to": f"📅 По какую дату искать?\n{DATE_HINT}",
}

STATES = {
    "query": SearchStates.waiting_query,
    "sender": SearchStates.waiting_sender,
    "date_from": SearchStates.waiting_date_from,
    "date_to": SearchStates.waiting_date_to,
}


def _build_filters(owner_id: int, data: dict[str, Any], timezone: str) -> MessageFilters:
    """Собрать условия из состояния диалога.

    Даты хранятся строкой в том виде, в каком их ввёл владелец, а разбор
    делается здесь с учётом его часового пояса.
    """
    date_from = parse_user_date(data.get("date_from") or "", timezone)
    date_to = parse_user_date(data.get("date_to") or "", timezone)
    return MessageFilters(
        owner_id=owner_id,
        query=data.get("query") or None,
        sender=data.get("sender") or None,
        only_deleted=bool(data.get("only_deleted")),
        include_outgoing=bool(data.get("include_outgoing", True)),
        date_from=date_from,
        date_to=day_end(date_to) if date_to else None,
    )


def _menu_text(filters: MessageFilters) -> str:
    return (
        "🔍 <b>Поиск по архиву</b>\n\n"
        f"Условия: <i>{escape(filters.describe())}</i>\n\n"
        "Задайте любые условия и нажмите «Найти»."
    )


async def _state_data(state: FSMContext) -> dict[str, Any]:
    """Состояние с уже выставленным по умолчанию флагом «со своими»."""
    data = await state.get_data()
    if "include_outgoing" not in data:
        data = await state.update_data(include_outgoing=True)
    return data


async def _load_page(
    uow: UnitOfWork, filters: MessageFilters, page_number: int, per_page: int
) -> Page:
    total = await uow.messages.count(filters)
    number = normalize_page(page_number, total, per_page)
    items = await uow.messages.search(
        filters, offset=offset_for(number, per_page), limit=per_page
    )
    return Page(items=items, total=total, number=number, per_page=per_page)


def _render_results(page: Page, filters: MessageFilters, timezone: str) -> str:
    if page.is_empty:
        return (
            "🔍 <b>Ничего не нашлось</b>\n\n"
            f"Условия: <i>{escape(filters.describe())}</i>\n\n"
            "Попробуйте ослабить фильтры или другое слово."
        )
    lines = [
        "🔍 <b>Результаты поиска</b>",
        f"Найдено: <b>{page.total}</b> · страница {page.label}",
        f"Условия: <i>{escape(filters.describe())}</i>",
        "",
    ]
    for offset, record in enumerate(page.items):
        lines.append(
            f"{page.first_index + offset}. <code>"
            f"{escape(fmt_datetime(record.sent_at, timezone))}</code>\n"
            f"    {escape(message_row(record))}"
        )
    return "\n".join(lines)


async def _menu_screen(
    state: FSMContext, user: User, user_settings: UserSettings
) -> tuple[str, Any]:
    """Текст и клавиатура экрана поиска."""
    await state.set_state(None)
    data = await _state_data(state)
    filters = _build_filters(user.id, data, user_settings.timezone)
    return _menu_text(filters), search_menu(data)


@router.message(Command("search"))
async def cmd_search(
    message: Message,
    state: FSMContext,
    user: User,
    user_settings: UserSettings,
) -> None:
    text, keyboard = await _menu_screen(state, user, user_settings)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(MenuCB.filter(F.action == "search"))
async def cb_search_entry(
    query: CallbackQuery,
    state: FSMContext,
    user: User,
    user_settings: UserSettings,
) -> None:
    text, keyboard = await _menu_screen(state, user, user_settings)
    await show(query, text, keyboard)
    await query.answer()


@router.callback_query(SearchCB.filter(F.action == "open"))
async def cb_search_open(
    query: CallbackQuery,
    state: FSMContext,
    user: User,
    user_settings: UserSettings,
) -> None:
    text, keyboard = await _menu_screen(state, user, user_settings)
    await show(query, text, keyboard)
    await query.answer()


@router.callback_query(SearchCB.filter(F.action == "reset"))
async def cb_search_reset(
    query: CallbackQuery,
    state: FSMContext,
    user: User,
    user_settings: UserSettings,
) -> None:
    await state.clear()
    text, keyboard = await _menu_screen(state, user, user_settings)
    await show(query, text, keyboard)
    await query.answer("Фильтры сброшены")


@router.callback_query(
    SearchCB.filter(F.action.in_({"only_deleted", "include_outgoing"}))
)
async def cb_search_toggle(
    query: CallbackQuery,
    callback_data: SearchCB,
    state: FSMContext,
    user: User,
    user_settings: UserSettings,
) -> None:
    data = await _state_data(state)
    field = callback_data.action
    default = field == "include_outgoing"
    await state.update_data(**{field: not bool(data.get(field, default))})
    text, keyboard = await _menu_screen(state, user, user_settings)
    await show(query, text, keyboard)
    await query.answer()


@router.callback_query(SearchCB.filter(F.action.in_(set(STATES))))
async def cb_search_ask(
    query: CallbackQuery,
    callback_data: SearchCB,
    state: FSMContext,
) -> None:
    """Спросить значение одного из текстовых фильтров."""
    await state.set_state(STATES[callback_data.action])
    await show(query, PROMPTS[callback_data.action], cancel_input())
    await query.answer()


@router.message(SearchStates.waiting_query, F.text)
async def on_query_input(
    message: Message,
    state: FSMContext,
    user: User,
    user_settings: UserSettings,
) -> None:
    await state.update_data(query=shorten(message.text, 200))
    text, keyboard = await _menu_screen(state, user, user_settings)
    await message.answer(text, reply_markup=keyboard)


@router.message(SearchStates.waiting_sender, F.text)
async def on_sender_input(
    message: Message,
    state: FSMContext,
    user: User,
    user_settings: UserSettings,
) -> None:
    await state.update_data(sender=shorten((message.text or "").lstrip("@"), 64))
    text, keyboard = await _menu_screen(state, user, user_settings)
    await message.answer(text, reply_markup=keyboard)


@router.message(SearchStates.waiting_date_from, F.text)
@router.message(SearchStates.waiting_date_to, F.text)
async def on_date_input(
    message: Message,
    state: FSMContext,
    user: User,
    user_settings: UserSettings,
) -> None:
    """Разобрать дату и вернуться в меню поиска."""
    current = await state.get_state()
    field = (
        "date_from" if current == SearchStates.waiting_date_from.state else "date_to"
    )
    parsed = parse_user_date(message.text or "", user_settings.timezone)
    if parsed is None:
        await message.answer(
            f"Не понял дату. {DATE_HINT}", reply_markup=cancel_input()
        )
        return
    await state.update_data(**{field: (message.text or "").strip()})
    text, keyboard = await _menu_screen(state, user, user_settings)
    await message.answer(text, reply_markup=keyboard)


@router.message(SearchStates.waiting_query)
@router.message(SearchStates.waiting_sender)
@router.message(SearchStates.waiting_date_from)
@router.message(SearchStates.waiting_date_to)
async def on_wrong_input(message: Message) -> None:
    """В режиме ввода ждём именно текст, а не фото или стикер."""
    await message.answer(
        "Нужен текст. Пришлите значение сообщением или вернитесь к поиску.",
        reply_markup=cancel_input(),
    )


@router.callback_query(SearchCB.filter(F.action == "run"))
async def cb_search_run(
    query: CallbackQuery,
    callback_data: SearchCB,
    state: FSMContext,
    uow: UnitOfWork,
    user: User,
    user_settings: UserSettings,
    settings: Settings,
) -> None:
    await state.set_state(None)
    data = await _state_data(state)
    filters = _build_filters(user.id, data, user_settings.timezone)
    page = await _load_page(
        uow, filters, callback_data.page, settings.history_page_size
    )
    await show(
        query,
        _render_results(page, filters, user_settings.timezone),
        results_keyboard(page) if not page.is_empty else search_menu(data),
    )
    await query.answer()


@router.callback_query(SearchCB.filter(F.action == "show"))
async def cb_search_show(
    query: CallbackQuery,
    callback_data: SearchCB,
    uow: UnitOfWork,
    user: User,
    user_settings: UserSettings,
) -> None:
    record = await uow.messages.get(user.id, callback_data.message_id)
    if record is None:
        await query.answer("Сообщение больше недоступно", show_alert=True)
        return
    media = list(record.media or [])
    versions = await uow.edits.count_for_message(record.id)
    text = message_card(record, media, versions)
    text += (
        "\n\nОтправлено: "
        f"{escape(fmt_datetime(record.sent_at, user_settings.timezone))}"
    )
    await show(query, text, result_card_keyboard(callback_data.page))
    await query.answer()
