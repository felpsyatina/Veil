"""Генерация QR-кода конфига/ссылки подписки в PNG (в памяти)."""
from __future__ import annotations

import io

import qrcode
from qrcode.image.pil import PilImage


def make_qr_png(data: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()
