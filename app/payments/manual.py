"""
Ручной провайдер оплаты.

Используется, пока не подключён реальный эквайринг (PAYMENT_PROVIDER=manual,
значение по умолчанию). Пользователь видит реквизиты/инструкцию и жмёт
«Я оплатил», после чего заявка попадает в очередь администратора —
подтверждение производится командой в разделе «Платежи» админ-панели бота
(см. app/bot/handlers/admin/payments.py), а не автоматически.

Это позволяет полноценно тестировать и даже мягко запускать бота ещё до
выбора конкретного эквайринга.
"""
from __future__ import annotations

from decimal import Decimal

from app.payments.base import BasePaymentProvider, PaymentCreateResult, PaymentStatusResult


class ManualPaymentProvider(BasePaymentProvider):
    name = "manual"

    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: str,
        description: str,
        idempotency_key: str,
        metadata: dict[str, str],
        return_url: str,
    ) -> PaymentCreateResult:
        return PaymentCreateResult(
            provider_payment_id=f"manual_{idempotency_key}",
            confirmation_url=return_url,
            raw_status="pending",
        )

    async def get_payment_status(self, provider_payment_id: str) -> PaymentStatusResult:
        # Ручной провайдер не умеет сам подтверждать оплату — это делает
        # админ явным действием, которое напрямую вызывает
        # PaymentsService.confirm_manual_payment(). До этого статус всегда pending.
        return PaymentStatusResult(
            provider_payment_id=provider_payment_id, raw_status="pending", paid=False
        )
