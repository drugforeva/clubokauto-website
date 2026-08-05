"""Роутеры личного диалога с владельцем.

Порядок в PRIVATE_ROUTERS важен: меню идёт первым, админка — последней,
чтобы её фильтр не перехватывал обычные сценарии.
"""

from app.handlers import (
    admin,
    errors,
    export,
    history,
    menu,
    search,
    settings,
    stats,
)

PRIVATE_ROUTERS = (
    menu.router,
    history.router,
    stats.router,
    export.router,
    admin.router,
)

__all__ = [
    "PRIVATE_ROUTERS",
    "admin",
    "errors",
    "export",
    "history",
    "menu",
    "search",
    "settings",
    "stats",
]
