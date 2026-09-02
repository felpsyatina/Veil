"""
Шифрование чувствительных данных (пароли панелей 3x-ui) и генерация
случайных токенов/кодов.

Пароли панелей шифруются перед записью в БД алгоритмом Fernet (AES-128 в
режиме CBC + HMAC), ключ — SECRET_KEY из .env. Это защита "в глубину":
даже если дамп БД утечёт, пароли от панелей не будут лежать открытым текстом.
"""
from __future__ import annotations

import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class SecretKeyNotConfigured(RuntimeError):
    pass


def _get_fernet() -> Fernet:
    if not settings.secret_key:
        raise SecretKeyNotConfigured(
            "SECRET_KEY не задан в .env. Сгенерируйте его командой:\n"
            "  python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(settings.secret_key.encode())


def encrypt_secret(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretKeyNotConfigured(
            "Не удалось расшифровать секрет — проверьте, что SECRET_KEY "
            "не менялся с момента, когда данные были сохранены."
        ) from exc


def generate_subscription_token() -> str:
    """Длинный непредсказуемый токен для публичной ссылки /sub/{token}."""
    return secrets.token_urlsafe(32)


def generate_referral_code() -> str:
    return secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]


def generate_idempotency_key() -> str:
    return secrets.token_hex(16)
