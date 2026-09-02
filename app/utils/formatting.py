"""Хелперы форматирования для текстов бота — время в МСК, суммы в рублях."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.config import settings

_TZ = ZoneInfo(settings.tz)


def to_local(value: dt.datetime) -> dt.datetime:
    """Конвертирует datetime (обычно UTC из БД) в локальную таймзону проекта."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.astimezone(_TZ)


def format_dt(value: dt.datetime) -> str:
    """'01.09.2026 15:04 МСК' — для текстов бота."""
    local = to_local(value)
    return local.strftime("%d.%m.%Y %H:%M МСК")


def format_date(value: dt.datetime) -> str:
    return to_local(value).strftime("%d.%m.%Y")


def format_money(amount: Decimal) -> str:
    """'299 ₽' без лишних копеек, если сумма целая; иначе '299.50 ₽'."""
    normalized = amount.quantize(Decimal("0.01"))
    if normalized == normalized.to_integral_value():
        return f"{int(normalized)} ₽"
    return f"{normalized} ₽"


def days_left(expires_at: dt.datetime) -> int:
    now = dt.datetime.now(dt.UTC)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.UTC)
    delta = expires_at - now
    return max(0, delta.days + (1 if delta.seconds > 0 else 0))
