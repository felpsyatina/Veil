"""Фильтр доступа к админ-хендлерам — по списку ADMIN_IDS из .env."""
from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from app.config import settings


class IsAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and user.id in settings.admin_ids
