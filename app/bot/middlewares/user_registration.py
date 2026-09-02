"""
Получает/создаёт пользователя на каждый апдейт и кладёт его в data["user"].

Также разбирает диплинк /start ref_<код> для реферальной программы: если
это первое сообщение нового пользователя, реферер сохраняется сразу при
создании записи (см. app.services.users.get_or_create_user).

Забаненным пользователям дальше хендлеров ход не даётся.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot import texts
from app.services import users as users_service


class UserContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session = data["session"]

        referrer_code: str | None = None
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            parts = event.text.split(maxsplit=1)
            if len(parts) > 1 and parts[1].startswith("ref_"):
                referrer_code = parts[1][len("ref_") :].strip() or None

        user, created = await users_service.get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            referrer_code=referrer_code,
        )
        data["user"] = user
        data["user_created"] = created

        if user.is_banned:
            if isinstance(event, Message):
                await event.answer(texts.BANNED)
            elif isinstance(event, CallbackQuery):
                await event.answer(texts.BANNED, show_alert=True)
            return None

        return await handler(event, data)
