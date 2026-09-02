"""FastAPI-приложение: вебхуки платёжного провайдера + публичные subscription-ссылки.

Запуск: uvicorn app.api.main:app --host 0.0.0.0 --port 8000
(см. docker-compose.yml, сервис `api`, за ним — Caddy с авто-HTTPS).
"""
from __future__ import annotations

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.rate_limit import limiter
from app.api.routes import health, payments, subscription
from app.logging_conf import setup_logging

setup_logging()

app = FastAPI(
    title="VPN Shop API",
    description="Вебхуки платежей и subscription-ссылки. Не предназначен для публичного браузинга.",
    docs_url=None,
    redoc_url=None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(health.router)
app.include_router(subscription.router)
app.include_router(payments.router)
