"""
Провайдер оплаты через ЮKassa (api.yookassa.ru/v3).

Настройка:
  1. Зарегистрируйте магазин на yookassa.ru, получите shopId и secretKey
     (в тестовом режиме — тестовые ключи).
  2. Впишите их в .env: YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY.
  3. В личном кабинете ЮKassa укажите URL вебхука:
     https://<ваш DOMAIN>/webhook/payments/yookassa
     (событие payment.succeeded как минимум; payment.canceled опционально).
  4. Поставьте PAYMENT_PROVIDER=yookassa в .env.

Безопасность вебхука: тело уведомления НЕ считается источником истины —
после его получения app/api/routes/payments.py всегда переспрашивает
статус через get_payment_status() (авторизованный запрос по secretKey),
и только по нему принимает решение о зачислении. Это защищает от подделки
вебхука без необходимости проверять подпись, которую ЮKassa в REST API v3
отдельно не подписывает (рекомендуемый ЮKassa паттерн — see docs).
"""
from __future__ import annotations

import logging
from decimal import Decimal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.payments.base import BasePaymentProvider, PaymentCreateResult, PaymentStatusResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.yookassa.ru/v3"


class YooKassaError(Exception):
    pass


class YooKassaProvider(BasePaymentProvider):
    name = "yookassa"

    def __init__(self, shop_id: str, secret_key: str) -> None:
        if not shop_id or not secret_key:
            raise ValueError(
                "YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY не заданы в .env. "
                "Либо заполните их, либо оставьте PAYMENT_PROVIDER=manual."
            )
        self._auth = (shop_id, secret_key)

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
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
        body = {
            "amount": {"value": f"{amount:.2f}", "currency": currency},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description[:128],
            "metadata": metadata,
        }
        async with httpx.AsyncClient(base_url=_BASE_URL, auth=self._auth, timeout=15) as client:
            resp = await client.post(
                "/payments", headers={"Idempotence-Key": idempotency_key}, json=body
            )
        if resp.status_code >= 400:
            logger.error("YooKassa create_payment %s: %s", resp.status_code, resp.text)
            raise YooKassaError(f"Не удалось создать платёж (HTTP {resp.status_code})")
        data = resp.json()
        return PaymentCreateResult(
            provider_payment_id=data["id"],
            confirmation_url=data["confirmation"]["confirmation_url"],
            raw_status=data["status"],
        )

    @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6))
    async def get_payment_status(self, provider_payment_id: str) -> PaymentStatusResult:
        async with httpx.AsyncClient(base_url=_BASE_URL, auth=self._auth, timeout=15) as client:
            resp = await client.get(f"/payments/{provider_payment_id}")
        if resp.status_code >= 400:
            logger.error("YooKassa get_payment_status %s: %s", resp.status_code, resp.text)
            raise YooKassaError(f"Не удалось получить статус платежа (HTTP {resp.status_code})")
        data = resp.json()
        return PaymentStatusResult(
            provider_payment_id=data["id"],
            raw_status=data["status"],
            paid=bool(data.get("paid", False)),
        )
