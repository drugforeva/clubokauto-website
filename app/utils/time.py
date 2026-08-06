"""Работа со временем.

В базе всё хранится как naive UTC — это единственный формат, который
одинаково ведёт себя в PostgreSQL и sqlite. Конвертация в пояс пользователя
происходит только на выводе (экспорт, фильтры по датам).

as_datetime() — грабли из истории проекта: Telegram присылает date/edit_date
целым числом (Unix-время), а колонка ждёт datetime.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%d/%m/%Y")


def utcnow() -> datetime:
    """Текущее время в UTC без tzinfo."""
    return datetime.now(UTC).replace(tzinfo=None)


def as_datetime(value: object) -> datetime | None:
    """Привести всё, что прислал Telegram, к naive UTC datetime."""
    if value is None:
        return None
    if isinstance(value, bool):  # защита от True/False, bool — подкласс int
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value), tz=UTC).replace(tzinfo=None)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, str):
        raw = value.strip().replace("Z", "+00:00")
        try:
            return as_datetime(datetime.fromisoformat(raw))
        except ValueError:
            return None
    return None


def resolve_zone(name: str | None) -> ZoneInfo:
    """Зона по имени с тихим фолбэком на UTC."""
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def is_known_zone(name: str) -> bool:
    """Существует ли такой часовой пояс (проверка ввода в /settings)."""
    try:
        ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def to_zone(value: datetime, tz_name: str | None) -> datetime:
    """naive UTC -> aware datetime в поясе пользователя."""
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone(resolve_zone(tz_name))


def fmt_datetime(value: datetime | None, tz_name: str | None = None) -> str:
    """Дата и время для файлов экспорта."""
    if value is None:
        return "—"
    return to_zone(value, tz_name).strftime("%d.%m.%Y %H:%M")


def fmt_date(value: datetime | None, tz_name: str | None = None) -> str:
    if value is None:
        return "—"
    return to_zone(value, tz_name).strftime("%d.%m.%Y")


def fmt_duration(seconds: float) -> str:
    """Секунды -> «2ч 15м» (uptime в админке)."""
    total = int(max(seconds, 0))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days}д {hours}ч"
    if hours:
        return f"{hours}ч {minutes}м"
    if minutes:
        return f"{minutes}м {secs}с"
    return f"{secs}с"


def parse_user_date(raw: str, tz_name: str | None = None) -> datetime | None:
    """Дата из сообщения пользователя -> naive UTC (начало суток)."""
    text = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        local = parsed.replace(tzinfo=resolve_zone(tz_name))
        return local.astimezone(UTC).replace(tzinfo=None)
    return None


def day_end(value: datetime) -> datetime:
    """Конец суток для верхней границы фильтра по дате."""
    return value + timedelta(days=1) - timedelta(microseconds=1)


def days_ago(days: int) -> datetime:
    return utcnow() - timedelta(days=days)
