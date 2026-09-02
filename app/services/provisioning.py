"""
Синхронизация состояния подписок с реальными VLESS-клиентами на нодах.

Это единственное место, где бизнес-логика подписок (app/services/subscriptions.py)
встречается с API нод (app/services/nodes.py + app/xui/client.py). Все функции
терпимы к сбоям отдельных нод: ошибка на одной ноде не прерывает синхронизацию
остальных, а фиксируется в SubscriptionServer.last_error для повторной попытки
на следующем цикле воркера (см. app/worker/jobs.py::reconcile_provisioning).
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import SubscriptionStatus
from app.db.models import Server, Subscription, SubscriptionServer
from app.services import nodes as nodes_service
from app.services import users as users_service
from app.services.subscriptions import list_active_and_trial
from app.xui.client import XUIClient, XUIClientConfig, expiry_ms_from_datetime

logger = logging.getLogger(__name__)


async def list_links_for_subscription(
    session: AsyncSession, subscription_id: int
) -> list[SubscriptionServer]:
    result = await session.execute(
        select(SubscriptionServer).where(SubscriptionServer.subscription_id == subscription_id)
    )
    return list(result.scalars().all())


async def _get_or_create_link(
    session: AsyncSession, subscription_id: int, server_id: int
) -> SubscriptionServer:
    result = await session.execute(
        select(SubscriptionServer).where(
            SubscriptionServer.subscription_id == subscription_id,
            SubscriptionServer.server_id == server_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        link = SubscriptionServer(
            subscription_id=subscription_id, server_id=server_id, is_provisioned=False
        )
        session.add(link)
        await session.flush()
    return link


async def _apply_client_state(
    session: AsyncSession,
    subscription: Subscription,
    server: Server,
    telegram_id: int,
    *,
    enable: bool,
) -> None:
    link = await _get_or_create_link(session, subscription.id, server.id)
    client_cfg = XUIClientConfig(
        id=subscription.xui_uuid,
        email=subscription.xui_email,
        limit_ip=subscription.device_limit,
        expiry_time_ms=expiry_ms_from_datetime(subscription.expires_at),
        enable=enable,
        tg_id=str(telegram_id),
        sub_id=subscription.subscription_token,
        comment=f"sub#{subscription.id}",
    )
    try:
        async with XUIClient(
            server.panel_url, server.panel_username, nodes_service.decrypt_panel_password(server)
        ) as xui:
            if link.is_provisioned:
                await xui.update_client(server.inbound_id, client_cfg)
            else:
                await xui.add_client(server.inbound_id, client_cfg)
                link.is_provisioned = True
        link.last_error = None
    except Exception as exc:  # noqa: BLE001 — сбой одной ноды не должен ронять остальные
        link.last_error = str(exc)[:500]
        logger.warning(
            "Не удалось синхронизировать sub#%s на ноде %s: %s", subscription.id, server.name, exc
        )
    await session.flush()


async def provision_on_server(
    session: AsyncSession, subscription: Subscription, server: Server, telegram_id: int
) -> None:
    desired_enable = subscription.status in (
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIAL,
    )
    await _apply_client_state(session, subscription, server, telegram_id, enable=desired_enable)


async def disable_on_server(
    session: AsyncSession, subscription: Subscription, server: Server, telegram_id: int
) -> None:
    await _apply_client_state(session, subscription, server, telegram_id, enable=False)


async def provision_on_all_active_servers(
    session: AsyncSession, subscription: Subscription, telegram_id: int
) -> None:
    for server in await nodes_service.list_servers(session, only_active=True):
        await provision_on_server(session, subscription, server, telegram_id)


async def provision_new_node_for_existing_subscriptions(
    session: AsyncSession, server: Server
) -> int:
    """Вызывается сразу после добавления новой ноды — раздаёт её всем, у кого
    сейчас есть доступ. Возвращает число обработанных подписок."""
    count = 0
    for sub in await list_active_and_trial(session):
        user = await users_service.get_by_id(session, sub.user_id)
        if user is not None:
            await provision_on_server(session, sub, server, user.telegram_id)
            count += 1
    return count


async def sync_subscription_everywhere(
    session: AsyncSession, subscription: Subscription, telegram_id: int
) -> None:
    """Приводит клиента подписки в соответствие с её текущим статусом на всех
    нодах: обновляет enable/expiry там, где клиент уже есть, отключает на
    деактивированных нодах и добавляет на новых активных нодах, если статус
    подписки активный/пробный.
    """
    existing_links = await list_links_for_subscription(session, subscription.id)
    linked_server_ids = {link.server_id for link in existing_links}
    all_servers = {s.id: s for s in await nodes_service.list_servers(session)}

    for link in existing_links:
        server = all_servers.get(link.server_id)
        if server is None:
            continue
        if server.is_active:
            await provision_on_server(session, subscription, server, telegram_id)
        elif link.is_provisioned:
            await disable_on_server(session, subscription, server, telegram_id)

    if subscription.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL):
        for server in all_servers.values():
            if server.is_active and server.id not in linked_server_ids:
                await provision_on_server(session, subscription, server, telegram_id)


async def revoke_subscription_everywhere(
    session: AsyncSession, subscription: Subscription, telegram_id: int
) -> None:
    for link in await list_links_for_subscription(session, subscription.id):
        if not link.is_provisioned:
            continue
        server = await nodes_service.get_server(session, link.server_id)
        if server is not None:
            await disable_on_server(session, subscription, server, telegram_id)
