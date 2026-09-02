"""
Реферальная программа.

Модель — бонусный баланс (в рублях), а не автопродление дней: за каждый
успешный платёж приглашённого пользователя рефереру начисляется
REFERRAL_PERCENT от суммы. Баланс можно списать при следующей покупке
(частично или полностью), уменьшив сумму, уходящую в эквайринг.

Списание баланса при создании платежа происходит сразу (reserve_balance),
чтобы исключить двойное использование одного и того же баланса при двух
параллельных попытках оплаты. Если платёж не завершится успехом — баланс
возвращается (refund_balance).
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, ReferralReward, User
from app.services.subscriptions import referral_reward_amount


async def reserve_balance(session: AsyncSession, user: User, max_amount: Decimal) -> Decimal:
    """Списывает из баланса пользователя min(баланс, max_amount) и возвращает списанное."""
    to_use = min(user.referral_balance, max_amount) if max_amount > 0 else Decimal("0")
    if to_use > 0:
        user.referral_balance -= to_use
        await session.flush()
    return to_use


async def refund_balance(session: AsyncSession, user: User, amount: Decimal) -> None:
    if amount > 0:
        user.referral_balance += amount
        await session.flush()


async def apply_referral_reward(
    session: AsyncSession, *, payer: User, payment: Payment
) -> ReferralReward | None:
    """Начисляет рефереру бонус после успешной оплаты. Вызывать один раз на
    платёж (после перевода Payment в SUCCEEDED) — сервис не проверяет
    идемпотентность сам, это делает вызывающий (app/services/payments.py)."""
    if payer.referrer_id is None:
        return None
    referrer = await session.get(User, payer.referrer_id)
    if referrer is None or referrer.is_banned:
        return None
    # Начисляем % от реально поступивших денег (за вычетом списанного бонусного
    # баланса), а не от номинальной цены тарифа — иначе баланс можно было бы
    # "размножать" оплатой подписок за счёт уже начисленных бонусов.
    cash_amount = payment.amount - payment.applied_balance
    amount = referral_reward_amount(cash_amount)
    if amount <= 0:
        return None
    referrer.referral_balance += amount
    reward = ReferralReward(
        referrer_id=referrer.id,
        referred_user_id=payer.id,
        payment_id=payment.id,
        amount=amount,
    )
    session.add(reward)
    await session.flush()
    return reward
