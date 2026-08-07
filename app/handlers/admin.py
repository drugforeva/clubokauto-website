"""Админ-панель.

Весь роутер закрыт фильтром IsAdmin — и на команды, и на кнопки.
Только здесь используются методы репозиториев, которые видят данные всех владельцев.
"""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.config.settings import Settings
from app.filters.admin import IsAdmin
from app.handlers.common import show
from app.keyboards.admin import (
    admin_menu,
    admin_message_keyboard,
    back_to_admin,
    user_card_keyboard,
    user_messages_keyboard,
    users_keyboard,
)
from app.keyboards.callbacks import AdminCB, MenuCB
from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.messages import MessageFilters
from app.repositories.uow import UnitOfWork
from app.services.broadcast import BroadcastService
from app.services.metrics import Metrics
from app.services.stats import StatsService
from app.utils.formatting import message_card, stats_block, versions_block
from app.utils.pagination import Page, normalize_page, offset_for
from app.utils.states import AdminStates
from app.utils.text import escape, human_size, plural
from app.utils.time import fmt_datetime

logger = structlog.get_logger(__name__)

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

NOT_FOUND = "Запись не найдена"

BROADCAST_PROMPT = (
    "📣 <b>Рассылка</b>\n\n"
    "Пришлите текст сообщения. Он уйдёт всем, кто не заблокировал бота.\n"
    "Разрешён HTML: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;code&gt;</code>.\n\n"
    "<i>Отменить отправку после старта нельзя.</i>"
)


async def _admin_screen(
    uow: UnitOfWork, stats: StatsService, metrics: Metrics
) -> str:
    return await stats.global_summary(uow, metrics=metrics)


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    state: FSMContext,
    uow: UnitOfWork,
    stats: StatsService,
    metrics: Metrics,
) -> None:
    await state.clear()
    await message.answer(
        await _admin_screen(uow, stats, metrics), reply_markup=admin_menu()
    )


@router.callback_query(MenuCB.filter(F.action == "admin"))
@router.callback_query(AdminCB.filter(F.action == "home"))
async def cb_admin_home(
    query: CallbackQuery,
    state: FSMContext,
    uow: UnitOfWork,
    stats: StatsService,
    metrics: Metrics,
) -> None:
    await state.clear()
    await show(query, await _admin_screen(uow, stats, metrics), admin_menu())
    await query.answer()


@router.callback_query(AdminCB.filter(F.action == "users"))
async def cb_admin_users(
    query: CallbackQuery,
    callback_data: AdminCB,
    uow: UnitOfWork,
    settings: Settings,
) -> None:
    """Список пользователей бота по страницам."""
    per_page = settings.admin_page_size
    total = await uow.users.count()
    number = normalize_page(callback_data.page, total, per_page)
    items = await uow.users.page(offset_for(number, per_page), per_page)
    page = Page(items=items, total=total, number=number, per_page=per_page)

    word = plural(total, "пользователь", "пользователя", "пользователей")
    text = (
        f"👥 <b>Пользователи</b>\n\n{total} {word} · страница {page.label}\n\n"
        "🚫 — бот заблокирован пользователем."
    )
    await show(query, text, users_keyboard(page))
    await query.answer()


@router.callback_query(AdminCB.filter(F.action == "user"))
async def cb_admin_user(
    query: CallbackQuery,
    callback_data: AdminCB,
    uow: UnitOfWork,
    user_settings: UserSettings,
) -> None:
    """Карточка пользователя с его цифрами."""
    target = await uow.users.get(callback_data.user_id)
    if target is None:
        await query.answer(NOT_FOUND, show_alert=True)
        return

    counters = await uow.messages.counters(target.id)
    chats = await uow.chats.count_for_owner(target.id)
    media = await uow.media.count_for_owner(target.id)
    stored = await uow.media.stored_bytes(target.id)
    connections = await uow.connections.for_user(target.id)
    target_settings = await uow.settings.get(target.id)

    rows: list[tuple[str, object]] = [
        ("Имя", target.display_name),
        ("Telegram ID", target.telegram_id),
        ("Логин", f"@{target.username}" if target.username else "—"),
        ("Подключений", len(connections)),
        ("Сообщений", counters["total"]),
        ("Удалено", counters["deleted"]),
        ("С правками", counters["edited"]),
        ("Диалогов", chats),
        ("Вложений", media),
    ]
    if stored:
        rows.append(("На диске", human_size(stored)))
    if target_settings is not None:
        rows.append(("Часовой пояс", target_settings.timezone))
    rows.append(
        ("Зарегистрирован", fmt_datetime(target.created_at, user_settings.timezone))
    )
    rows.append(
        ("Видели последний раз", fmt_datetime(target.last_seen_at, user_settings.timezone))
    )
    if target.is_blocked:
        rows.append(("Статус", "бот заблокирован"))

    await show(
        query,
        stats_block("👤 Карточка пользователя", rows),
        user_card_keyboard(target.id, callback_data.page),
    )
    await query.answer()


