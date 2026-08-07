"""Статистика: личная (/stats) и общая (/admin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.utils.formatting import content_label, stats_block
from app.utils.text import human_size
from app.utils.time import days_ago, fmt_date, fmt_duration

if TYPE_CHECKING:
    from app.models.settings import UserSettings
    from app.models.user import User
    from app.repositories.uow import UnitOfWork


class StatsService:
    async def personal(
        self, uow: UnitOfWork, *, owner: User, settings: UserSettings
    ) -> str:
        """Сводка по архиву одного владельца."""
        counters = await uow.messages.counters(owner.id)
        chats = await uow.chats.count_for_owner(owner.id)
        media = await uow.media.count_for_owner(owner.id)
        stored = await uow.media.stored_bytes(owner.id)
        deletions = await uow.deleted.count_for_owner(owner.id)
        first_at = await uow.messages.first_sent_at(owner.id)

        rows: list[tuple[str, object]] = [
            ("Сообщений в архиве", counters["total"]),
            ("Из них удалено собеседниками", counters["deleted"]),
            ("С правками", counters["edited"]),
            ("Событий удаления", deletions),
            ("Диалогов", chats),
            ("Вложений", media),
        ]
        if stored:
            rows.append(("На диске", human_size(stored)))
        if first_at:
            rows.append(("Первое сообщение", fmt_date(first_at, settings.timezone)))

        blocks = [stats_block("📊 Статистика архива", rows)]

        types = await uow.messages.type_breakdown(owner.id)
        if types:
            lines = ["", "<b>По типам</b>", ""]
            lines += [f"{content_label(name)}: <b>{count}</b>" for name, count in types[:8]]
            blocks.append("\n".join(lines))

        top = await uow.messages.top_chats(owner.id)
        if top:
            lines = ["", "<b>Активные диалоги</b>", ""]
            lines += [f"{name}: <b>{count}</b>" for name, count in top]
            blocks.append("\n".join(lines))

        return "\n".join(blocks)

    async def global_summary(
        self, uow: UnitOfWork, *, metrics: Any | None = None
    ) -> str:
        """Сводка по всему боту — только для админа."""
        users = await uow.users.count()
        active = await uow.users.count_active()
        connections = await uow.connections.count_enabled()
        chats = await uow.chats.count()
        messages = await uow.messages.count_all()
        media = await uow.media.count_all()
        deletions = await uow.deleted.count_all()
        day = days_ago(1)
        week = days_ago(7)

        rows: list[tuple[str, object]] = [
            ("Пользователей", users),
            ("Из них активных", active),
            ("Активных подключений", connections),
            ("Диалогов", chats),
            ("Сообщений", messages),
            ("Вложений", media),
            ("Удалений всего", deletions),
            ("Новых сообщений за сутки", await uow.messages.count_since(day)),
            ("Новых пользователей за неделю", await uow.users.created_since(week)),
        ]
        blocks = [stats_block("🛠 Статистика бота", rows)]

        if metrics is not None:
            snapshot = metrics.snapshot()
            lines = ["", "<b>Нагрузка</b>", ""]
            lines.append(f"В работе: <b>{fmt_duration(snapshot['uptime_seconds'])}</b>")
            lines.append(f"Апдейтов обработано: <b>{snapshot['updates']}</b>")
            lines.append(f"Ошибок: <b>{snapshot['errors']}</b>")
            blocks.append("\n".join(lines))

        return "\n".join(blocks)
