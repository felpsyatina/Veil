"""
Анти-флуд: не чаще одного действия за rate_limit секунд на пользователя.

Redis (а не in-memory кэш) — намеренно: так лимит переживает рестарт бота и
останется корректным, если бот когда-нибудь будет масштабирован на несколько
инстансов.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from redis.asyncio import Redis


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, rate_limit_sec: float = 0.6) -> None:
        self._redis = redis
        self._rate_limit_ms = int(rate_limit_sec * 1000)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            key = f"throttle:{user.id}"
            allowed = await self._redis.set(key, "1", nx=True, px=self._rate_limit_ms)
            if not allowed:
                if isinstance(event, CallbackQuery):
                    await event.answer()
                return None
        return await handler(event, data)
