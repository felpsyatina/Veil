"""Точка входа воркера. Запускается командой `python -m app.worker.main`."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.loader import create_bot
from app.config import settings
from app.logging_conf import setup_logging
from app.worker import jobs

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    logger.info("Запуск воркера...")

    bot = create_bot()
    scheduler = AsyncIOScheduler(timezone=settings.tz)

    scheduler.add_job(
        jobs.check_nodes_health, "interval", minutes=5, args=[bot],
        id="check_nodes_health", max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        jobs.notify_expiring_subscriptions, "interval", hours=6, args=[bot],
        id="notify_expiring_subscriptions", max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        jobs.expire_subscriptions, "interval", minutes=15, args=[bot],
        id="expire_subscriptions", max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        jobs.reconcile_provisioning, "interval", minutes=30, args=[bot],
        id="reconcile_provisioning", max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        jobs.reconcile_pending_payments, "interval", minutes=10, args=[bot],
        id="reconcile_pending_payments", max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        jobs.backup_database, "cron", hour=settings.backup_hour, minute=0,
        id="backup_database", max_instances=1, coalesce=True,
    )

    scheduler.start()
    logger.info("Воркер запущен, задачи по расписанию активны")

    try:
        await asyncio.Event().wait()  # держим процесс живым
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
