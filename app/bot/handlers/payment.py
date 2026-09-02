"""Кнопка «Проверить оплату» — ручной опрос статуса платежа пользователем."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.handlers.common import render
from app.bot.keyboards.user import back_kb
from app.db.models import User
from app.services import payments as payments_service

router = Router(name="payment")


@router.callback_query(F.data.startswith("pay:check:"))
async def cb_pay_check(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[-1])
    payment = await payments_service.get_payment(session, payment_id)
    if payment is None or payment.user_id != user.id:
        await callback.answer(texts.PAYMENT_NOT_FOUND, show_alert=True)
        return

    payment = await payments_service.check_and_process_payment(session, payment_id)

    if payment.status.value == "succeeded":
        await render(callback, texts.PAYMENT_SUCCESS, back_kb("menu:main"))
        await callback.answer()
    elif payment.status.value == "cancelled":
        await render(callback, texts.PAYMENT_CANCELLED, back_kb("sub:menu"))
        await callback.answer()
    else:
        await callback.answer(texts.PAYMENT_STILL_PENDING, show_alert=True)
