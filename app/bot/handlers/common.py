"""Общие хелперы, переиспользуемые разными хендлерами бота."""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup


async def render(
    callback: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    """Редактирует текст текущего сообщения бота; если это невозможно
    (например, предыдущее сообщение было фото с QR-кодом) — отправляет новое.
    """
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup)
