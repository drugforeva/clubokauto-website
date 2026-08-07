"""Тесты работы со временем.

Главная проверяемая грабля: Telegram присылает date целым числом,
а в базе лежит naive UTC datetime.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.utils.time import (
    as_datetime,
    day_end,
    fmt_datetime,
    fmt_duration,
    is_known_zone,
    parse_user_date,
    resolve_zone,
    to_zone,
    utcnow,
)


def test_utcnow_is_naive() -> None:
    assert utcnow().tzinfo is None


def test_as_datetime_accepts_unix_timestamp() -> None:
    # 1 января 2026 00:00 UTC
    assert as_datetime(1767225600) == datetime(2026, 1, 1, 0, 0)


def test_as_datetime_rejects_bool() -> None:
    # bool — подкласс int, без отдельной проверки True стал бы 1970 годом.
    assert as_datetime(True) is None
    assert as_datetime(None) is None
    assert as_datetime("не дата") is None


def test_as_datetime_strips_timezone() -> None:
    aware = datetime(2026, 8, 5, 3, 0, tzinfo=UTC)
    assert as_datetime(aware) == datetime(2026, 8, 5, 3, 0)
    assert as_datetime("2026-08-05T03:00:00Z") == datetime(2026, 8, 5, 3, 0)


def test_resolve_zone_falls_back_to_utc() -> None:
    assert str(resolve_zone("Europe/Moscow")) == "Europe/Moscow"
    assert str(resolve_zone("Марс/Кратер")) == "UTC"
    assert str(resolve_zone(None)) == "UTC"


def test_is_known_zone() -> None:
    assert is_known_zone(" Europe/Moscow ") is True
    assert is_known_zone("Москва") is False


def test_to_zone_shifts_to_user_offset() -> None:
    local = to_zone(datetime(2026, 8, 4, 21, 0), "Europe/Moscow")
    assert (local.day, local.hour) == (5, 0)


def test_fmt_datetime_uses_user_zone() -> None:
    assert fmt_datetime(datetime(2026, 8, 4, 21, 0), "Europe/Moscow") == "05.08.2026 00:00"
    assert fmt_datetime(None) == "—"


def test_parse_user_date_supports_several_formats() -> None:
    expected = datetime(2026, 8, 4, 21, 0)  # начало московских суток в UTC
    assert parse_user_date("05.08.2026", "Europe/Moscow") == expected
    assert parse_user_date("2026-08-05", "Europe/Moscow") == expected
    assert parse_user_date("05/08/2026", "Europe/Moscow") == expected


def test_parse_user_date_returns_none_on_garbage() -> None:
    assert parse_user_date("вчера") is None
    assert parse_user_date("32.13.2026") is None


def test_day_end_is_last_microsecond_of_day() -> None:
    end = day_end(datetime(2026, 8, 5, 0, 0))
    assert end == datetime(2026, 8, 5, 23, 59, 59, 999999)


def test_fmt_duration() -> None:
    assert fmt_duration(-5) == "0с"
    assert fmt_duration(42) == "42с"
    assert fmt_duration(605) == "10м 5с"
    assert fmt_duration(8100) == "2ч 15м"
    assert fmt_duration(180000) == "2д 2ч"
