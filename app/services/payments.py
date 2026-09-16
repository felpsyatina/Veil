"""
Сервис платежей — самое чувствительное место всего проекта: здесь деньги
превращаются в доступ к VPN, и ошибка означает либо потерянную оплату, либо
задвоенное продление.

Идемпотентность обеспечена на двух уровнях:
  1. idempotency_key уходит в платёжный провайдер (защита от задвоения
     самого платежа при повторной отправке запроса).
  2. check_and_process_payment() перечитывает Payment с SELECT ... FOR UPDATE
     перед проверкой статуса — конкурентные вызовы (вебхук + ручная проверка
     + фоновая сверка одновременно) не смогут дважды продлить подписку по
     одному и тому же платежу.

Источник истины по статусу платежа — всегда ответ провайдера на
get_payment_status(), а не тело вебхука (см. app/payments/yookassa.py).
"""
from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.enums import PaymentStatus
from app.db.models import Payment, Tariff, User
from app.payments.base import PaymentCreateResult
from app.payments.factory import get_payment_provider
from app.services import provisioning as provisioning_service
from app.services import referrals as referrals_service
from app.services import subscriptions as subscriptions_service
from app.utils.security import generate_idempotency_key

logger = logging.getLogger(__name__)


class PaymentCreationError(Exception):
    pass


def _return_url() -> str:
    return settings.yookassa_return_url or "https://t.me"


async def _fulfil_payment(session: AsyncSession, payment: Payment, user: User) -> None:
    """Идемпотентная часть: продлевает подписку и синхронизирует ноды.
    Вызывать ровно один раз на платёж, уже переведённый в SUCCEEDED."""
    if payment.tariff_id is None:
        logger.warning("Payment #%s помечен успешным, но без tariff_id — пропуск", payment.id)
        return
    tariff = await session.get(Tariff, payment.tariff_id)
    if tariff is None:
        logger.error("Payment #%s ссылается на несуществующий tariff_id=%s", payment.id, payment.tariff_id)
        return

    sub = await subscriptions_service.get_or_create_for_purchase(session, user)
    await subscriptions_service.apply_paid_period(session, sub, tariff)
    payment.subscription_id = sub.id
    await session.flush()

    await provisioning_service.sync_subscription_everywhere(session, sub, user.telegram_id)
    await referrals_service.apply_referral_reward(session, payer=user, payment=payment)


async def create_payment_for_tariff(
    session: AsyncSession, user: User, tariff: Tariff, *, use_balance: bool = True
) -> tuple[Payment, PaymentCreateResult | None]:
    """Создаёт платёж на тариф. Второй элемент результата — None, если сумма
    полностью покрылась бонусным балансом (платёж уже SUCCEEDED, подписка
    уже продлена и синхронизирована — эквайринг не понадобился)."""
    amount = tariff.price
    applied = (
        await referrals_service.reserve_balance(session, user, amount)
        if use_balance
        else Decimal("0")
    )
    cash_amount = amount - applied

    payment = Payment(
        user_id=user.id,
        tariff_id=tariff.id,
        amount=amount,
        applied_balance=applied,
        currency="RUB",
        provider=settings.payment_provider,
        idempotency_key=generate_idempotency_key(),
        status=PaymentStatus.PENDING,
        description=f"Подписка «{tariff.title}»",
    )
    session.add(payment)
    await session.flush()

    if cash_amount <= 0:
        payment.status = PaymentStatus.SUCCEEDED
        payment.provider = "balance"
        payment.provider_payment_id = f"balance_{payment.id}"
        await session.flush()
        await _fulfil_payment(session, payment, user)
        return payment, None

    provider = get_payment_provider()
    try:
        result = await provider.create_payment(
            amount=cash_amount,
            currency="RUB",
            description=payment.description or "Оплата подписки",
            idempotency_key=payment.idempotency_key,
            metadata={"payment_id": str(payment.id), "user_id": str(user.id)},
            return_url=_return_url(),
        )
    except Exception as exc:
        await referrals_service.refund_balance(session, user, applied)
        payment.status = PaymentStatus.FAILED
        await session.flush()
        raise PaymentCreationError(str(exc)) from exc

    payment.provider_payment_id = result.provider_payment_id
    payment.confirmation_url = result.confirmation_url
    await session.flush()
    return payment, result


