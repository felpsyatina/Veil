"""Точка входа бота (long polling). Запускается командой `python -m app.bot.main`."""
from __future__ import annotations

import asyncio
import logging

from aiogram.types import ErrorEvent
from redis.asyncio import Redis

from app.bot.handlers import help_guide, payment, referral, start, subscription, support
from app.bot.handlers.admin import broadcast as admin_broadcast
from app.bot.handlers.admin import nodes as admin_nodes
from app.bot.handlers.admin import panel as admin_panel
from app.bot.handlers.admin import payments as admin_payments
from app.bot.handlers.admin import tariffs as admin_tariffs
from app.bot.handlers.admin import tickets as admin_tickets
from app.bot.handlers.admin import users as admin_users
from app.bot.loader import create_bot, create_dispatcher
from app.bot.middlewares.db_session import DbSessionMiddleware
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.middlewares.user_registration import UserContextMiddleware
from app.config import settings
from app.logging_conf import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    logger.info("Запуск бота...")

    bot = create_bot()
    dp = create_dispatcher()
    redis = Redis.from_url(settings.redis_url)

    # Порядок важен: троттлинг — самый внешний (не тратим ресурсы на
    # заблокированные апдейты), затем сессия БД, затем контекст пользователя
    # (которому сессия уже нужна).
    dp.update.outer_middleware(ThrottlingMiddleware(redis))
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(UserContextMiddleware())

    dp.include_router(start.router)
    dp.include_router(subscription.router)
    dp.include_router(payment.router)
    dp.include_router(referral.router)
    dp.include_router(help_guide.router)
    dp.include_router(support.router)
    dp.include_router(admin_panel.router)
    dp.include_router(admin_nodes.router)
    dp.include_router(admin_tariffs.router)
    dp.include_router(admin_users.router)
    dp.include_router(admin_payments.router)
    dp.include_router(admin_broadcast.router)
    dp.include_router(admin_tickets.router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        logger.exception("Необработанная ошибка при обработке апдейта", exc_info=event.exception)
        return True

    me = await bot.get_me()
    dp["bot_username"] = me.username
    logger.info("Бот запущен: @%s", me.username)

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
