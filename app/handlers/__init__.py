"""Роутеры личного диалога.

errors подключается отдельно в app/bot.py — он должен видеть всё,
а не только личные сообщения.
"""

from __future__ import annotations

from aiogram import Router

from app.handlers import admin, common, errors, export, history, menu, stats

#: Порядок важен: common разбирает всё, что не взяли остальные, поэтому он последний.
PRIVATE_ROUTERS: tuple[Router, ...] = (
    menu.router,
    history.router,
    stats.router,
    export.router,
    admin.router,
    common.router,
)

__all__ = [
    "PRIVATE_ROUTERS",
    "admin",
    "common",
    "errors",
    "export",
    "history",
    "menu",
    "stats",
]