"""Тикеты поддержки внутри бота: пользователь пишет — админ отвечает в боте."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import TicketSender, TicketStatus
from app.db.models import SupportTicket, TicketMessage, User


async def create_ticket(session: AsyncSession, user: User, text: str) -> SupportTicket:
    ticket = SupportTicket(user_id=user.id, status=TicketStatus.OPEN)
    session.add(ticket)
    await session.flush()
    session.add(
        TicketMessage(
            ticket_id=ticket.id,
            sender=TicketSender.USER,
            sender_telegram_id=user.telegram_id,
            text=text,
        )
    )
    await session.flush()
    return ticket


async def add_message(
    session: AsyncSession,
    ticket: SupportTicket,
    *,
    sender: TicketSender,
    sender_telegram_id: int,
    text: str,
) -> TicketMessage:
    msg = TicketMessage(
        ticket_id=ticket.id, sender=sender, sender_telegram_id=sender_telegram_id, text=text
    )
    session.add(msg)
    ticket.status = TicketStatus.ANSWERED if sender == TicketSender.ADMIN else TicketStatus.OPEN
    await session.flush()
    return msg


async def close_ticket(session: AsyncSession, ticket: SupportTicket) -> None:
    ticket.status = TicketStatus.CLOSED
    await session.flush()


async def get_ticket(session: AsyncSession, ticket_id: int) -> SupportTicket | None:
    return await session.get(SupportTicket, ticket_id)


async def get_open_ticket_for_user(session: AsyncSession, user_id: int) -> SupportTicket | None:
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.user_id == user_id, SupportTicket.status != TicketStatus.CLOSED)
        .order_by(SupportTicket.id.desc())
    )
    return result.scalars().first()


async def list_messages(session: AsyncSession, ticket_id: int) -> list[TicketMessage]:
    result = await session.execute(
        select(TicketMessage).where(TicketMessage.ticket_id == ticket_id).order_by(TicketMessage.id)
    )
    return list(result.scalars().all())


async def list_open_tickets(session: AsyncSession, limit: int = 20) -> list[SupportTicket]:
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.ANSWERED]))
        .order_by(SupportTicket.updated_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())
