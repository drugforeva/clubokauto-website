"""Экспорт архива в файл.

Даты в файлах есть (в отличие от уведомлений и карточек) и сразу переводятся
в часовой пояс владельца: файл читают глазами, а не кодом.
"""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

from app.utils.text import escape
from app.utils.time import fmt_datetime, utcnow

if TYPE_CHECKING:
    from app.models.user import User
    from app.repositories.messages import MessageFilters
    from app.repositories.uow import UnitOfWork

FORMATS: tuple[str, ...] = ("txt", "csv", "json", "html")
FORMAT_LABELS: dict[str, str] = {
    "txt": "📄 TXT",
    "csv": "📊 CSV",
    "json": "🧾 JSON",
    "html": "🌐 HTML",
}
MAX_ROWS = 5000


class ExportService:
    """Собирает выборку и превращает её в байты файла."""

    async def build(
        self,
        uow: UnitOfWork,
        *,
        owner: User,
        filters: MessageFilters,
        fmt: str,
        timezone: str,
    ) -> tuple[str, bytes, int]:
        """Вернуть (имя файла, содержимое, число строк)."""
        if fmt not in FORMATS:
            raise ValueError(f"Неизвестный формат экспорта: {fmt}")
        rows = await uow.messages.export_rows(filters, limit=MAX_ROWS)
        builder = {
            "txt": self._as_txt,
            "csv": self._as_csv,
            "json": self._as_json,
            "html": self._as_html,
        }[fmt]
        content = builder(rows, timezone)
        stamp = utcnow().strftime("%Y%m%d_%H%M")
        filename = f"sohrano_{owner.telegram_id}_{stamp}.{fmt}"
        return filename, content.encode("utf-8"), len(rows)

    def _row_dict(self, message: Any, timezone: str) -> dict[str, Any]:
        chat = getattr(message, "chat", None)
        media = list(getattr(message, "media", []) or [])
        return {
            "дата": fmt_datetime(message.sent_at, timezone),
            "диалог": getattr(chat, "display_name", "") if chat else "",
            "автор": f"{message.sender_first_name or ''} {message.sender_last_name or ''}".strip(),
            "username": f"@{message.sender_username}" if message.sender_username else "",
            "тип": message.content_type,
            "текст": message.text or "",
            "вложений": len(media),
            "изменений": int(message.edit_count or 0),
            "удалено": "да" if message.is_deleted else "нет",
            "исходящее": "да" if message.is_outgoing else "нет",
        }

    def _as_txt(self, rows: list[Any], timezone: str) -> str:
        if not rows:
            return "Архив пуст: под выбранные условия сообщений нет.\n"
        lines = ["Сохрано — экспорт архива", "=" * 40, ""]
        for message in rows:
            data = self._row_dict(message, timezone)
            marks = []
            if message.is_deleted:
                marks.append("удалено")
            if message.edit_count:
                marks.append(f"правок: {message.edit_count}")
            suffix = f" [{', '.join(marks)}]" if marks else ""
            author = data["username"] or data["автор"] or "неизвестный"
            lines.append(f"[{data['дата']}] {data['диалог']} — {author}{suffix}")
            lines.append(f"  тип: {data['тип']}")
            if data["текст"]:
                lines.append(f"  {data['текст']}")
            if data["вложений"]:
                lines.append(f"  вложений: {data['вложений']}")
            lines.append("")
        return "\n".join(lines)

    def _as_csv(self, rows: list[Any], timezone: str) -> str:
        buffer = io.StringIO()
        fieldnames = [
            "дата",
            "диалог",
            "автор",
            "username",
            "тип",
            "текст",
            "вложений",
            "изменений",
            "удалено",
            "исходящее",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for message in rows:
            writer.writerow(self._row_dict(message, timezone))
        # BOM нужен, иначе Excel открывает кириллицу кракозябрами.
        return "\ufeff" + buffer.getvalue()

    def _as_json(self, rows: list[Any], timezone: str) -> str:
        payload = {
            "exported_at": fmt_datetime(utcnow(), timezone),
            "timezone": timezone,
            "count": len(rows),
            "messages": [self._row_dict(message, timezone) for message in rows],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _as_html(self, rows: list[Any], timezone: str) -> str:
        head = (
            "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
            "<title>Сохрано — экспорт</title><style>"
            "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;color:#1f2328}"
            ".m{border:1px solid #e1e4e8;border-radius:10px;padding:12px;margin-bottom:10px}"
            ".meta{color:#57606a;font-size:13px;margin-bottom:6px}"
            ".del{border-color:#f1a5a5;background:#fff5f5}"
            "</style></head><body><h1>Сохрано — экспорт архива</h1>"
        )
        parts = [head, f"<p>Сообщений: {len(rows)}</p>"]
        for message in rows:
            data = self._row_dict(message, timezone)
            css = "m del" if message.is_deleted else "m"
            author = data["username"] or data["автор"] or "неизвестный"
            parts.append(
                f'<div class="{css}"><div class="meta">{escape(data["дата"])} · '
                f"{escape(data['диалог'])} · {escape(author)} · {escape(data['тип'])}</div>"
                f"<div>{escape(data['текст']) or '<i>без текста</i>'}</div></div>"
            )
        parts.append("</body></html>")
        return "".join(parts)
