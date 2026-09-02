"""
Состояние подписки пользователя.

Намеренно НЕ обращается к 3x-ui напрямую — только читает/пишет БД. Реальное
создание/отключение VLESS-клиентов на нодах — в app/services/provisioning.py,
который дергает эти функции и функции app/services/nodes.py вместе.

У пользователя не больше одной подписки (User.subscription — one-to-one):
повторная оплата продлевает текущую запись, а не создаёт новую.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.enums import SubscriptionStatus
from app.db.models import Subscription, Tariff, User
from app.utils.security import generate_subscription_token


async def get_by_user(session: AsyncSession, user_id: int) -> Subscription | None:
    result = await session.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_by_token(session: AsyncSession, token: str) -> Subscription | None:
    result = await session.execute(
        select(Subscription).where(Subscription.subscription_token == token)
    )
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, sub_id: int) -> Subscription | None:
    return await session.get(Subscription, sub_id)


def _new_identity(telegram_id: int) -> tuple[str, str, str]:
    """Возвращает (xui_uuid, xui_email, subscription_token) для новой подписки."""
    client_uuid = str(uuid.uuid4())
    email = f"u{telegram_id}-{client_uuid[:8]}"
    token = generate_subscription_token()
    return client_uuid, email, token


async def create_trial(session: AsyncSession, user: User) -> Subscription:
    if await get_by_user(session, user.id) is not None:
        raise ValueError("У пользователя уже есть подписка")
    client_uuid, email, token = _new_identity(user.telegram_id)
    now = dt.datetime.now(dt.UTC)
    sub = Subscription(
        user_id=user.id,
        xui_uuid=client_uuid,
        xui_email=email,
        status=SubscriptionStatus.TRIAL,
        tariff_id=None,
        device_limit=settings.device_limit,
        subscription_token=token,
        started_at=now,
        expires_at=now + dt.timedelta(days=settings.trial_days),
    )
    session.add(sub)
    await session.flush()
    return sub


async def get_or_create_for_purchase(session: AsyncSession, user: User) -> Subscription:
    """Возвращает существующую подписку пользователя либо создаёт пустую запись
    со статусом EXPIRED (ещё не оплачена) — на неё затем накатывается тариф
    через apply_paid_period()/extend_days().
    """
    sub = await get_by_user(session, user.id)
    if sub is not None:
        return sub
    client_uuid, email, token = _new_identity(user.telegram_id)
    now = dt.datetime.now(dt.UTC)
    sub = Subscription(
        user_id=user.id,
        xui_uuid=client_uuid,
        xui_email=email,
        status=SubscriptionStatus.EXPIRED,
        tariff_id=None,
        device_limit=settings.device_limit,
        subscription_token=token,
        started_at=now,
        expires_at=now,
    )
    session.add(sub)
    await session.flush()
    return sub


def _extend_base(subscription: Subscription) -> dt.datetime:
    now = dt.datetime.now(dt.UTC)
    return subscription.expires_at if subscription.expires_at > now else now


async def apply_paid_period(
    session: AsyncSession, subscription: Subscription, tariff: Tariff
) -> Subscription:
    """Продлевает подписку на срок тарифа. Если подписка ещё активна — прибавляет
    дни к текущему expires_at (не сгорает при досрочном продлении), иначе
    считает от текущего момента.
    """
    subscription.expires_at = _extend_base(subscription) + dt.timedelta(days=tariff.duration_days)
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.tariff_id = tariff.id
    subscription.notified_thresholds = ""
    subscription.notified_expired = False
    await session.flush()
    return subscription


async def extend_days(session: AsyncSession, subscription: Subscription, days: int) -> Subscription:
    """Продление вручную из админ-панели (без привязки к тарифу). days может
    быть отрицательным, чтобы сократить подписку."""
    new_expiry = _extend_base(subscription) + dt.timedelta(days=days)
    now = dt.datetime.now(dt.UTC)
    subscription.expires_at = new_expiry if new_expiry > now else now
    subscription.status = SubscriptionStatus.ACTIVE if subscription.expires_at > now else SubscriptionStatus.EXPIRED
    subscription.notified_thresholds = ""
    subscription.notified_expired = False
    await session.flush()
    return subscription


async def mark_expired(session: AsyncSession, subscription: Subscription) -> None:
    subscription.status = SubscriptionStatus.EXPIRED
    await session.flush()


async def mark_cancelled(session: AsyncSession, subscription: Subscription) -> None:
    subscription.status = SubscriptionStatus.CANCELLED
    await session.flush()


async def list_active_and_trial(session: AsyncSession) -> list[Subscription]:
    result = await session.execute(
        select(Subscription).where(
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        )
    )
    return list(result.scalars().all())


async def list_expiring_between(
    session: AsyncSession, *, from_days: float, to_days: float
) -> list[Subscription]:
    now = dt.datetime.now(dt.UTC)
    result = await session.execute(
        select(Subscription).where(
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            Subscription.expires_at > now + dt.timedelta(days=from_days),
            Subscription.expires_at <= now + dt.timedelta(days=to_days),
        )
    )
    return list(result.scalars().all())


async def list_newly_expired(session: AsyncSession) -> list[Subscription]:
    """Подписки, у которых срок истёк, но статус ещё не обновлён (для воркера)."""
    now = dt.datetime.now(dt.UTC)
    result = await session.execute(
        select(Subscription).where(
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            Subscription.expires_at <= now,
        )
    )
    return list(result.scalars().all())


def has_notified(subscription: Subscription, threshold_days: int) -> bool:
    tokens = {t for t in subscription.notified_thresholds.split(",") if t}
    return str(threshold_days) in tokens


async def record_notification(
    session: AsyncSession, subscription: Subscription, threshold_days: int
) -> None:
    tokens = [t for t in subscription.notified_thresholds.split(",") if t]
    if str(threshold_days) not in tokens:
        tokens.append(str(threshold_days))
    subscription.notified_thresholds = ",".join(tokens)
    await session.flush()


async def record_expired_notification(session: AsyncSession, subscription: Subscription) -> None:
    subscription.notified_expired = True
    await session.flush()


def referral_reward_amount(payment_amount: Decimal) -> Decimal:
    return (payment_amount * settings.referral_percent / Decimal("100")).quantize(Decimal("0.01"))
