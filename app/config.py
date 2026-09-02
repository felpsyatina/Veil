"""
Конфигурация приложения.

Все переменные читаются из окружения (см. .env.example). Настройки шарятся
между всеми сервисами (bot, api, worker, migrate) — это один и тот же образ,
просто с разной командой запуска.
"""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Общее
    env: str = "production"
    log_level: str = "INFO"
    tz: str = "Europe/Moscow"

    # Telegram
    bot_token: str
    admin_ids: list[int] = []
    support_username: str = "@support"

    # База данных
    postgres_db: str = "vpnshop"
    postgres_user: str = "vpnshop"
    postgres_password: str = ""
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: str = ""

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Безопасность
    secret_key: str = ""

    # Домен / публичный API
    domain: str = "localhost"
    acme_email: str = ""
    subscription_base_url: str = "http://localhost:8000"

    # Бизнес-логика
    trial_days: int = 3
    device_limit: int = 1
    referral_percent: Decimal = Decimal("10")
    notify_before_days: list[int] = [3, 1]

    # Платежи
    payment_provider: str = "manual"
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = ""

    # Reality (значения по умолчанию для новых нод)
    reality_dest: str = "www.microsoft.com:443"
    reality_server_names: str = "www.microsoft.com"
    reality_fingerprint: str = "chrome"

    # Резервные копии
    backup_dir: str = "/backups"
    backup_retention_days: int = 14
    backup_hour: int = 4

    # Антифрод
    payment_rate_limit_count: int = 5
    payment_rate_limit_window_sec: int = 3600

    @field_validator("admin_ids", "notify_before_days", mode="before")
    @classmethod
    def _parse_int_csv(cls, v: object) -> object:
        """Разбирает строки вида '1,2,3' из .env в список int."""
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def _build_database_url(self) -> "Settings":
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        return self

    @property
    def reality_server_names_list(self) -> list[str]:
        return [s.strip() for s in self.reality_server_names.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
