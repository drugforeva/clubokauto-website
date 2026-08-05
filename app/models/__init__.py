"""Импорт всех моделей в одном месте.

Строковые аннотации связей SQLAlchemy разрешает только после того, как все
классы зарегистрированы, поэтому импортируем всё здесь. Этот же модуль
импортирует migrations/env.py, чтобы Base.metadata была полной.
"""

from app.database.base import Base
from app.models.business_connection import BusinessConnection
from app.models.chat import Chat
from app.models.deleted_message import DeletedMessage
from app.models.edit import MessageEdit
from app.models.media import Media
from app.models.message import Message
from app.models.settings import UserSettings
from app.models.user import User

__all__ = [
    "Base",
    "BusinessConnection",
    "Chat",
    "DeletedMessage",
    "Media",
    "Message",
    "MessageEdit",
    "User",
    "UserSettings",
]
