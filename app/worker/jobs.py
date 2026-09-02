"""
Фоновые задачи, запускаемые планировщиком (см. app/worker/main.py).

Каждая задача открывает свою короткую сессию БД и не держит транзакцию
открытой во время медленных сетевых вызовов (к нодам/Telegram) — это чтобы
не блокировать пул соединений Postgres на время, пока мы ждём ответ от
внешнего сервиса.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import gzip
import logging
import os

from aiogram import Bot

from app.bot import texts
from app.config import settings
from app.db.base import get_session
from app.services import nodes as nodes_service
from app.services import payments as payments_service
from app.services import provisioning as provisioning_service
from app.services import subscriptions as subscriptions_service
from app.services import users as users_service

logger = logging.getLogger(__name__)


async def _notify_admins(bot: Bot, text: str) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось уведомить админа %s: %s", admin_id, exc)


async def check_nodes_health(bot: Bot) -> None:
    async with get_session() as session:
        server_ids = [(s.id, s.is_healthy) for s in await nodes_service.list_servers(session)]

    for server_id, was_healthy in server_ids:
        async with get_session() as session:
            server = await nodes_service.get_server(session, server_id)
            if server is None:
                continue
            healthy, error = await nodes_service.check_node_health(server)
            await nodes_service.set_health(session, server, healthy=healthy, error=error)
            name = server.name

        if was_healthy and not healthy:
            await _notify_admins(bot, texts.admin_node_down_alert(server, error))
        elif not was_healthy and healthy:
            await _notify_admins(bot, texts.admin_node_up_alert(server))
        logger.info("Health-check %s: healthy=%s", name, healthy)


async def notify_expiring_subscriptions(bot: Bot) -> None:
    thresholds = sorted(set(settings.notify_before_days), reverse=True)
    async with get_session() as session:
        for days in thresholds:
            subs = await subscriptions_service.list_expiring_between(
                session, from_days=days - 1, to_days=days
            )
            for sub in subs:
                if subscriptions_service.has_notified(sub, days):
                    continue
                user = await users_service.get_by_id(session, sub.user_id)
                if user is None:
                    continue
                try:
                    await bot.send_message(user.telegram_id, texts.notify_expiring(sub, days))
                except Exception as exc:  # noqa: BLE001 — пользователь мог заблокировать бота
                    logger.info("Не удалось отправить напоминание %s: %s", user.telegram_id, exc)
                await subscriptions_service.record_notification(session, sub, days)


async def expire_subscriptions(bot: Bot) -> None:
    async with get_session() as session:
        subs = await subscriptions_service.list_newly_expired(session)
        for sub in subs:
            was_trial = sub.status.value == "trial"
            already_notified = sub.notified_expired
            user = await users_service.get_by_id(session, sub.user_id)
            await subscriptions_service.mark_expired(session, sub)

            if user is None:
                continue
            await provisioning_service.revoke_subscription_everywhere(session, sub, user.telegram_id)

            if not already_notified:
                text = texts.NOTIFY_TRIAL_EXPIRED if was_trial else texts.NOTIFY_EXPIRED
                try:
                    await bot.send_message(user.telegram_id, text)
                except Exception as exc:  # noqa: BLE001
                    logger.info("Не удалось уведомить об истечении %s: %s", user.telegram_id, exc)
                await subscriptions_service.record_expired_notification(session, sub)


async def reconcile_provisioning(bot: Bot) -> None:
    """Повторяет синхронизацию там, где предыдущая попытка провалилась
    (SubscriptionServer.last_error не пуст) — сеть могла временно моргнуть."""
    async with get_session() as session:
        for sub in await subscriptions_service.list_active_and_trial(session):
            links = await provisioning_service.list_links_for_subscription(session, sub.id)
            if not any(link.last_error for link in links):
                continue
            user = await users_service.get_by_id(session, sub.user_id)
            if user is not None:
                await provisioning_service.sync_subscription_everywhere(session, sub, user.telegram_id)


async def reconcile_pending_payments(bot: Bot) -> None:
    """Подстраховка на случай недоставленного вебхука — переспрашивает
    провайдера напрямую по зависшим платежам."""
    async with get_session() as session:
        for payment in await payments_service.list_stale_pending_payments(session, older_than_minutes=20):
            try:
                await payments_service.check_and_process_payment(session, payment.id)
            except Exception as exc:  # noqa: BLE001 — одна ошибка не должна прерывать сверку остальных
                logger.warning("Сверка платежа #%s не удалась: %s", payment.id, exc)


async def backup_database() -> None:
    """pg_dump → gzip → BACKUP_DIR, с ротацией по BACKUP_RETENTION_DAYS.

    ⚠️ Это резервная копия НАШЕЙ БД (пользователи/подписки/платежи), а не
    самих 3x-ui нод. Bce параметры Reality нужные для восстановления доступа
    (публичный ключ, short-id, dest и т.д.) уже задублированы в таблице
    servers, так что при потере ноды инбаунд можно пересоздать по этим
    данным — но саму ноду (её собственную БД) стоит бэкапить отдельно,
    см. README → «Резервные копии».
    """
    os.makedirs(settings.backup_dir, exist_ok=True)
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(settings.backup_dir, f"vpnshop_{timestamp}.sql.gz")

    env = os.environ.copy()
    env["PGPASSWORD"] = settings.postgres_password
    cmd = [
        "pg_dump",
        "-h", settings.postgres_host,
        "-p", str(settings.postgres_port),
        "-U", settings.postgres_user,
        "-d", settings.postgres_db,
        "--no-owner",
        "--no-privileges",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("pg_dump завершился с ошибкой: %s", stderr.decode(errors="replace")[:2000])
        return

    with gzip.open(filename, "wb") as f:
        f.write(stdout)
    logger.info("Бэкап БД сохранён: %s (%d байт)", filename, len(stdout))

    _rotate_backups()


def _rotate_backups() -> None:
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=settings.backup_retention_days)
    for fname in os.listdir(settings.backup_dir):
        if not (fname.startswith("vpnshop_") and fname.endswith(".sql.gz")):
            continue
        path = os.path.join(settings.backup_dir, fname)
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(path), tz=dt.UTC)
        if mtime < cutoff:
            os.remove(path)
            logger.info("Удалён старый бэкап: %s", fname)
