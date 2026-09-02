"""Enum'ы статусов, общие для моделей и бизнес-логики."""
from __future__ import annotations

import enum


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    ANSWERED = "answered"
    CLOSED = "closed"


class TicketSender(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
