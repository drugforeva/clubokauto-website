"""Админская рассылка.

Телеграм бьёт по рукам за быструю отправку, поэтому между сообщениями есть пауза,
а пользователи, заблокировавшие бота, помечаются и больше не беспокоятся.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.repositories.uow import UnitOfWork
    from app.services.notifier import NotificationService

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class BroadcastReport:
    sent: int = 0
    failed: int = 0
    blocked: int = 0

    @property
    def total(self) -> int:
        return self.sent + self.failed + self.blocked


class BroadcastService:
    def __init__(self, notifier: NotificationService, delay: float = 0.05) -> None:
        self.notifier = notifier
        self.delay = delay

    async def run(self, uow: UnitOfWork, *, text: str) -> BroadcastReport:
        report = BroadcastReport()
        recipients = await uow.users.all_recipients()
        for user in recipients:
            result = await self.notifier.send(user.telegram_id, text)
            if result.blocked:
                await uow.users.mark_blocked(user.id)
                report.blocked += 1
            elif result.ok:
                report.sent += 1
            else:
                report.failed += 1
            await asyncio.sleep(self.delay)
        await uow.commit()
        logger.info(
            "broadcast.done",
            sent=report.sent,
            failed=report.failed,
            blocked=report.blocked,
        )
        return report
