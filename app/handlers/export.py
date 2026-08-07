"""Экспорт архива файлом.

Файл собирается в памяти и сразу отправляется владельцу: на диске ничего
не остаётся, потому что выгрузка часто содержит личную переписку.
"""

from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.handlers.common import scope_filters, scope_title, show
from app.keyboards.callbacks import ExportCB, MenuCB
from app.keyboards.export import export_menu
from app.models.settings import UserSettings
from app.models.user import User
from app.repositories.uow import UnitOfWork
from app.services.export import MAX_ROWS, ExportService
from app.services.notifier import NotificationService
from app.utils.text import escape, human_size, plural

logger = structlog.get_logger(__name__)

router = Router(name="export")


def _screen(scope: str) -> str:
    return (
        "📤 <b>Экспорт архива</b>\n\n"
        f"Объём: <b>{escape(scope_title(scope))}</b>\n"
        f"Максимум за один раз: <b>{MAX_ROWS}</b> сообщений (самые свежие).\n\n"
        "Выберите формат:\n"
        "• <b>TXT</b> — читать глазами\n"
        "• <b>CSV</b> — открыть в таблице\n"
        "• <b>JSON</b> — для обработки программой\n"
        "• <b>HTML</b> — открыть в браузере"
    )


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    await message.answer(_screen("all"), reply_markup=export_menu("all"))


@router.callback_query(MenuCB.filter(F.action == "export"))
async def cb_export_entry(query: CallbackQuery) -> None:
    await show(query, _screen("all"), export_menu("all"))
    await query.answer()


@router.callback_query(ExportCB.filter(F.action == "open"))
async def cb_export_open(query: CallbackQuery, callback_data: ExportCB) -> None:
    await show(query, _screen(callback_data.scope), export_menu(callback_data.scope))
    await query.answer()


@router.callback_query(ExportCB.filter(F.action == "build"))
async def cb_export_build(
    query: CallbackQuery,
    callback_data: ExportCB,
    uow: UnitOfWork,
    user: User,
    user_settings: UserSettings,
    export_service: ExportService,
    notifier: NotificationService,
) -> None:
    """Собрать выгрузку и отдать её документом."""
    await query.answer("Готовлю файл…")

    filters = scope_filters(user.id, callback_data.scope)
    filename, content, count = await export_service.build(
        uow,
        owner=user,
        filters=filters,
        fmt=callback_data.fmt,
        timezone=user_settings.timezone,
    )
    if count == 0:
        await query.answer("Нечего выгружать: подборка пуста", show_alert=True)
        return

    word = plural(count, "сообщение", "сообщения", "сообщений")
    caption = (
        f"📤 <b>{escape(scope_title(callback_data.scope))}</b>\n"
        f"{count} {word} · {escape(human_size(len(content)))}"
    )
    result = await notifier.send_document(
        query.message.chat.id, filename, content, caption=caption
    )
    logger.info(
        "export.sent",
        user_id=user.telegram_id,
        fmt=callback_data.fmt,
        scope=callback_data.scope,
        count=count,
        ok=result.ok,
    )
    if not result.ok:
        await query.answer("Не удалось отправить файл, попробуйте позже", show_alert=True)
