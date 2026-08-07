"""Гейт обязательной подписки на канал.

Middleware решает ровно один вопрос: пускать человека дальше или нет.
Приветствие и гайд по подключению живут в app/handlers/menu.py.

Канал берётся из настроек. Пустое REQUIRED_CHANNEL полностью выключает
проверку — бот работает для всех. Раньше здесь был зашит юзернейм самого
бота вместо канала, и проверка не работала вообще.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)

from app.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)

#: Сколько секунд доверять прошлой проверке.
CACHE_TTL = 60.0

#: Потолок кэша — иначе он растёт всю жизнь процесса.
MAX_CACHED_USERS = 10_000

#: Статусы, при которых человек каналу не принадлежит.
NOT_MEMBER = ("left", "kicked", "banned")

#: callback_data кнопки «Я подписался».
CHECK_CALLBACK = "check_sub"


def subscribe_text(channel_link: str) -> str:
    """Текст экрана с требованием подписки."""
    link_line = channel_link + "\n\n" if channel_link else ""
    return (
        "\U0001f512 <b>Нужна подписка на канал</b>\n\n"
        + link_line
        + "Подпишитесь и нажмите «Я подписался» — сразу пришлю инструкцию "
        "по подключению бота."
    )


def subscribe_keyboard(channel_link: str) -> InlineKeyboardMarkup:
    """Кнопка на канал появляется, только если ссылка известна."""
    rows: list[list[InlineKeyboardButton]] = []
    if channel_link:
        rows.append(
            [InlineKeyboardButton(text="\U0001f4e2 Подписаться", url=channel_link)]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="\u2705 Я подписался", callback_data=CHECK_CALLBACK
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


class SubscriptionMiddleware(BaseMiddleware):
    """Пускает дальше только подписчиков канала."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._cache: OrderedDict[int, tuple[float, bool]] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self.settings.subscription_enabled

    def _remember(self, user_id: int, ok: bool) -> None:
        self._cache[user_id] = (time.monotonic(), ok)
        self._cache.move_to_end(user_id)
        while len(self._cache) > MAX_CACHED_USERS:
            self._cache.popitem(last=False)

    async def _is_subscribed(self, bot: Any, user_id: int, force: bool = False) -> bool:
        """Проверить подписку. force — для кнопки «Я подписался»."""
        if not force:
            cached = self._cache.get(user_id)
            if cached is not None and time.monotonic() - cached[0] < CACHE_TTL:
                return cached[1]
        if bot is None:
            return True
        try:
            member = await bot.get_chat_member(self.settings.required_channel, user_id)
        except TelegramAPIError as error:
            # Чаще всего это наша ошибка настройки: неверный канал или бот
            # не админ. Наказывать за это пользователя нельзя, но и молчать — тоже.
            logger.warning(
                "subscription.check_failed",
                user_id=user_id,
                channel=self.settings.required_channel,
                error=str(error),
            )
            return True
        status = getattr(member, "status", "")
        status = getattr(status, "value", status)
        ok = str(status) not in NOT_MEMBER
        self._remember(user_id, ok)
        return ok

    async def _prompt(self, event: TelegramObject, is_check: bool) -> None:
        """Показать экран подписки."""
        text = subscribe_text(self.settings.channel_link)
        keyboard = subscribe_keyboard(self.settings.channel_link)
        try:
            if isinstance(event, CallbackQuery):
                if is_check:
                    await event.answer(
                        "Подписки пока не вижу. Попробуйте ещё раз.", show_alert=True
                    )
                    return
                await event.answer()
                if event.message is not None:
                    await event.message.answer(text, reply_markup=keyboard)
            elif isinstance(event, Message):
                await event.answer(text, reply_markup=keyboard)
        except TelegramAPIError as error:
            logger.info("subscription.prompt_failed", error=str(error))

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.enabled:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        bot = data.get("bot") or getattr(event, "bot", None)
        is_check = isinstance(event, CallbackQuery) and event.data == CHECK_CALLBACK

        # Нажатие «Я подписался» всегда идёт мимо кэша: иначе человек
        # будет ждать минуту после того, как уже подписался.
        if await self._is_subscribed(bot, user.id, force=is_check):
            return await handler(event, data)

        await self._prompt(event, is_check)
        return None