async def check_and_process_payment(session: AsyncSession, payment_id: int) -> Payment:
    """Идемпотентно проверяет платёж у провайдера и, если оплачен, фиксирует
    успех + продлевает подписку. Безопасно вызывать многократно и параллельно
    (вебхук, кнопка «Проверить оплату», фоновая сверка) — блокирует строку
    платежа на время проверки, так что задвоения не произойдёт.
    """
    result = await session.execute(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    payment = result.scalar_one()

    if payment.status != PaymentStatus.PENDING:
        return payment
    if payment.provider_payment_id is None or payment.provider.lower() == "manual":
        return payment

    provider = get_payment_provider()
    status = await provider.get_payment_status(payment.provider_payment_id)

    if status.paid:
        payment.status = PaymentStatus.SUCCEEDED
        await session.flush()
        user = await session.get(User, payment.user_id)
        if user is not None:
            await _fulfil_payment(session, payment, user)
    elif status.raw_status in ("canceled", "cancelled"):
        payment.status = PaymentStatus.CANCELLED
        await session.flush()
        user = await session.get(User, payment.user_id)
        if user is not None:
            await referrals_service.refund_balance(session, user, payment.applied_balance)

    return payment


async def confirm_manual_payment(session: AsyncSession, payment_id: int) -> Payment:
    """Ручное подтверждение оплаты администратором (PAYMENT_PROVIDER=manual
    или банковский перевод без вебхуков). Та же блокировка строки, что и в
    check_and_process_payment — защищает от повторного нажатия."""
    result = await session.execute(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    payment = result.scalar_one()
    if payment.status != PaymentStatus.PENDING:
        return payment

    payment.status = PaymentStatus.SUCCEEDED
    await session.flush()
    user = await session.get(User, payment.user_id)
    if user is not None:
        await _fulfil_payment(session, payment, user)
    return payment


async def cancel_payment(session: AsyncSession, payment_id: int) -> Payment:
    result = await session.execute(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    payment = result.scalar_one()
    if payment.status != PaymentStatus.PENDING:
        return payment
    payment.status = PaymentStatus.CANCELLED
    await session.flush()
    user = await session.get(User, payment.user_id)
    if user is not None:
        await referrals_service.refund_balance(session, user, payment.applied_balance)
    return payment


async def get_payment(session: AsyncSession, payment_id: int) -> Payment | None:
    return await session.get(Payment, payment_id)


async def list_payment_history(session: AsyncSession, user_id: int, limit: int = 10) -> list[Payment]:
    result = await session.execute(
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_stale_pending_payments(session: AsyncSession, older_than_minutes: int) -> list[Payment]:
    """Для фоновой сверки — платежи, зависшие в pending дольше N минут
    (на случай, если вебхук не дошёл)."""
    threshold = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=older_than_minutes)
    result = await session.execute(
        select(Payment).where(
            Payment.status == PaymentStatus.PENDING,
            func.lower(Payment.provider) != "manual",
            Payment.created_at <= threshold,
        )
    )
    return list(result.scalars().all())


async def list_pending_manual_payments(session: AsyncSession, limit: int = 30) -> list[Payment]:
    """Платежи, ожидающие ручного подтверждения админом (PAYMENT_PROVIDER=manual)."""
    result = await session.execute(
        select(Payment)
        .where(Payment.status == PaymentStatus.PENDING, func.lower(Payment.provider) == "manual")
        .order_by(Payment.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_payment_by_provider_id(session: AsyncSession, provider_payment_id: str) -> Payment | None:
    result = await session.execute(
        select(Payment).where(Payment.provider_payment_id == provider_payment_id)
    )
    return result.scalar_one_or_none()
