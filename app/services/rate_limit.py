"""Счётчик "N действий за окно времени" на Redis — для антифрод-лимитов."""
from __future__ import annotations

from redis.asyncio import Redis


async def check_rate_limit(redis: Redis, key: str, limit: int, window_sec: int) -> bool:
    """True, если действие разрешено (лимит ещё не превышен за текущее окно)."""
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_sec)
    return current <= limit
