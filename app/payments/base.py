"""
Общий интерфейс платёжного провайдера.

Конкретный способ оплаты выбирается через .env (PAYMENT_PROVIDER) и не должен
влиять на код бота/воркера — они работают только через этот интерфейс.
Чтобы подключить другой эквайринг (CloudPayments, Тинькофф и т.д.), достаточно
реализовать BasePaymentProvider и зарегистрировать провайдера в factory.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PaymentCreateResult:
    provider_payment_id: str
    confirmation_url: str
    raw_status: str


@dataclass
class PaymentStatusResult:
    provider_payment_id: str
    raw_status: str
    paid: bool


class BasePaymentProvider(ABC):
    name: str

    @abstractmethod
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
        """Создаёт платёж у провайдера и возвращает ссылку на оплату."""

    @abstractmethod
    async def get_payment_status(self, provider_payment_id: str) -> PaymentStatusResult:
        """Актуальный статус платежа — источник истины, а не тело вебхука.

        Вебхуки удобны как триггер "иди проверь", но окончательное решение о
        зачислении подписки всегда должно приниматься по результату ЭТОГО
        вызова (авторизованного нашим секретным ключом), а не по телу
        входящего запроса, которое в принципе можно подделать.
        """
