"""Выбор активного платёжного провайдера по PAYMENT_PROVIDER из .env."""
from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.payments.base import BasePaymentProvider
from app.payments.manual import ManualPaymentProvider
from app.payments.yookassa import YooKassaProvider


@lru_cache
def get_payment_provider() -> BasePaymentProvider:
    provider = settings.payment_provider.lower().strip()
    if provider == "yookassa":
        return YooKassaProvider(settings.yookassa_shop_id, settings.yookassa_secret_key)
    if provider == "manual":
        return ManualPaymentProvider()
    raise ValueError(
        f"Неизвестный PAYMENT_PROVIDER={provider!r}. Допустимые значения: manual, yookassa."
    )
