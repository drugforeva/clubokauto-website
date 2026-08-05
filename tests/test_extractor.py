"""Тесты разбора сообщений.

extract() читает атрибуты через getattr, поэтому заглушек SimpleNamespace
достаточно — без сети и без сборки полных aiogram-объектов.
Проверяется главное: порядок проверок (кружок не видео, GIF не документ)
и то, что подпись к фото не теряется.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.business.extractor import extract


def test_plain_text() -> None:
    result = extract(SimpleNamespace(text="Привет"))
    assert result.content_type == "text"
    assert result.text == "Привет"
    assert result.media == []


def test_photo_keeps_caption_and_largest_size() -> None:
    small = SimpleNamespace(file_id="small", file_unique_id="u1", width=90, height=60)
    large = SimpleNamespace(
        file_id="large",
        file_unique_id="u2",
        width=1280,
        height=720,
        file_size=204800,
    )
    result = extract(SimpleNamespace(photo=[small, large], caption="На даче"))

    assert result.content_type == "photo"
    assert result.text == "На даче"  # подпись важнее пустого text
    assert len(result.media) == 1
    assert result.media[0].file_id == "large"  # самое крупное разрешение
    assert result.media[0].file_name == "photo.jpg"
    assert result.extra == {"width": 1280, "height": 720}


def test_video_note_wins_over_video() -> None:
    note = SimpleNamespace(file_id="note", file_unique_id="u3", duration=7)
    video = SimpleNamespace(file_id="video", file_unique_id="u4", duration=7)
    result = extract(SimpleNamespace(video_note=note, video=video))

    assert result.content_type == "video_note"
    assert result.media[0].file_id == "note"


def test_animation_wins_over_document() -> None:
    # Telegram к каждому GIF прикладывает ещё и document.
    animation = SimpleNamespace(file_id="gif", file_unique_id="u5", file_name="fun.gif")
    document = SimpleNamespace(file_id="doc", file_unique_id="u6", file_name="fun.gif")
    result = extract(SimpleNamespace(animation=animation, document=document))

    assert result.content_type == "animation"
    assert result.media[0].file_id == "gif"


def test_document_carries_metadata() -> None:
    document = SimpleNamespace(
        file_id="doc",
        file_unique_id="u7",
        file_name="договор.pdf",
        mime_type="application/pdf",
        file_size=51200,
    )
    result = extract(SimpleNamespace(document=document, caption="На подпись"))

    assert result.content_type == "document"
    assert result.text == "На подпись"
    assert result.media[0].file_name == "договор.pdf"
    assert result.media[0].mime_type == "application/pdf"
    assert result.media[0].file_size == 51200


def test_sticker_saves_emoji() -> None:
    sticker = SimpleNamespace(file_id="st", file_unique_id="u8", emoji="🔥", set_name="Pack")
    result = extract(SimpleNamespace(sticker=sticker))

    assert result.content_type == "sticker"
    assert result.extra == {"emoji": "🔥", "set_name": "Pack"}


def test_location_has_no_media() -> None:
    location = SimpleNamespace(latitude=55.75, longitude=37.61)
    result = extract(SimpleNamespace(location=location))

    assert result.content_type == "location"
    assert result.media == []
    assert result.extra == {"latitude": 55.75, "longitude": 37.61}


def test_contact_builds_readable_text() -> None:
    contact = SimpleNamespace(
        phone_number="+79990000000", first_name="Иван", last_name="Петров"
    )
    result = extract(SimpleNamespace(contact=contact))

    assert result.content_type == "contact"
    assert result.text == "Иван Петров +79990000000"


def test_poll_keeps_question_and_options() -> None:
    poll = SimpleNamespace(
        question="Куда едем?",
        options=[SimpleNamespace(text="Море"), SimpleNamespace(text="Горы")],
    )
    result = extract(SimpleNamespace(poll=poll))

    assert result.content_type == "poll"
    assert result.text == "Куда едем?"
    assert result.extra == {"options": ["Море", "Горы"]}


def test_unknown_type_is_still_archived() -> None:
    result = extract(SimpleNamespace(dice=SimpleNamespace(value=6)))

    assert result.content_type == "unknown"
    assert result.text is None
    assert result.media == []


def test_one_time_photo_is_marked_ephemeral() -> None:
    """Bot API таких сообщений не присылает — проверяем готовность к полю."""
    photo = SimpleNamespace(file_id="once", file_unique_id="u9", width=800, height=600)
    result = extract(SimpleNamespace(photo=[photo], ttl_seconds=5))

    assert result.content_type == "photo"
    assert result.extra["ephemeral"] is True
    assert result.extra["ephemeral_fields"] == {"ttl_seconds": 5}
    assert result.extra["width"] == 800  # старые пометки не затёрты


def test_view_once_flag_is_detected() -> None:
    video = SimpleNamespace(file_id="v", file_unique_id="u10", duration=3)
    result = extract(SimpleNamespace(video=video, view_once=True))

    assert result.extra["ephemeral"] is True
    assert result.extra["ephemeral_fields"] == {"view_once": True}


def test_spoiler_is_marked_separately() -> None:
    photo = SimpleNamespace(file_id="sp", file_unique_id="u11", width=10, height=10)
    result = extract(SimpleNamespace(photo=[photo], has_media_spoiler=True))

    assert result.extra["spoiler"] is True
    assert "ephemeral" not in result.extra


def test_ordinary_message_has_no_marks() -> None:
    result = extract(SimpleNamespace(text="Привет"))

    assert result.extra is None


def test_card_and_row_show_ephemeral_mark() -> None:
    from app.utils.formatting import message_card, message_row

    message = SimpleNamespace(
        sender_username="marina",
        sender_id=200200,
        content_type="photo",
        text=None,
        is_deleted=True,
        edit_count=0,
        chat=SimpleNamespace(username="marina"),
        extra_data={"ephemeral": True},
    )

    assert "🔥 одноразовое" in message_card(message)
    assert "🔥" in message_row(message)
