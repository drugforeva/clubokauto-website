"""FSM-состояния диалогов с владельцем.

Состояния живут в Redis (или в памяти при REDIS_URL=memory://), поэтому после
рестарта бота начатый ввод не теряется.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """Админские сценарии."""

    waiting_broadcast = State()
    waiting_user_query = State()
