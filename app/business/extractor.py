"""Разбор сообщения Telegram в плоскую структуру для базы.

Функции намеренно читают атрибуты через getattr, а не требуют aiogram-типов:
так тесты проверяют разбор на простых заглушках без сети и без базы.

Порядок проверок важен: animation в Telegram одновременно выглядит как document,
а video_note — как video, поэтому более узкие типы идут раньше. Текст проверяется
последним, иначе фото с подписью уехало бы в «текст».
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MediaPayload:
    """Одно вложение сообщения."""

    media_type: str
    file_id: str
    file_unique_id: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    duration: int | None = None


@dataclass(slots=True)
class Extracted:
    """Результат разбора."""

    content_type: str = "unknown"
    text: str | None = None
    extra: dict[str, Any] | None = None
    media: list[MediaPayload] = field(default_factory=list)


def _text_of(message: Any) -> str | None:
    return getattr(message, "text", None) or getattr(message, "caption", None)


def _payload(obj: Any, media_type: str, *, file_name: str | None = None) -> MediaPayload:
    return MediaPayload(
        media_type=media_type,
        file_id=str(getattr(obj, "file_id", "")),
        file_unique_id=getattr(obj, "file_unique_id", None),
        file_name=file_name or getattr(obj, "file_name", None),
        mime_type=getattr(obj, "mime_type", None),
        file_size=getattr(obj, "file_size", None),
        duration=getattr(obj, "duration", None),
    )


def _photo(message: Any) -> Extracted | None:
    photos = getattr(message, "photo", None)
    if not photos:
        return None
    # Последний элемент — самое крупное разрешение.
    largest = photos[-1]
    payload = _payload(largest, "photo", file_name="photo.jpg")
    extra = {
        "width": getattr(largest, "width", None),
        "height": getattr(largest, "height", None),
    }
    return Extracted("photo", _text_of(message), extra, [payload])


def _video_note(message: Any) -> Extracted | None:
    obj = getattr(message, "video_note", None)
    if obj is None:
        return None
    return Extracted(
        "video_note",
        _text_of(message),
        {"duration": getattr(obj, "duration", None)},
        [_payload(obj, "video_note", file_name="video_note.mp4")],
    )


def _video(message: Any) -> Extracted | None:
    obj = getattr(message, "video", None)
    if obj is None:
        return None
    return Extracted("video", _text_of(message), None, [_payload(obj, "video")])


def _voice(message: Any) -> Extracted | None:
    obj = getattr(message, "voice", None)
    if obj is None:
        return None
    return Extracted(
        "voice",
        _text_of(message),
        {"duration": getattr(obj, "duration", None)},
        [_payload(obj, "voice", file_name="voice.ogg")],
    )


def _animation(message: Any) -> Extracted | None:
    obj = getattr(message, "animation", None)
    if obj is None:
        return None
    return Extracted("animation", _text_of(message), None, [_payload(obj, "animation")])


def _audio(message: Any) -> Extracted | None:
    obj = getattr(message, "audio", None)
    if obj is None:
        return None
    extra = {
        "title": getattr(obj, "title", None),
        "performer": getattr(obj, "performer", None),
    }
    return Extracted("audio", _text_of(message), extra, [_payload(obj, "audio")])


def _document(message: Any) -> Extracted | None:
    obj = getattr(message, "document", None)
    if obj is None:
        return None
    return Extracted("document", _text_of(message), None, [_payload(obj, "document")])


def _sticker(message: Any) -> Extracted | None:
    obj = getattr(message, "sticker", None)
    if obj is None:
        return None
    extra = {
        "emoji": getattr(obj, "emoji", None),
        "set_name": getattr(obj, "set_name", None),
    }
    return Extracted("sticker", _text_of(message), extra, [_payload(obj, "sticker")])


def _location(message: Any) -> Extracted | None:
    obj = getattr(message, "location", None)
    if obj is None:
        return None
    extra = {
        "latitude": getattr(obj, "latitude", None),
        "longitude": getattr(obj, "longitude", None),
    }
    return Extracted("location", _text_of(message), extra, [])


def _contact(message: Any) -> Extracted | None:
    obj = getattr(message, "contact", None)
    if obj is None:
        return None
    extra = {
        "phone_number": getattr(obj, "phone_number", None),
        "first_name": getattr(obj, "first_name", None),
        "last_name": getattr(obj, "last_name", None),
    }
    name = f"{extra['first_name'] or ''} {extra['last_name'] or ''}".strip()
    text = f"{name} {extra['phone_number'] or ''}".strip() or None
    return Extracted("contact", text, extra, [])


def _poll(message: Any) -> Extracted | None:
    obj = getattr(message, "poll", None)
    if obj is None:
        return None
    options = [getattr(item, "text", None) for item in getattr(obj, "options", []) or []]
    extra = {"options": [item for item in options if item]}
    return Extracted("poll", getattr(obj, "question", None), extra, [])


def _plain_text(message: Any) -> Extracted | None:
    text = _text_of(message)
    if not text:
        return None
    return Extracted("text", text, None, [])


# Порядок проверок — часть логики, менять его нельзя без необходимости.
_EXTRACTORS: tuple[Callable[[Any], Extracted | None], ...] = (
    _photo,
    _video_note,
    _video,
    _voice,
    _animation,
    _audio,
    _document,
    _sticker,
    _location,
    _contact,
    _poll,
    _plain_text,
)


# Поля, которыми Telegram помечает исчезающие медиа: фото на один просмотр
# и снимки с таймером. Сейчас Bot API не отдаёт ни одного из них, но проверка
# через getattr ничего не стоит. Если такое сообщение всё же придёт, архив
# пометит его и скачает файл немедленно (см. CaptureService.capture_message).
_EPHEMERAL_ATTRS: tuple[str, ...] = (
    "ttl_seconds",
    "self_destruct_time",
    "view_once",
    "is_view_once",
    "one_time",
    "is_one_time",
)


def _marks(message: Any) -> dict[str, Any]:
    """Пометки об одноразовом медиа и спойлере."""
    found = {
        attr: getattr(message, attr, None)
        for attr in _EPHEMERAL_ATTRS
        if getattr(message, attr, None)
    }
    marks: dict[str, Any] = {}
    if found:
        marks["ephemeral"] = True
        marks["ephemeral_fields"] = found
    if getattr(message, "has_media_spoiler", False):
        marks["spoiler"] = True
    return marks


def extract(message: Any) -> Extracted:
    """Разобрать сообщение. Неизвестный тип попадает в архив как unknown."""
    result = Extracted(content_type="unknown", text=None, extra=None, media=[])
    for extractor in _EXTRACTORS:
        parsed = extractor(message)
        if parsed is not None:
            result = parsed
            break
    marks = _marks(message)
    if marks:
        result.extra = dict(result.extra or {})
        result.extra.update(marks)
    return result
