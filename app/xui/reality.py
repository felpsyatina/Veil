"""
Генерация пары ключей X25519 для Reality и сборка share-ссылок vless://.

Ключи генерируются локально через `cryptography` (это обычная пара X25519,
формат идентичен тому, что делает `xray x25519`), а не через API панели —
так добавление новой ноды не зависит от конкретной версии/форка 3x-ui.
"""
from __future__ import annotations

import base64
import secrets
from urllib.parse import quote

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def _b64url_nopad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate_x25519_keypair() -> tuple[str, str]:
    """Возвращает (private_key_b64, public_key_b64) в формате, который ждёт Xray Reality."""
    private_key = X25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    )
    public_raw = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _b64url_nopad(private_raw), _b64url_nopad(public_raw)


def generate_short_id(length: int = 8) -> str:
    """Короткий hex-идентификатор Reality (0-16 символов согласно спецификации)."""
    return secrets.token_hex(length // 2)


def build_vless_reality_link(
    *,
    uuid: str,
    host: str,
    port: int,
    public_key: str,
    short_id: str,
    server_name: str,
    fingerprint: str = "chrome",
    flow: str = "xtls-rprx-vision",
    remark: str = "server",
) -> str:
    """Собирает vless:// ссылку для клиента VLESS + Reality (TCP-транспорт)."""
    query = (
        "type=tcp"
        "&security=reality"
        "&encryption=none"
        f"&pbk={quote(public_key, safe='')}"
        f"&fp={quote(fingerprint, safe='')}"
        f"&sni={quote(server_name, safe='')}"
        f"&sid={quote(short_id, safe='')}"
        "&spx=%2F"
    )
    if flow:
        query += f"&flow={quote(flow, safe='')}"
    return f"vless://{uuid}@{host}:{port}?{query}#{quote(remark, safe='')}"
