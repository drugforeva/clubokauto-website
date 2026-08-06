"""Redis: FSM-хранилище и счётчики троттлинга.

URL вида memory:// поднимает fakeredis в памяти процесса — это режим
run_local.py и тестов, без установленного Redis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config import Settings

MEMORY_SCHEME = "memory://"


def build_redis(settings: Settings) -> Any:
    """Клиент Redis или его ин-мемори замена."""
    url = settings.redis_url
    if url.startswith(MEMORY_SCHEME):
        from fakeredis.aioredis import FakeRedis

        return FakeRedis()
    from redis.asyncio import Redis

    return Redis.from_url(url)


async def ping(redis: Any) -> bool:
    """Проверка живости — используется в админке (раздел «Нагрузка»)."""
    try:
        await redis.ping()
    except Exception:  # noqa: BLE001 - любая ошибка значит «нет связи»
        return False
    return True
