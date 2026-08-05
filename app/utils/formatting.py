"""Форматирование уведомлений, карточек и строк списка.

Два решения владельца, зафиксированные здесь:
1. Отметок времени нет ни в уведомлениях, ни в карточке, ни в списке
   истории — даты остались только в файлах экспорта.
2. Подпись автора — это @username, а не имя: username однозначно
   определяет человека, тогда как имя меняется в один клик.
Функции намеренно duck-typed: им достаточно любого объекта с нужными
атрибутами, поэтому тесты обходятся без базы.
"""

from __future__ import annotations

from typing import Any

from app.utils.text import escape, human_size, plural, shorten

CONTENT_LABELS: dict[str, str] = {
    "text": "📝 Текст",
    "photo": "📷 Фото",
    "video": "🎥 Видео",
    "voice": "🎤 Голосовое",
    "video_note": "⭕ Кружок",
    "document": "📄 Документ",
    "animation": "🎬 GIF",
    "sticker": "🧩 Стикер",
    "audio": "🎵 Аудио",
    "location": "📍 Геолокация",
    "contact": "👤 Контакт",
    "poll": "📊 Опрос",
    "unknown": "❓ Другое",
}

SHORT_LABELS: dict[str, str] = {
    "text": "📝",
    "photo": "📷",
    "video": "🎥",
    "voice": "🎤",
    "video_note": "⭕",
    "document": "📄",
    "animation": "🎬",
    "sticker": "🧩",
    "audio": "🎵",
    "location": "📍",
    "contact": "👤",
    "poll": "📊",
    "unknown": "❓",
}


def content_label(content_type: str | None) -> str:
    return CONTENT_LABELS.get(content_type or "unknown", CONTENT_LABELS["unknown"])


def short_label(content_type: str | None) -> str:
    return SHORT_LABELS.get(content_type or "unknown", SHORT_LABELS["unknown"])


def sender_name(message: Any) -> str:
    """@username, если есть; иначе имя; иначе id."""
    username = getattr(message, "sender_username", None)
    if username:
        return f"@{username}"
    first = getattr(message, "sender_first_name", None) or ""
    last = getattr(message, "sender_last_name", None) or ""
    name = f"{first} {last}".strip()
    if name:
        return name
    sender_id = getattr(message, "sender_id", None)
    return f"id{sender_id}" if sender_id else "Неизвестный"


def sender_link(message: Any) -> str:
    """Кликабельная подпись.

    С username — ссылка t.me/username (работает в мобильном, десктопе и вебе),
    без username — tg://user?id=.
    """
    label = escape(sender_name(message))
    username = getattr(message, "sender_username", None)
    if username:
        return f'<a href="https://t.me/{username}">{label}</a>'
    sender_id = getattr(message, "sender_id", None)
    if sender_id:
        return f'<a href="tg://user?id={sender_id}">{label}</a>'
    return label


def chat_label(chat: Any) -> str:
    """Название диалога для фильтров и списков."""
    if chat is None:
        return "Диалог"
    username = getattr(chat, "username", None)
    if username:
        return f"@{username}"
    for attr in ("title", "first_name"):
        value = getattr(chat, attr, None)
        if value:
            return str(value)
    return f"chat {getattr(chat, 'telegram_chat_id', '')}".strip()


def _body(message: Any) -> str:
    """Тело сообщения или пометка о типе без текста."""
    text = getattr(message, "text", None)
    if text:
        return escape(text)
    return f"<i>{escape(content_label(getattr(message, 'content_type', None)))} без текста</i>"


def _media_line(media: list[Any] | None) -> str:
    if not media:
        return ""
    labels = ", ".join(
        SHORT_LABELS.get(getattr(item, "media_type", ""), "📎") for item in media
    )
    return f"📎 {labels}"


def _flags(message: Any) -> dict[str, Any]:
    """Служебные пометки из extra_data: одноразовое медиа, спойлер."""
    extra = getattr(message, "extra_data", None)
    return extra if isinstance(extra, dict) else {}


