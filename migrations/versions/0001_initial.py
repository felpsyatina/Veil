"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-01

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64)),
        sa.Column("full_name", sa.String(256)),
        sa.Column("referrer_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("referral_code", sa.String(16), nullable=False),
        sa.Column("referral_balance", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trial_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)
    op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)

    op.create_table(
        "tariffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(64), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "servers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country_code", sa.String(4)),
        sa.Column("host", sa.String(256), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("panel_url", sa.String(512), nullable=False),
        sa.Column("panel_username", sa.String(128), nullable=False),
        sa.Column("panel_password_encrypted", sa.Text(), nullable=False),
        sa.Column("inbound_id", sa.Integer()),
        sa.Column("reality_public_key", sa.String(128)),
        sa.Column("reality_private_key_encrypted", sa.Text()),
        sa.Column("reality_short_ids", sa.String(256)),
        sa.Column("reality_server_names", sa.String(512)),
        sa.Column("reality_dest", sa.String(256)),
        sa.Column("reality_fingerprint", sa.String(32), nullable=False, server_default="chrome"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_healthy", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_check_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("xui_uuid", sa.String(36), nullable=False),
        sa.Column("xui_email", sa.String(128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("trial", "active", "expired", "cancelled", name="subscription_status"),
            nullable=False,
            server_default="trial",
        ),
        sa.Column("tariff_id", sa.Integer(), sa.ForeignKey("tariffs.id")),
        sa.Column("device_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("subscription_token", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notified_thresholds", sa.String(64), nullable=False, server_default=""),
        sa.Column("notified_expired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"], unique=True)
    op.create_index("ix_subscriptions_xui_uuid", "subscriptions", ["xui_uuid"], unique=True)
    op.create_index("ix_subscriptions_xui_email", "subscriptions", ["xui_email"], unique=True)
    op.create_index(
        "ix_subscriptions_token", "subscriptions", ["subscription_token"], unique=True
    )

    op.create_table(
        "subscription_servers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id"), nullable=False
        ),
        sa.Column("server_id", sa.Integer(), sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("is_provisioned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_error", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("subscription_id", "server_id", name="uq_sub_server"),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscriptions.id")),
        sa.Column("tariff_id", sa.Integer(), sa.ForeignKey("tariffs.id")),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_payment_id", sa.String(128)),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column("applied_balance", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.Enum("pending", "succeeded", "failed", "cancelled", name="payment_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("confirmation_url", sa.String(1024)),
        sa.Column("description", sa.String(256)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_payments_provider_payment_id", "payments", ["provider_payment_id"], unique=True
    )
    op.create_index("ix_payments_idempotency_key", "payments", ["idempotency_key"], unique=True)

    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "answered", "closed", name="ticket_status"),
            nullable=False,
            server_default="open",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "ticket_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id"), nullable=False
        ),
        sa.Column("sender", sa.Enum("user", "admin", name="ticket_sender"), nullable=False),
        sa.Column("sender_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Тарифы по умолчанию — ЦЕНЫ ЯВНО ПОДСТАВНЫЕ, поменяйте их в разделе
    # «Тарифы» админ-панели бота под свою экономику до открытия продаж.
    tariffs_table = sa.table(
        "tariffs",
        sa.column("title", sa.String),
        sa.column("duration_days", sa.Integer),
        sa.column("price", sa.Numeric),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        tariffs_table,
        [
            {"title": "1 месяц", "duration_days": 30, "price": 149, "sort_order": 1},
            {"title": "3 месяца", "duration_days": 90, "price": 399, "sort_order": 2},
            {"title": "12 месяцев", "duration_days": 365, "price": 1390, "sort_order": 3},
        ],
    )


def downgrade() -> None:
    op.drop_table("ticket_messages")
    op.drop_table("support_tickets")
    op.drop_table("referral_rewards")
    op.drop_table("payments")
    op.drop_table("subscription_servers")
    op.drop_table("subscriptions")
    op.drop_table("servers")
    op.drop_table("tariffs")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS subscription_status")
    op.execute("DROP TYPE IF EXISTS payment_status")
    op.execute("DROP TYPE IF EXISTS ticket_status")
    op.execute("DROP TYPE IF EXISTS ticket_sender")
