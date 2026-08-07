"""Текстовые хелперы: экранирование, обрезка, размеры, склонения.

Всё, что уходит в Telegram, идёт с parse_mode=HTML, поэтому любой пользовательский
текст обязательно прогоняется через escape(). Иначе одно сообщение вида «<b»
валит отправку уведомления с ошибкой разбора сущоностей.
"""

from __future__ import annotations

import html
import re

_UNSAFE_FILENAME = re.compile(r"[^\w\-. ]+", re.UNICODE)
_MULTI_SPACE = re.compile(r"\s+")
_SIZE_UNITS = ("Б", "КБ", "МБ", "ГБ", "ТБ")


def escape(value: str | None) -> str:
    """Экранировать текст для HTML-разметки Telegram."""
    if not value:
        return ""
    return html.escape(str(value), quote=False)


def shorten(value: str | None, limit: int = 80) -> str:
    """Обрезать текст до limit символов с многоточием.

    Переносы строк склеиваются в пробел: в однострочной кнопке или строке
    списка многострочный текст ломает вёрстку.
    """
    if not value:
        return ""
    flat = _MULTI_SPACE.sub(" ", str(value)).strip()
    if len(flat) <= limit:
        return flat
    return flat[: max(limit - 1, 1)].rstrip() + "…"


def plural(count: int, one: str, few: str, many: str) -> str:
    """Русское склонение: 1 вложение, 2 вложения, 5 вложений."""
    number = abs(int(count))
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def human_size(size: int | float | None) -> str:
    """Байты в человеческий вид."""
    if not size or size <= 0:
        return "0 Б"
    value = float(size)
    for unit in _SIZE_UNITS:
        if value < 1024 or unit == _SIZE_UNITS[-1]:
            if unit == "Б":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}".replace(".0 ", " ")
        value /= 1024
    return f"{value:.1f} {_SIZE_UNITS[-1]}"


def sanitize_filename(value: str | None, fallback: str) -> str:
    """Превратить присланное имя файла в безопасное имя на диске.

    Имя приходит от собеседника и вполне может содержать «../» или нулевой байт,
    поэтому склеивать его с путём напрямую нельзя.
    """
    raw = (value or "").strip().replace("\x00", "")
    raw = raw.replace("/", "_").replace("\\", "_")
    cleaned = _UNSAFE_FILENAME.sub("_", raw).strip(". _")
    if not cleaned:
        cleaned = fallback
    return cleaned[:120]
