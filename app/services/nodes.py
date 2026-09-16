"""
Сервис нод (VPN-серверов).

Разделение ответственности:
- provision_node_inbound() — разовая настройка Reality-инбаунда на панели
  новой ноды (вызывается один раз при добавлении сервера).
- create_server() / list_servers() / ... — CRUD записи Server в нашей БД.
- Добавление/удаление VLESS-клиентов конкретных подписок на нодах —
  в app/services/provisioning.py, а не здесь.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Server, SubscriptionServer
from app.utils.security import decrypt_secret, encrypt_secret
from app.xui.client import XUIClient
from app.xui.reality import generate_short_id, generate_x25519_keypair


@dataclass
class NodeProvisionResult:
    inbound_id: int
    private_key: str
    public_key: str
    short_ids: list[str]
    server_names: list[str]
    dest: str
    fingerprint: str


async def provision_node_inbound(
    *,
    panel_url: str,
    panel_username: str = "",
    panel_password: str = "",
    api_token: str | None = None,
    remark: str,
    xray_port: int,
    dest: str | None = None,
    server_names: list[str] | None = None,
    fingerprint: str | None = None,
) -> NodeProvisionResult:
    """Логинится на панель ноды (по api_token, если задан, иначе по
    username/password) и создаёт пустой VLESS+Reality инбаунд.

    Ключи Reality генерируются локально (см. app.xui.reality) — панели
    нужны только для того, чтобы прописать их в конфиг Xray.
    """
    private_key, public_key = generate_x25519_keypair()
    short_id = generate_short_id()
    dest = dest or settings.reality_dest
    server_names = server_names or settings.reality_server_names_list
    fingerprint = fingerprint or settings.reality_fingerprint

    async with XUIClient(panel_url, panel_username, panel_password, api_token=api_token) as xui:
        result = await xui.create_reality_inbound(
            remark=remark,
            port=xray_port,
            private_key=private_key,
            public_key=public_key,
            short_ids=[short_id],
            server_names=server_names,
            dest=dest,
            fingerprint=fingerprint,
        )

    return NodeProvisionResult(
        inbound_id=result.inbound_id,
        private_key=private_key,
        public_key=public_key,
        short_ids=[short_id],
        server_names=server_names,
        dest=dest,
        fingerprint=fingerprint,
    )


async def create_server(
    session: AsyncSession,
    *,
    name: str,
    country_code: str | None,
    host: str,
    port: int,
    panel_url: str,
    panel_username: str = "",
    panel_password: str = "",
    api_token: str | None = None,
    provision: NodeProvisionResult,
    sort_order: int = 0,
) -> Server:
    server = Server(
        name=name,
        country_code=country_code,
        host=host,
        port=port,
        panel_url=panel_url,
        panel_username=panel_username,
        panel_password_encrypted=encrypt_secret(panel_password),
        api_token_encrypted=encrypt_secret(api_token) if api_token else None,
        inbound_id=provision.inbound_id,
        reality_public_key=provision.public_key,
        reality_private_key_encrypted=encrypt_secret(provision.private_key),
        reality_short_ids=",".join(provision.short_ids),
        reality_server_names=",".join(provision.server_names),
        reality_dest=provision.dest,
        reality_fingerprint=provision.fingerprint,
        sort_order=sort_order,
    )
    session.add(server)
    await session.flush()
    return server


async def get_server(session: AsyncSession, server_id: int) -> Server | None:
    return await session.get(Server, server_id)


async def list_servers(
    session: AsyncSession, *, only_active: bool = False, only_selectable: bool = False
) -> list[Server]:
    """only_selectable — активные И здоровые (то, что реально можно предлагать пользователю)."""
    stmt = select(Server).order_by(Server.sort_order, Server.id)
    if only_selectable:
        stmt = stmt.where(Server.is_active.is_(True), Server.is_healthy.is_(True))
    elif only_active:
        stmt = stmt.where(Server.is_active.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def set_active(session: AsyncSession, server: Server, active: bool) -> None:
    server.is_active = active
    await session.flush()


async def set_health(
    session: AsyncSession, server: Server, *, healthy: bool, error: str | None = None
) -> None:
    server.is_healthy = healthy
    server.last_error = error
    server.last_check_at = dt.datetime.now(dt.UTC)
    await session.flush()


async def delete_server(session: AsyncSession, server: Server) -> None:
    await session.delete(server)
    await session.flush()


async def get_client_count(session: AsyncSession, server_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(SubscriptionServer)
        .where(SubscriptionServer.server_id == server_id, SubscriptionServer.is_provisioned.is_(True))
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


def decrypt_panel_password(server: Server) -> str:
    if not server.panel_password_encrypted:
        return ""
    return decrypt_secret(server.panel_password_encrypted)


def decrypt_api_token(server: Server) -> str | None:
    if not server.api_token_encrypted:
        return None
    return decrypt_secret(server.api_token_encrypted)


async def check_node_health(server: Server) -> tuple[bool, str | None]:
    """Пингует панель ноды (по токену, если есть, иначе логином). Возвращает (healthy, текст_ошибки)."""
    try:
        async with XUIClient(
            server.panel_url,
            server.panel_username,
            decrypt_panel_password(server),
            api_token=decrypt_api_token(server),
        ) as xui:
            ok = await xui.health_check()
        return ok, None if ok else "Не удалось подключиться к панели"
    except Exception as exc:  # noqa: BLE001 — health-check не должен ронять воркер
        return False, str(exc)[:500]
