"""Проверка подписки на канал перед доступом к боту."""
from __future__ import annotations
import time
from collections.abc import Awaitable, Callable
from typing import Any
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, TelegramObject

REQUIRED_CHANNEL = "@sohranobot"
CHANNEL_URL = "https://t.me/sohranobot"
CACHE_TTL = 60

SUBSCRIBE_TEXT = (
    "\U0001f512 <b>\u0414\u043e\u0441\u0442\u0443\u043f \u0437\u0430\u043a\u0440\u044b\u0442</b>\n\n"
    "\u0427\u0442\u043e\u0431\u044b \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c\u0441\u044f \u0431\u043e\u0442\u043e\u043c, \u043f\u043e\u0434\u043f\u0438\u0448\u0438\u0442\u0435\u0441\u044c \u043d\u0430 \u043a\u0430\u043d\u0430\u043b:\n"
    "https://t.me/sohranobot\n\n"
    "\u041f\u043e\u0441\u043b\u0435 \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443 \u043d\u0438\u0436\u0435."
)

SUBSCRIBE_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(
            text="\U0001f4e2 \u041f\u043e\u0434\u043f\u0438\u0441\u0430\u0442\u044c\u0441\u044f",
            url=CHANNEL_URL,
        )],
        [InlineKeyboardButton(
            text="\u2705 \u042f \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043b\u0441\u044f(\u0430\u0441\u044c)",
            callback_data="check_sub",
        )],
    ]
)

_cache: dict[int, tuple[bool, float]] = {}


async def _is_subscribed(bot: Any, user_id: int) -> bool:
    now = time.monotonic()
    cached = _cache.get(user_id)
    if cached and now - cached[1] < CACHE_TTL:
        return cached[0]
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        ok = member.status not in ("left", "kicked", "banned")
    except TelegramAPIError:
        ok = True
    _cache[user_id] = (ok, now)
    return ok


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = data.get("event_from_user")
        if from_user is None or getattr(from_user, "is_bot", False):
            return await handler(event, data)
        bot = data.get("bot")
        if bot is None:
            return await handler(event, data)
        user_id = int(from_user.id)
        cb_data = getattr(event, "data", None)
        if cb_data == "check_sub":
            _cache.pop(user_id, None)
        if await _is_subscribed(bot, user_id):
            return await handler(event, data)
        try:
            if cb_data is not None:
                await event.answer(
                    "\u0412\u044b \u0435\u0449\u0451 \u043d\u0435 \u043f\u043e\u0434\u043f\u0438\u0441\u0430\u043d\u044b \u274c",
                    show_alert=True
                )
                msg = getattr(event, "message", None)
                if msg:
                    await msg.edit_text(SUBSCRIBE_TEXT, reply_markup=SUBSCRIBE_KB)
            else:
                msg = getattr(event, "message", None) or event
                answer = getattr(msg, "answer", None)
                if answer:
                    await answer(SUBSCRIBE_TEXT, reply_markup=SUBSCRIBE_KB)
        except TelegramAPIError:
            pass
        return None
