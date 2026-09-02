"""
GET /sub/{token} — то, что пользователь вставляет в VPN-клиент как ссылку
на подписку. Отдаёт base64 со списком vless://-ссылок сразу для всех нод,
где у подписки есть активный клиент (см. app/services/subscription_links.py).

Сам токен — криптостойкий случайный (32 байта), поэтому эндпоинт
не требует дополнительной аутентификации: токен и есть секрет.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.rate_limit import limiter
from app.db.base import get_session
from app.services import subscription_links as subscription_links_service
from app.services import subscriptions as subscriptions_service

router = APIRouter()


@router.get("/sub/{token}")
@limiter.limit("30/minute")
async def get_subscription(token: str, request: Request) -> Response:
    async with get_session() as session:
        sub = await subscriptions_service.get_by_token(session, token)
        if sub is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        content = await subscription_links_service.build_subscription_content(session, sub)
        expire_ts = int(sub.expires_at.timestamp())

    headers = {
        "Profile-Update-Interval": "12",
        "Subscription-Userinfo": f"upload=0;download=0;total=0;expire={expire_ts}",
    }
    return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)
