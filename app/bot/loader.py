"""Инициализация Bot/Dispatcher. Вынесено отдельно, чтобы worker мог
переиспользовать тот же Bot для отправки уведомлений, не поднимая диспетчер."""
from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from app.config import settings


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    storage = RedisStorage.from_url(settings.redis_url)
    return Dispatcher(storage=storage)
