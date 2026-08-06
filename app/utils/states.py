"""FSM-состояния диалогов с владельцем.

Состояния живут в Redis (или в памяти при REDIS_URL=memory://), поэтому после
рестарта бота начатый поиск не теряется.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    """Пошаговое уточнение поискового запроса."""

    waiting_query = State()
    waiting_sender = State()
    waiting_date_from = State()
    waiting_date_to = State()


class SettingsStates(StatesGroup):
    """Ввод значений в настройках."""

    waiting_timezone = State()


class AdminStates(StatesGroup):
    """Админские сценарии."""

    waiting_broadcast = State()
    waiting_user_query = State()
