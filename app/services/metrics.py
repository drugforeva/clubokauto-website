"""Простейшие счётчики в памяти для /admin.

Не замена Prometheus, а способ быстро понять, жив ли бот и не сыпется ли он.
Сбрасывается при рестарте — это осознанное упрощение.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any


class Metrics:
    def __init__(self) -> None:
        self._started = time.monotonic()
        self._counters: Counter[str] = Counter()

    def record_update(self, kind: str = "update") -> None:
        self._counters["updates"] += 1
        self._counters[f"update:{kind}"] += 1

    def record_capture(self, kind: str) -> None:
        self._counters[f"capture:{kind}"] += 1

    def record_error(self, kind: str = "unknown") -> None:
        self._counters["errors"] += 1
        self._counters[f"error:{kind}"] += 1

    @property
    def uptime_seconds(self) -> int:
        return int(time.monotonic() - self._started)

    def snapshot(self) -> dict[str, Any]:
        return {
            "uptime_seconds": self.uptime_seconds,
            "updates": self._counters.get("updates", 0),
            "errors": self._counters.get("errors", 0),
            "counters": dict(self._counters),
        }
