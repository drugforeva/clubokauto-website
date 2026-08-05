"""Тесты постраничного вывода.

Нажатая старая кнопка легко приносит номер страницы, которой больше нет,
поэтому границы проверяются отдельно.
"""

from __future__ import annotations

from app.utils.pagination import Page, normalize_page, offset_for, total_pages


def test_total_pages_never_returns_zero() -> None:
    assert total_pages(0) == 1
    assert total_pages(-10) == 1


def test_total_pages_rounds_up() -> None:
    assert total_pages(8, 8) == 1
    assert total_pages(9, 8) == 2
    assert total_pages(17, 8) == 3


def test_normalize_page_clamps_to_range() -> None:
    assert normalize_page(0, 20, 8) == 1
    assert normalize_page(99, 20, 8) == 3
    assert normalize_page(2, 20, 8) == 2


def test_normalize_page_survives_broken_input() -> None:
    assert normalize_page("страница", 20, 8) == 1  # type: ignore[arg-type]
    assert normalize_page(None, 20, 8) == 1  # type: ignore[arg-type]


def test_offset_for() -> None:
    assert offset_for(1, 8) == 0
    assert offset_for(3, 8) == 16
    assert offset_for(0, 8) == 0


def test_page_navigation_flags() -> None:
    page = Page(items=list(range(8)), total=20, number=2, per_page=8)
    assert page.pages == 3
    assert page.has_prev is True
    assert page.has_next is True
    assert page.first_index == 9
    assert page.label == "2/3"
    assert page.is_empty is False


def test_last_page_has_no_next() -> None:
    page = Page(items=[1, 2, 3, 4], total=20, number=3, per_page=8)
    assert page.has_next is False
    assert page.has_prev is True


def test_empty_page() -> None:
    page = Page()
    assert page.is_empty is True
    assert page.pages == 1
    assert page.label == "1/1"
    assert page.has_prev is False
    assert page.has_next is False
