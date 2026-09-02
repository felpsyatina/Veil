"""Агрегированная статистика для админ-панели бота (раздел «Аналитика»)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import PaymentStatus, SubscriptionStatus, TicketStatus
from app.db.models import Payment, Server, SupportTicket, Subscription, User


@dataclass
class DashboardStats:
    total_users: int
    banned_users: int
    active_subscriptions: int
    trial_subscriptions: int
    new_users_today: int
    revenue_today: Decimal
    revenue_week: Decimal
    revenue_month: Decimal
    revenue_total: Decimal
    payments_today: int
    open_tickets: int
    servers_total: int
    servers_healthy: int


async def _cash_revenue_since(session: AsyncSession, since: dt.datetime | None) -> Decimal:
    stmt = select(func.coalesce(func.sum(Payment.amount - Payment.applied_balance), 0)).where(
        Payment.status == PaymentStatus.SUCCEEDED
    )
    if since is not None:
        stmt = stmt.where(Payment.created_at >= since)
    result = await session.execute(stmt)
    value = result.scalar_one()
    return Decimal(value) if value is not None else Decimal("0")


async def get_dashboard_stats(session: AsyncSession) -> DashboardStats:
    now = dt.datetime.now(dt.UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - dt.timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    total_users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    banned_users = (
        await session.execute(select(func.count()).select_from(User).where(User.is_banned.is_(True)))
    ).scalar_one()
    new_users_today = (
        await session.execute(
            select(func.count()).select_from(User).where(User.created_at >= today_start)
        )
    ).scalar_one()

    active_subs = (
        await session.execute(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.status == SubscriptionStatus.ACTIVE)
        )
    ).scalar_one()
    trial_subs = (
        await session.execute(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.status == SubscriptionStatus.TRIAL)
        )
    ).scalar_one()

    payments_today = (
        await session.execute(
            select(func.count())
            .select_from(Payment)
            .where(Payment.status == PaymentStatus.SUCCEEDED, Payment.created_at >= today_start)
        )
    ).scalar_one()

    open_tickets = (
        await session.execute(
            select(func.count())
            .select_from(SupportTicket)
            .where(SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.ANSWERED]))
        )
    ).scalar_one()

    servers_total = (await session.execute(select(func.count()).select_from(Server))).scalar_one()
    servers_healthy = (
        await session.execute(
            select(func.count())
            .select_from(Server)
            .where(Server.is_active.is_(True), Server.is_healthy.is_(True))
        )
    ).scalar_one()

    return DashboardStats(
        total_users=total_users,
        banned_users=banned_users,
        active_subscriptions=active_subs,
        trial_subscriptions=trial_subs,
        new_users_today=new_users_today,
        revenue_today=await _cash_revenue_since(session, today_start),
        revenue_week=await _cash_revenue_since(session, week_start),
        revenue_month=await _cash_revenue_since(session, month_start),
        revenue_total=await _cash_revenue_since(session, None),
        payments_today=payments_today,
        open_tickets=open_tickets,
        servers_total=servers_total,
        servers_healthy=servers_healthy,
    )