def _flags_line(message: Any) -> str:
    """Строка с пометками или пустота, если помечать нечего."""
    marks = _flags(message)
    parts = []
    if marks.get("ephemeral"):
        parts.append("🔥 одноразовое")
    if marks.get("spoiler"):
        parts.append("🙈 под спойлером")
    return " · ".join(parts)


def deletion_notice(message: Any, media: list[Any] | None = None) -> str:
    """Уведомление об удалённом сообщении."""
    name = escape(sender_name(message))
    lines = [f"🗑 <b>{name} удалил(а) сообщение</b>"]
    flags = _flags_line(message)
    if flags:
        lines.append(flags)
    lines += ["", _body(message)]
    return "\n".join(lines)


def unknown_deletion_notice(count: int) -> str:
    """Удалено сообщение, которого нет в базе (пришло до подключения)."""
    word = plural(count, "сообщение", "сообщения", "сообщений")
    return (
        "🗑 <b>Удалено сообщение вне архива</b>\n"
        f"Не сохранено: {count} {word}. "
        "Бот видит только то, что пришло после подключения."
    )


def edit_notice(message: Any, versions: list[Any] | None = None) -> str:
    """Уведомление о правке: версия 1 — исходник, дальше по записи на правку."""
    lines = [
        "✏️ <b>Собеседник изменил сообщение</b>",
        f"От: {sender_link(message)}",
    ]
    ordered = sorted(versions or [], key=lambda item: getattr(item, "version", 0))
    if ordered:
        lines.append("")
        for item in ordered:
            number = getattr(item, "version", 0)
            title = "исходник" if number <= 1 else f"версия {number}"
            body = escape(getattr(item, "text", None) or "") or "<i>пусто</i>"
            lines.append(f"<b>{title}:</b> {body}")
    else:
        lines += ["", _body(message)]
    return "\n".join(lines)


def versions_block(versions: list[Any]) -> str:
    """Полная история правок для отдельного экрана."""
    if not versions:
        return "Правок не было."
    lines = ["✏️ <b>История правок</b>", ""]
    for item in sorted(versions, key=lambda value: getattr(value, "version", 0)):
        number = getattr(item, "version", 0)
        title = "исходник" if number <= 1 else f"версия {number}"
        body = escape(getattr(item, "text", None) or "") or "<i>пусто</i>"
        lines.append(f"<b>{title}:</b> {body}")
    return "\n".join(lines)


def message_card(
    message: Any,
    media: list[Any] | None = None,
    versions_count: int = 0,
    owner_hint: str | None = None,
) -> str:
    """Карточка одного сообщения."""
    header = "🗑 <b>Удалённое сообщение</b>"
    if not getattr(message, "is_deleted", False):
        header = "💬 <b>Сообщение</b>"
    lines = [header]
    if owner_hint:
        lines.append(f"Владелец: {escape(owner_hint)}")
    name = escape(sender_name(message))
    lines.append(f"От: <b>{name}</b>")
    flags = _flags_line(message)
    if flags:
        lines.append(flags)
    lines += ["", _body(message)]
    if versions_count > 1:
        lines += ["", f"✏️ версий текста: {versions_count}"]
    return "\n".join(lines)


def message_row(message: Any, limit: int = 46) -> str:
    """Короткая строка для кнопки в списке (без HTML и без дат)."""
    marks = []
    if getattr(message, "is_deleted", False):
        marks.append("🗑")
    if int(getattr(message, "edit_count", 0) or 0) > 0:
        marks.append("✏️")
    if _flags(message).get("ephemeral"):
        marks.append("🔥")
    marks.append(short_label(getattr(message, "content_type", None)))
    body = getattr(message, "text", None) or content_label(
        getattr(message, "content_type", None)
    ).split(" ", 1)[-1]
    return f"{''.join(marks)} {sender_name(message)}: {shorten(body, limit)}"


def stats_block(title: str, rows: list[tuple[str, object]]) -> str:
    """Общий блок «ключ: значение» для статистики и админки."""
    lines = [f"<b>{escape(title)}</b>", ""]
    lines += [f"{escape(name)}: <b>{escape(str(value))}</b>" for name, value in rows]
    return "\n".join(lines)
