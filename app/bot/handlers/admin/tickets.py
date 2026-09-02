"""Админ: просмотр открытых тикетов и ответы пользователям."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.filters.admin import IsAdmin
from app.bot.handlers.common import render
from app.bot.keyboards.admin import admin_back_kb, admin_ticket_card_kb, admin_tickets_kb
from app.bot.states import AdminTicketReplyStates
from app.db.enums import TicketSender
from app.services import tickets as tickets_service
from app.services import users as users_service

router = Router(name="admin_tickets")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:tickets")
async def cb_tickets_list(callback: CallbackQuery, session: AsyncSession) -> None:
    tickets = await tickets_service.list_open_tickets(session)
    labels: dict[int, str] = {}
    for t in tickets:
        u = await users_service.get_by_id(session, t.user_id)
        labels[t.id] = f"@{u.username}" if u and u.username else str(t.user_id)
    text = "💬 Открытые обращения:" if tickets else texts.ADMIN_TICKETS_EMPTY
    await render(callback, text, admin_tickets_kb(tickets, labels))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:ticketcard:"))
async def cb_ticket_card(callback: CallbackQuery, session: AsyncSession) -> None:
    ticket_id = int(callback.data.split(":")[-1])
    ticket = await tickets_service.get_ticket(session, ticket_id)
    if ticket is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    messages = await tickets_service.list_messages(session, ticket_id)
    history = "\n\n".join(
        f"{'👤 Пользователь' if m.sender == TicketSender.USER else '🛠 Вы'}: {m.text}"
        for m in messages[-10:]
    )
    await render(callback, f"<b>Обращение #{ticket.id}</b>\n\n{history}", admin_ticket_card_kb(ticket.id))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:ticketreply:"))
async def cb_ticket_reply_start(callback: CallbackQuery, state: FSMContext) -> None:
    ticket_id = int(callback.data.split(":")[-1])
    await state.set_state(AdminTicketReplyStates.text)
    await state.update_data(ticket_id=ticket_id)
    await render(
        callback, texts.ADMIN_TICKET_REPLY_PROMPT, admin_back_kb(f"adm:ticketcard:{ticket_id}")
    )
    await callback.answer()


@router.message(AdminTicketReplyStates.text, F.text)
async def on_ticket_reply(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    ticket = await tickets_service.get_ticket(session, ticket_id) if ticket_id else None
    await state.clear()
    if ticket is None:
        await message.answer("Обращение не найдено — возможно, уже закрыто.")
        return

    await tickets_service.add_message(
        session,
        ticket,
        sender=TicketSender.ADMIN,
        sender_telegram_id=message.from_user.id,
        text=message.text,
    )
    user = await users_service.get_by_id(session, ticket.user_id)
    await message.answer("✅ Ответ отправлен.", reply_markup=admin_ticket_card_kb(ticket.id))
    if user is not None:
        try:
            await message.bot.send_message(
                user.telegram_id, f"{texts.SUPPORT_NEW_REPLY_NOTICE}\n\n{message.text}"
            )
        except Exception:  # noqa: BLE001 — пользователь мог заблокировать бота
            pass


@router.callback_query(F.data.startswith("adm:ticketclose:"))
async def cb_ticket_close(callback: CallbackQuery, session: AsyncSession) -> None:
    ticket_id = int(callback.data.split(":")[-1])
    ticket = await tickets_service.get_ticket(session, ticket_id)
    if ticket is not None:
        await tickets_service.close_ticket(session, ticket)
    await render(callback, "✅ Обращение закрыто.", admin_back_kb("adm:tickets"))
    await callback.answer()
