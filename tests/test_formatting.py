"""Тесты текстовых хелперов и шаблонов уведомлений.

Самое важное здесь — экранирование: всё уходит в Telegram с parse_mode=HTML,
и одно сообщение с «<b» внутри уронит отправку уведомления.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.utils.formatting import (
    chat_label,
    content_label,
    deletion_notice,
    edit_notice,
    message_card,
    message_row,
    sender_link,
    sender_name,
    short_label,
    stats_block,
    unknown_deletion_notice,
    versions_block,
)
from app.utils.text import escape, human_size, plural, sanitize_filename, shorten


def _message(**kwargs: object) -> SimpleNamespace:
    base = {
        "sender_username": "marina",
        "sender_first_name": "Марина",
        "sender_last_name": None,
        "sender_id": 200200,
        "content_type": "text",
        "text": "Текст",
        "is_deleted": False,
        "edit_count": 0,
        "chat": SimpleNamespace(username="marina", title=None, first_name="Марина"),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_escape_protects_html() -> None:
    assert escape("<b>болд & точка") == "&lt;b&gt;болд &amp; точка"
    assert escape(None) == ""


def test_shorten_flattens_and_cuts() -> None:
    assert shorten("первая\nвторая") == "первая вторая"
    assert shorten("a" * 100, 10) == "a" * 9 + "…"
    assert shorten(None) == ""


def test_plural_russian_forms() -> None:
    assert plural(1, "вложение", "вложения", "вложений") == "вложение"
    assert plural(3, "вложение", "вложения", "вложений") == "вложения"
    assert plural(5, "вложение", "вложения", "вложений") == "вложений"
    assert plural(11, "вложение", "вложения", "вложений") == "вложений"
    assert plural(21, "вложение", "вложения", "вложений") == "вложение"


def test_human_size() -> None:
    assert human_size(0) == "0 Б"
    assert human_size(None) == "0 Б"
    assert human_size(512) == "512 Б"
    assert human_size(2048) == "2 КБ"
    assert human_size(1024 * 1024 * 3.5) == "3.5 МБ"


def test_sanitize_filename_blocks_traversal() -> None:
    assert sanitize_filename("../../etc/passwd", "file.bin") == "etc_passwd"
    assert sanitize_filename("", "file.bin") == "file.bin"
    assert sanitize_filename("отчёт за год.pdf", "file.bin") == "отчёт за год.pdf"
    assert len(sanitize_filename("и" * 300, "file.bin")) == 120


def test_content_labels_have_fallback() -> None:
    assert content_label("photo") == "📷 Фото"
    assert content_label(None) == content_label("что-то новое")
    assert short_label("voice") == "🎤"


def test_sender_name_prefers_username() -> None:
    assert sender_name(_message()) == "@marina"
    assert sender_name(_message(sender_username=None)) == "Марина"
    assert (
        sender_name(_message(sender_username=None, sender_first_name=None)) == "id200200"
    )


def test_sender_link_is_clickable() -> None:
    assert "t.me/marina" in sender_link(_message())
    assert "tg://user?id=200200" in sender_link(_message(sender_username=None, sender_first_name=None))


def test_chat_label_fallbacks() -> None:
    assert chat_label(SimpleNamespace(username="marina")) == "@marina"
    assert chat_label(SimpleNamespace(username=None, title="Работа")) == "Работа"
    assert chat_label(None) == "Диалог"


def test_deletion_notice_escapes_body() -> None:
    notice = deletion_notice(_message(text="<script>alert(1)</script>"))

    assert "Собеседник удалил сообщение" in notice
    assert "<script>" not in notice
    assert "&lt;script&gt;" in notice


def test_deletion_notice_mentions_media() -> None:
    media = [SimpleNamespace(file_size=1024), SimpleNamespace(file_size=1024)]
    notice = deletion_notice(_message(content_type="photo", text=None), media)

    assert "📎 2 вложения" in notice
    assert "без текста" in notice


def test_unknown_deletion_notice() -> None:
    assert "1 сообщение" in unknown_deletion_notice(1)
    assert "5 сообщений" in unknown_deletion_notice(5)


def test_edit_notice_shows_all_versions_in_order() -> None:
    versions = [
        SimpleNamespace(version=2, text="второй"),
        SimpleNamespace(version=1, text="первый"),
    ]
    notice = edit_notice(_message(), versions)

    assert notice.index("первый") < notice.index("второй")
    assert "исходник" in notice
    assert "версия 2" in notice


def test_versions_block_without_edits() -> None:
    assert versions_block([]) == "Правок не было."


def test_message_card_marks_deleted() -> None:
    card = message_card(_message(is_deleted=True), versions_count=3)

    assert "Удалённое сообщение" in card
    assert "версий текста: 3" in card


def test_message_card_owner_hint_for_admin() -> None:
    card = message_card(_message(), owner_hint="@owner")
    assert "Владелец: @owner" in card


def test_message_row_is_compact() -> None:
    row = message_row(_message(is_deleted=True, edit_count=2, text="Очень длинный " * 10))

    assert row.startswith("🗑✏️📝 @marina: ")
    assert "\n" not in row
    assert len(row) < 120


def test_stats_block_renders_rows() -> None:
    block = stats_block("Статистика", [("Всего", 10), ("Удалено", 2)])

    assert block.startswith("<b>Статистика</b>")
    assert "Всего: <b>10</b>" in block
