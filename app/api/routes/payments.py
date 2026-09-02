"""
Вебхук ЮKassa. Тело уведомления используется только как подсказка «на какой
платёж посмотреть» — фактическое решение о зачислении принимается внутри
check_and_process_payment() по результату авторизованного запроса статуса
к API ЮKassa, а не по содержимому этого запроса (см. app/payments/yookassa.py).

Всегда отвечает 200, если платёж в принципе найден и обработан (даже если
он оказался не оплачен) — иначе ЮKassa будет повторять доставку вебхука.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from app.api.rate_limit import limiter
from app.db.base import get_session
from app.services import payments as payments_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook/payments/yookassa")
@limiter.limit("120/minute")
async def yookassa_webhook(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return Response(status_code=400)

    obj = body.get("object") or {}
    provider_payment_id = obj.get("id")
    metadata = obj.get("metadata") or {}
    raw_payment_id = metadata.get("payment_id")

    async with get_session() as session:
        payment = None
        if raw_payment_id is not None and str(raw_payment_id).isdigit():
            payment = await payments_service.get_payment(session, int(raw_payment_id))
        if payment is None and provider_payment_id:
            payment = await payments_service.get_payment_by_provider_id(session, provider_payment_id)
        if payment is None:
            logger.warning(
                "Webhook YooKassa: платёж не найден (provider_payment_id=%s)", provider_payment_id
            )
            return Response(status_code=200)

        await payments_service.check_and_process_payment(session, payment.id)

    return Response(status_code=200)
