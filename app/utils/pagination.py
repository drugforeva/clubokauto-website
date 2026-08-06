"""Постраничный вывод для инлайн-клавиатур.

Страницы нумеруются с 1: число из callback_data показывается человеку как есть.
Все границы проверяет normalize_page: нажатая старая кнопка может принести
номер страницы, которой уже не существует.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")

DEFAULT_PER_PAGE = 8


def total_pages(total: int, per_page: int = DEFAULT_PER_PAGE) -> int:
    """Сколько всего страниц. Пустой список — всё равно одна страница."""
    per_page = max(int(per_page), 1)
    if total <= 0:
        return 1
    return (int(total) + per_page - 1) // per_page


def normalize_page(page: int, total: int, per_page: int = DEFAULT_PER_PAGE) -> int:
    """Зажать номер страницы в допустимые границы."""
    pages = total_pages(total, per_page)
    try:
        current = int(page)
    except (TypeError, ValueError):
        current = 1
    return min(max(current, 1), pages)


def offset_for(page: int, per_page: int = DEFAULT_PER_PAGE) -> int:
    """OFFSET для SQL по номеру страницы."""
    return max(int(page) - 1, 0) * max(int(per_page), 1)


@dataclass(slots=True)
class Page(Generic[T]):
    """Готовая страница для рендера списка и клавиатуры."""

    items: list[T] = field(default_factory=list)
    total: int = 0
    number: int = 1
    per_page: int = DEFAULT_PER_PAGE

    @property
    def pages(self) -> int:
        return total_pages(self.total, self.per_page)

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def has_prev(self) -> bool:
        return self.number > 1

    @property
    def has_next(self) -> bool:
        return self.number < self.pages

    @property
    def first_index(self) -> int:
        """Номер первого элемента страницы для нумерованного списка."""
        return offset_for(self.number, self.per_page) + 1

    @property
    def label(self) -> str:
        return f"{self.number}/{self.pages}"
