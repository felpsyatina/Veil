"""Тикеты поддержки: пользователь пишет — уведомление уходит всем админам."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.handlers.common import render
from app.bot.keyboards.user import back_kb, support_ticket_kb
from app.bot.states import SupportStates
from app.config import settings
from app.db.enums import TicketSender
from app.db.models import User
from app.services import tickets as tickets_service

logger = logging.getLogger(__name__)
router = Router(name="support")


@router.callback_query(F.data == "sup:menu")
async def cb_support_menu(
    callback: CallbackQuery, user: User, session: AsyncSession, state: FSMContext
) -> None:
    ticket = await tickets_service.get_open_ticket_for_user(session, user.id)
    await state.set_state(SupportStates.waiting_message)
    if ticket is not None:
        await state.update_data(ticket_id=ticket.id)
        messages = await tickets_service.list_messages(session, ticket.id)
        history = "\n".join(
            f"{'Вы' if m.sender == TicketSender.USER else '🛠 Поддержка'}: {m.text}"
            for m in messages[-5:]
        )
        text = f"{texts.SUPPORT_HAS_OPEN_TICKET}\n\n{history}"
        await render(callback, text, support_ticket_kb(ticket.id))
    else:
        await state.update_data(ticket_id=None)
        await render(callback, texts.SUPPORT_INTRO, back_kb("menu:main"))
    await callback.answer()


@router.message(SupportStates.waiting_message, F.text)
async def on_support_message(
    message: Message, user: User, session: AsyncSession, state: FSMContext
) -> None:
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    ticket = await tickets_service.get_ticket(session, ticket_id) if ticket_id else None

    if ticket is None or ticket.status.value == "closed":
        ticket = await tickets_service.create_ticket(session, user, message.text)
        reply_text = texts.SUPPORT_TICKET_CREATED
    else:
        await tickets_service.add_message(
            session,
            ticket,
            sender=TicketSender.USER,
            sender_telegram_id=user.telegram_id,
            text=message.text,
        )
        reply_text = texts.SUPPORT_MESSAGE_SENT

    await state.update_data(ticket_id=ticket.id)
    await message.answer(reply_text, reply_markup=support_ticket_kb(ticket.id))

    admin_notice = (
        f"💬 Тикет #{ticket.id} от @{user.username or user.telegram_id} "
        f"(ID {user.telegram_id}):\n\n{message.text}"
    )
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(admin_id, admin_notice)
        except Exception as exc:  # noqa: BLE001 — недоставка одному админу не критична
            logger.warning("Не удалось уведомить админа %s о тикете: %s", admin_id, exc)


@router.message(SupportStates.waiting_message)
async def on_support_non_text(message: Message) -> None:
    await message.answer("Пожалуйста, опишите проблему текстовым сообщением 🙏")


@router.callback_query(F.data.startswith("sup:close:"))
async def cb_support_close(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    ticket_id = int(callback.data.split(":")[-1])
    ticket = await tickets_service.get_ticket(session, ticket_id)
    if ticket is not None:
        await tickets_service.close_ticket(session, ticket)
    await state.clear()
    await render(callback, texts.SUPPORT_TICKET_CLOSED, back_kb("menu:main"))
    await callback.answer()
