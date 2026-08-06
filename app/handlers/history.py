
"""Архив сообщений: выбор собеседника, список, карточка."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config.settings import Settings
from app.handlers.common import scope_filters, show
from app.keyboards.callbacks import HistoryCB, MenuCB
from app.keyboards.history import (
    chats_keyboard,
    history_keyboard,
    message_keyboard,
)
from app.keyboards.menu import back_to_menu
from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.messages import MessageFilters
from app.repositories.uow import UnitOfWork
from app.utils.formatting import message_card, message_row, versions_block
from app.utils.pagination import Page, normalize_page, offset_for
from app.utils.text import escape, human_size
from app.utils.time import fmt_datetime

router = Router(name="history")

NO_CHATS = (
    "💬 <b>Собеседников нет</b>\n\n"
    "Как только кто-то напишет — его здесь появится."
)

EMPTY = (
    "🗑 <b>Удалённыхov сообщений нет</b>\n\n"
    "Как только кто-то удалит сообщение — оно появится здесь."
)

NOT_FOUND = "Сообщение не найдено — возможно, его убрала автоочистка"


async def _load_page(
    uow: UnitOfWork,
    owner_id: int,
    scope: str,
    page_number: int,
    per_page: int,
    chat_id: int = 0,
) -> Page:
    filters = MessageFilters(
        owner_id=owner_id,
        only_deleted=(scope == "deleted"),
        only_edited=(scope == "edited"),
        chat_id=chat_id if chat_id else None,
    )
    total = await uow.messages.count(filters)
    number = normalize_page(page_number, total, per_page)
    items = await uow.messages.search(
        filters, offset=offset_for(number, per_page), limit=per_page
    )
    return Page(items=items, total=total, number=number, per_page=per_page)


def _render_chats(chats: list) -> str:
    if not chats:
        return NO_CHATS
    lines = ["👥 <b>Выберите собеседника</b>", ""]
    for chat in chats:
        username = getattr(chat, "username", None)
        first = getattr(chat, "first_name", None) or ""
        last = getattr(chat, "last_name", None) or ""
        name = f"{first} {last}".strip() or getattr(chat, "title", None) or "?"
        line = f"• {escape(name)}"
        if username:
            line += f" (@{escape(username)})"
        lines.append(line)
    return "\n".join(lines)


def _render_list(page: Page, scope: str, timezone: str, chat_name: str = "") -> str:
    scope_label = {"deleted": "🗑 Удалённые", "edited": "✏️ Изменённые", "all": "📋 Все"}[scope]
    header = f"{scope_label} · {escape(chat_name)}" if chat_name else scope_label
    if page.is_empty:
        return EMPTY
    lines = [
        f"🗂 <b>Архив</b> — {header}",
        f"Всего: <b>{page.total}</b> · страница {page.label}",
        "",
    ]
    for offset, record in enumerate(page.items):
        lines.append(
            f"{page.first_index + offset}. <code>"
            f"{escape(fmt_datetime(record.sent_at, timezone))}</code>\n"
            f"    {escape(message_row(record))}"
        )
    return "\n".join(lines)


def _render_card(record: object, media: list, versions: int, timezone: str) -> str:
    parts = [message_card(record, media, versions), ""]
    parts.append(f"Отправлено: {escape(fmt_datetime(getattr(record, 'sent_at', None), timezone))}")
    edited_at = getattr(record, "edited_at", None)
    if edited_at:
        parts.append(f"Изменено: {escape(fmt_datetime(edited_at, timezone))}")
    deleted_at = getattr(record, "deleted_at", None)
    if deleted_at:
        parts.append(f"Удалено: {escape(fmt_datetime(deleted_at, timezone))}")
    return "\n".join(parts)


async def _chat_name(uow: UnitOfWork, owner_id: int, chat_id: int) -> str:
    if not chat_id:
        return ""
    chat = await uow.chats.get(chat_id)
    if chat is None or chat.owner_id != owner_id:
        return ""
    username = getattr(chat, "username", None)
    first = getattr(chat, "first_name", None) or ""
    last = getattr(chat, "last_name", None) or ""
    return f"{first} {last}".strip() or getattr(chat, "title", None) or (
        f"@{username}" if username else ""
    )


@router.message(Command("history"))
async def cmd_history(
    message: Message,
    state: FSMContext,
    uow: UnitOfWork,
    user: User,
) -> None:
    await state.clear()
    chats = await uow.chats.for_owner(user.id)
    await message.answer(
        _render_chats(chats),
        reply_markup=chats_keyboard(chats) if chats else back_to_menu(),
    )


@router.callback_query(MenuCB.filter(F.action == "history"))
async def cb_history_entry(
    query: CallbackQuery,
    state: FSMContext,
    uow: UnitOfWork,
    user: User,
) -> None:
    await state.clear()
    chats = await uow.chats.for_owner(user.id)
    await show(
        query,
        _render_chats(chats),
        chats_keyboard(chats) if chats else back_to_menu(),
    )
    await query.answer()


@router.callback_query(HistoryCB.filter(F.action == "chats"))
async def cb_history_chats(
    query: CallbackQuery,
    uow: UnitOfWork,
    user: User,
) -> None:
    chats = await uow.chats.for_owner(user.id)
    await show(
        query,
        _render_chats(chats),
        chats_keyboard(chats) if chats else back_to_menu(),
    )
    await query.answer()


@router.callback_query(HistoryCB.filter(F.action == "list"))
async def cb_history_list(
    query: CallbackQuery,
    callback_data: HistoryCB,
    uow: UnitOfWork,
    user: User,
    user_settings: UserSettings,
    settings: Settings,
) -> None:
    cid = callback_data.chat_id or 0
    page = await _load_page(
        uow, user.id, callback_data.scope,
        callback_data.page, settings.history_page_size, cid,
    )
    name = await _chat_name(uow, user.id, cid)
    kb = history_keyboard(page, callback_data.scope, cid) if not page.is_empty else back_to_menu()
    await show(query, _render_list(page, callback_data.scope, user_settings.timezone, name), kb)
    await query.answer()


@router.callback_query(HistoryCB.filter(F.action == "open"))
async def cb_history_open(
    query: CallbackQuery,
    callback_data: HistoryCB,
    uow: UnitOfWork,
    user: User,
    user_settings: UserSettings,
) -> None:
    record = await uow.messages.get(user.id, callback_data.message_id)
    if record is None:
        await query.answer(NOT_FOUND, show_alert=True)
        return
    media = list(record.media or [])
    versions = await uow.edits.count_for_message(record.id)
    await show(
        query,
        _render_card(record, media, versions, user_settings.timezone),
        message_keyboard(
            record.id,
            has_media=bool(media),
            has_versions=versions > 1,
            scope=callback_data.scope,
            page=callback_data.page,
            chat_id=callback_data.chat_id,
        ),
    )
    await query.answer()


@router.callback_query(HistoryCB.filter(F.action == "media"))
async def cb_history_media(
    query: CallbackQuery,
    callback_data: HistoryCB,
    uow: UnitOfWork,
    user: User,
) -> None:
    record = await uow.messages.get(user.id, callback_data.message_id)
    if record is None:
        await query.answer(NOT_FOUND, show_alert=True)
        return
    items = await uow.media.for_message(record.id)
    if not items:
        await query.answer("Вложений у этого сообщения нет", show_alert=True)
        return
    lines = ["📎 <b>Вложения</b>", ""]
    for item in items:
        title = escape(item.file_name or item.media_type)
        saved = " · скачано" if item.local_path else ""
        lines.append(f"• {title}{saved}")
        lines.append(f"  <code>{escape(item.file_id)}</code>")
    await show(
        query,
        "\n".join(lines),
        message_keyboard(
            record.id,
            has_media=False,
            has_versions=bool(await uow.edits.count_for_message(record.id) > 1),
            scope=callback_data.scope,
            page=callback_data.page,
            chat_id=callback_data.chat_id,
        ),
    )
    await query.answer()


@router.callback_query(HistoryCB.filter(F.action == "versions"))
async def cb_history_versions(
    query: CallbackQuery,
    callback_data: HistoryCB,
    uow: UnitOfWork,
    user: User,
) -> None:
    record = await uow.messages.get(user.id, callback_data.message_id)
    if record is None:
        await query.answer(NOT_FOUND, show_alert=True)
        return
    versions = await uow.edits.for_message(record.id)
    await show(
        query,
        versions_block(versions),
        message_keyboard(
            record.id,
            has_media=bool(record.media),
            has_versions=False,
            scope=callback_data.scope,
            page=callback_data.page,
            chat_id=callback_data.chat_id,
        ),
    )
    await query.answer()
