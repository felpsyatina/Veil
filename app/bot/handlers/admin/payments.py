"""
Админ: платежи, ожидающие подтверждения (актуально при PAYMENT_PROVIDER=manual —
пока не подключён реальный эквайринг, см. README → «Оплата»).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.filters.admin import IsAdmin
from app.bot.handlers.common import render
from app.bot.keyboards.admin import admin_back_kb, admin_payment_card_kb, admin_pending_payments_kb
from app.services import payments as payments_service
from app.services import users as users_service

router = Router(name="admin_payments")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:pending")
async def cb_pending_list(callback: CallbackQuery, session: AsyncSession) -> None:
    payments = await payments_service.list_pending_manual_payments(session)
    text = "🧾 Ожидают подтверждения:" if payments else texts.PENDING_PAYMENTS_EMPTY
    await render(callback, text, admin_pending_payments_kb(payments))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:paycard:"))
async def cb_payment_card(callback: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[-1])
    payment = await payments_service.get_payment(session, payment_id)
    if payment is None:
        await callback.answer(texts.PAYMENT_NOT_FOUND, show_alert=True)
        return
    user = await users_service.get_by_id(session, payment.user_id)
    await render(callback, texts.admin_payment_card(payment, user), admin_payment_card_kb(payment.id))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:payconfirm:"))
async def cb_payment_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[-1])
    payment = await payments_service.confirm_manual_payment(session, payment_id)
    await render(callback, "✅ Оплата подтверждена, подписка продлена.", admin_back_kb("adm:pending"))
    await callback.answer()
    if payment.status.value == "succeeded":
        user = await users_service.get_by_id(session, payment.user_id)
        if user is not None:
            try:
                await callback.bot.send_message(user.telegram_id, texts.PAYMENT_SUCCESS)
            except Exception:  # noqa: BLE001
                pass


@router.callback_query(F.data.startswith("adm:paycancel:"))
async def cb_payment_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[-1])
    await payments_service.cancel_payment(session, payment_id)
    await render(callback, "❌ Платёж отклонён.", admin_back_kb("adm:pending"))
    await callback.answer()
