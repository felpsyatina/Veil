"""
Сборка содержимого subscription-ссылки и автоматический выбор сервера.

Почему это отдельный сервис, а не функция внутри 3x-ui: у самой панели 3x-ui
есть собственный механизм subscription (per-node), но он отдаёт конфиги только
клиентов ОДНОЙ ноды. Чтобы в одной подписке был список из нескольких разных
серверов (то, что просили в ТЗ), агрегацию нужно делать на нашей стороне —
собирая по одной vless-ссылке с каждой ноды, где у подписки есть клиент.

Нездоровые (Server.is_healthy=False) и выключенные (is_active=False) ноды
автоматически выпадают из выдачи — им ничего дополнительно "отключать" на
уровне XUI не нужно (см. app/services/provisioning.py про отдельный кейс
реальной деактивации ноды администратором).
"""
from __future__ import annotations

import base64

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Server, Subscription, SubscriptionServer
from app.services import nodes as nodes_service
from app.xui.reality import build_vless_reality_link


async def list_selectable_servers(
    session: AsyncSession, subscription: Subscription
) -> list[Server]:
    """Активные, здоровые ноды, на которых у подписки реально создан клиент."""
    stmt = (
        select(Server)
        .join(SubscriptionServer, SubscriptionServer.server_id == Server.id)
        .where(
            SubscriptionServer.subscription_id == subscription.id,
            SubscriptionServer.is_provisioned.is_(True),
            Server.is_active.is_(True),
            Server.is_healthy.is_(True),
        )
        .order_by(Server.sort_order, Server.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def build_server_link(server: Server, subscription: Subscription) -> str:
    short_id = (server.reality_short_ids or "").split(",")[0]
    server_name = (server.reality_server_names or "").split(",")[0]
    return build_vless_reality_link(
        uuid=subscription.xui_uuid,
        host=server.host,
        port=server.port,
        public_key=server.reality_public_key or "",
        short_id=short_id,
        server_name=server_name,
        fingerprint=server.reality_fingerprint or "chrome",
        remark=server.name,
    )


async def build_subscription_content(session: AsyncSession, subscription: Subscription) -> str:
    """Base64 список vless://-ссылок — то, что отдаёт GET /sub/{token}."""
    servers = await list_selectable_servers(session, subscription)
    links = [build_server_link(s, subscription) for s in servers]
    raw = "\n".join(links)
    return base64.b64encode(raw.encode()).decode()


async def pick_auto_server(session: AsyncSession, subscription: Subscription) -> Server | None:
    """Выбирает наименее загруженный из доступных подписке серверов —
    используется кнопкой «Автовыбор» в разделе «Моя подписка»."""
    servers = await list_selectable_servers(session, subscription)
    if not servers:
        return None
    loads = {s.id: await nodes_service.get_client_count(session, s.id) for s in servers}
    return min(servers, key=lambda s: loads[s.id])
