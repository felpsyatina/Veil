"""Тарифы — хранятся в БД, чтобы админ мог добавлять/менять их без деплоя."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tariff


async def list_tariffs(session: AsyncSession, *, only_active: bool = False) -> list[Tariff]:
    stmt = select(Tariff).order_by(Tariff.sort_order, Tariff.id)
    if only_active:
        stmt = stmt.where(Tariff.is_active.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_tariff(session: AsyncSession, tariff_id: int) -> Tariff | None:
    return await session.get(Tariff, tariff_id)


async def create_tariff(
    session: AsyncSession, *, title: str, duration_days: int, price: Decimal, sort_order: int = 0
) -> Tariff:
    tariff = Tariff(title=title, duration_days=duration_days, price=price, sort_order=sort_order)
    session.add(tariff)
    await session.flush()
    return tariff


async def set_active(session: AsyncSession, tariff: Tariff, active: bool) -> None:
    tariff.is_active = active
    await session.flush()


async def update_price(session: AsyncSession, tariff: Tariff, price: Decimal) -> None:
    tariff.price = price
    await session.flush()