@router.callback_query(AdminCB.filter(F.action == "messages"))
async def cb_admin_messages(
    query: CallbackQuery,
    callback_data: AdminCB,
    uow: UnitOfWork,
    user_settings: UserSettings,
    settings: Settings,
) -> None:
    """Сообщения конкретного владельца."""
    target = await uow.users.get(callback_data.user_id)
    if target is None:
        await query.answer(NOT_FOUND, show_alert=True)
        return

    per_page = settings.admin_page_size
    filters = MessageFilters(owner_id=target.id)
    total = await uow.messages.count(filters)
    number = normalize_page(callback_data.page, total, per_page)
    items = await uow.messages.search(
        filters, offset=offset_for(number, per_page), limit=per_page
    )
    page = Page(items=items, total=total, number=number, per_page=per_page)

    if page.is_empty:
        await show(
            query,
            f"💬 <b>{escape(target.display_name)}</b>\n\nАрхив пуст.",
            user_card_keyboard(target.id, 1),
        )
        await query.answer()
        return

    lines = [
        f"💬 <b>Сообщения: {escape(target.display_name)}</b>",
        f"Всего: <b>{total}</b> · страница {page.label}",
        "",
    ]
    for offset, record in enumerate(page.items):
        lines.append(
            f"{page.first_index + offset}. <code>"
            f"{escape(fmt_datetime(record.sent_at, user_settings.timezone))}</code>"
        )
    await show(query, "\n".join(lines), user_messages_keyboard(page, target.id))
    await query.answer()


@router.callback_query(AdminCB.filter(F.action == "message"))
async def cb_admin_message(
    query: CallbackQuery,
    callback_data: AdminCB,
    uow: UnitOfWork,
    user_settings: UserSettings,
) -> None:
    """Карточка сообщения глазами админа."""
    record = await uow.messages.get_any_owner(callback_data.message_id)
    if record is None:
        await query.answer(NOT_FOUND, show_alert=True)
        return
    owner = await uow.users.get(record.owner_id)
    media = await uow.media.for_message(record.id)
    versions = await uow.edits.count_for_message(record.id)

    text = message_card(
        record,
        media,
        versions,
        owner_hint=owner.display_name if owner is not None else None,
    )
    text += (
        "\n\nОтправлено: "
        f"{escape(fmt_datetime(record.sent_at, user_settings.timezone))}"
    )
    await show(
        query,
        text,
        admin_message_keyboard(
            record.id,
            callback_data.user_id,
            page=callback_data.page,
            has_media=bool(media),
            has_versions=versions > 1,
        ),
    )
    await query.answer()


@router.callback_query(AdminCB.filter(F.action == "media"))
async def cb_admin_media(
    query: CallbackQuery,
    callback_data: AdminCB,
    uow: UnitOfWork,
) -> None:
    items = await uow.media.for_message(callback_data.message_id)
    if not items:
        await query.answer("Вложений нет", show_alert=True)
        return
    lines = ["📎 <b>Вложения</b>", ""]
    for item in items:
        size = f" · {human_size(item.file_size)}" if item.file_size else ""
        saved = " · на диске" if item.local_path else ""
        lines.append(f"• {escape(item.file_name or item.media_type)}{size}{saved}")
    await show(
        query,
        "\n".join(lines),
        admin_message_keyboard(
            callback_data.message_id,
            callback_data.user_id,
            page=callback_data.page,
        ),
    )
    await query.answer()


@router.callback_query(AdminCB.filter(F.action == "versions"))
async def cb_admin_versions(
    query: CallbackQuery,
    callback_data: AdminCB,
    uow: UnitOfWork,
) -> None:
    versions = await uow.edits.for_message(callback_data.message_id)
    await show(
        query,
        versions_block(versions),
        admin_message_keyboard(
            callback_data.message_id,
            callback_data.user_id,
            page=callback_data.page,
        ),
    )
    await query.answer()


@router.callback_query(AdminCB.filter(F.action == "deleted"))
async def cb_admin_deleted(
    query: CallbackQuery,
    uow: UnitOfWork,
    user_settings: UserSettings,
) -> None:
    """Последние события удаления по всем владельцам."""
    events = await uow.deleted.recent_any_owner(limit=15)
    if not events:
        await show(
            query,
            "🗑 <b>Удаления</b>\n\nСобытий пока нет.",
            back_to_admin(),
        )
        await query.answer()
        return

    lines = ["🗑 <b>Последние удаления</b>", ""]
    for event in events:
        when = fmt_datetime(event.detected_at, user_settings.timezone)
        known = "в архиве" if event.message_id else "вне архива"
        lines.append(
            f"• <code>{escape(when)}</code> · msg {event.telegram_message_id} · {known}"
        )
    await show(query, "\n".join(lines), back_to_admin())
    await query.answer()


@router.callback_query(AdminCB.filter(F.action == "broadcast"))
async def cb_admin_broadcast(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_broadcast)
    await show(query, BROADCAST_PROMPT, back_to_admin())
    await query.answer()


@router.message(AdminStates.waiting_broadcast, F.text)
async def on_broadcast_text(
    message: Message,
    state: FSMContext,
    uow: UnitOfWork,
    user: User,
    broadcast: BroadcastService,
) -> None:
    """Отправить рассылку и показать итог."""
    await state.clear()
    await message.answer("📣 Начинаю рассылку…")
    report = await broadcast.run(uow, text=message.text or "")
    logger.info(
        "admin.broadcast",
        admin_id=user.telegram_id,
        sent=report.sent,
        failed=report.failed,
        blocked=report.blocked,
    )
    await message.answer(
        stats_block(
            "📣 Рассылка завершена",
            [
                ("Доставлено", report.sent),
                ("Заблокировали бота", report.blocked),
                ("Ошибок", report.failed),
                ("Всего получателей", report.total),
            ],
        ),
        reply_markup=back_to_admin(),
    )


@router.message(AdminStates.waiting_broadcast)
async def on_broadcast_wrong(message: Message) -> None:
    await message.answer(
        "Для рассылки нужен текст. Пришлите сообщение текстом.",
        reply_markup=back_to_admin(),
    )
