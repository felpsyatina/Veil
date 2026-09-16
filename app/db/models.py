"""
ORM-модели проекта.

Ключевые решения (см. docs/ARCHITECTURE.md для подробностей):
- У пользователя не больше одной "боевой" подписки (Subscription.user_id уникален).
  Повторная оплата продлевает существующую подписку, а не создаёт новую — так
  UUID VLESS-клиента и его привязки к нодам не приходится пересоздавать.
- Subscription агрегирует несколько серверов через SubscriptionServer:
  один subscription_token → один VLESS UUID → клиент добавлен на всех активных
  нодах. Содержимое subscription-ссылки собирается на лету из активных и
  здоровых нод (см. app/services/subscription_links.py).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import PaymentStatus, SubscriptionStatus, TicketSender, TicketStatus


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(256))

    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    referral_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))

    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    referrer: Mapped["User | None"] = relationship(
        remote_side="User.id", back_populates="referred_users"
    )
    referred_users: Mapped[list["User"]] = relationship(
        back_populates="referrer", foreign_keys=[referrer_id]
    )
    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="user", uselist=False
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    tickets: Mapped[list["SupportTicket"]] = relationship(back_populates="user")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} tg={self.telegram_id}>"


class Server(Base):
    """Нода — отдельный сервер с 3x-ui и Reality-инбаундом для наших клиентов."""

    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    country_code: Mapped[str | None] = mapped_column(String(4))

    # Адрес, который попадает в vless:// ссылку клиента (домен или IP ноды).
    host: Mapped[str] = mapped_column(String(256))
    port: Mapped[int] = mapped_column(Integer)

    # Доступ к панели 3x-ui этой ноды.
    panel_url: Mapped[str] = mapped_column(String(512))
    panel_username: Mapped[str] = mapped_column(String(128))
    panel_password_encrypted: Mapped[str] = mapped_column(Text)
    # API-токен панели (3x-ui 3.7.0+, Settings → Security → API Token) —
    # предпочтительный способ авторизации бота на панели, см. app/xui/client.py.
    # Может быть пустым для старых версий панели без поддержки токенов —
    # тогда используется обычный логин по username/password.
    api_token_encrypted: Mapped[str | None] = mapped_column(Text)

    inbound_id: Mapped[int | None] = mapped_column(Integer)

    # Параметры Reality, закэшированные на момент создания инбаунда — нужны,
    # чтобы строить vless:// ссылки без обращения к панели на каждый чих.
    reality_public_key: Mapped[str | None] = mapped_column(String(128))
    reality_private_key_encrypted: Mapped[str | None] = mapped_column(Text)
    reality_short_ids: Mapped[str | None] = mapped_column(String(256))  # csv
    reality_server_names: Mapped[str | None] = mapped_column(String(512))  # csv
    reality_dest: Mapped[str | None] = mapped_column(String(256))
    reality_fingerprint: Mapped[str] = mapped_column(String(32), default="chrome")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    last_check_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    subscription_links: Mapped[list["SubscriptionServer"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Server id={self.id} name={self.name!r}>"


class Tariff(Base):
    """Тарифный план. Хранится в БД, чтобы админ мог добавлять/менять тарифы без деплоя."""

    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(64))
    duration_days: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Subscription(Base):
    """"Боевая" подписка пользователя. У одного пользователя — не более одной."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)

    xui_uuid: Mapped[str] = mapped_column(String(36), unique=True)
    xui_email: Mapped[str] = mapped_column(String(128), unique=True)

    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, name="subscription_status"),
        default=SubscriptionStatus.TRIAL,
    )
    tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"))
    device_limit: Mapped[int] = mapped_column(Integer, default=1)

    subscription_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))

    # csv из порогов (в днях), по которым уже отправлено напоминание,
    # например "3,1" — чтобы не слать одно и то же уведомление повторно.
    notified_thresholds: Mapped[str] = mapped_column(String(64), default="")
    notified_expired: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="subscription")
    tariff: Mapped["Tariff | None"] = relationship()
    servers: Mapped[list["SubscriptionServer"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="subscription")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subscription id={self.id} user_id={self.user_id} status={self.status}>"


class SubscriptionServer(Base):
    """Связка «подписка ↔ нода»: на какой ноде реально создан VLESS-клиент."""

    __tablename__ = "subscription_servers"
    __table_args__ = (UniqueConstraint("subscription_id", "server_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id"))

    is_provisioned: Mapped[bool] = mapped_column(Boolean, default=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    subscription: Mapped["Subscription"] = relationship(back_populates="servers")
    server: Mapped["Server"] = relationship(back_populates="subscription_links")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"))
    tariff_id: Mapped[int | None] = mapped_column(ForeignKey("tariffs.id"))

    provider: Mapped[str] = mapped_column(String(32))
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    applied_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))

    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING
    )
    confirmation_url: Mapped[str | None] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(String(256))

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="payments")
    subscription: Mapped["Subscription | None"] = relationship(back_populates="payments")
    tariff: Mapped["Tariff | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment id={self.id} status={self.status} amount={self.amount}>"


class ReferralReward(Base):
    """Лог начислений по реферальной программе (для прозрачности и статистики)."""

    __tablename__ = "referral_rewards"

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(TicketStatus, name="ticket_status"), default=TicketStatus.OPEN
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="tickets")
    messages: Mapped[list["TicketMessage"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketMessage.id"
    )


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id"))
    sender: Mapped[TicketSender] = mapped_column(SAEnum(TicketSender, name="ticket_sender"))
    sender_telegram_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    ticket: Mapped["SupportTicket"] = relationship(back_populates="messages")
