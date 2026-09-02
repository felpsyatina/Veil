"""Админ: управление тарифами (добавление, вкл/выкл)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.filters.admin import IsAdmin
from app.bot.handlers.common import render
from app.bot.keyboards.admin import admin_back_kb, admin_tariff_card_kb, admin_tariffs_kb
from app.bot.states import AdminTariffAddStates
from app.services import tariffs as tariffs_service

router = Router(name="admin_tariffs")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:tariffs")
async def cb_tariffs_list(callback: CallbackQuery, session: AsyncSession) -> None:
    tariffs = await tariffs_service.list_tariffs(session)
    text = "💳 Тарифы:" if tariffs else "Тарифов пока нет — добавьте первый."
    await render(callback, text, admin_tariffs_kb(tariffs))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:tariffcard:"))
async def cb_tariff_card(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = int(callback.data.split(":")[-1])
    tariff = await tariffs_service.get_tariff(session, tariff_id)
    if tariff is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    await render(callback, texts.admin_tariff_card(tariff), admin_tariff_card_kb(tariff))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:tarifftoggle:"))
async def cb_tariff_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = int(callback.data.split(":")[-1])
    tariff = await tariffs_service.get_tariff(session, tariff_id)
    if tariff is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    await tariffs_service.set_active(session, tariff, not tariff.is_active)
    await render(callback, texts.admin_tariff_card(tariff), admin_tariff_card_kb(tariff))
    await callback.answer()


@router.callback_query(F.data == "adm:tariffadd")
async def cb_tariff_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminTariffAddStates.title)
    await render(callback, texts.ADMIN_TARIFF_ADD_ASK_TITLE, admin_back_kb("adm:tariffs"))
    await callback.answer()


@router.message(AdminTariffAddStates.title, F.text)
async def tariff_add_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminTariffAddStates.days)
    await message.answer(texts.ADMIN_TARIFF_ADD_ASK_DAYS)


@router.message(AdminTariffAddStates.days, F.text)
async def tariff_add_days(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Введите положительное целое число дней:")
        return
    await state.update_data(days=int(raw))
    await state.set_state(AdminTariffAddStates.price)
    await message.answer(texts.ADMIN_TARIFF_ADD_ASK_PRICE)


@router.message(AdminTariffAddStates.price, F.text)
async def tariff_add_price(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = message.text.strip().replace(",", ".")
    try:
        price = Decimal(raw)
        if price <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("Введите цену числом, например 299 или 299.90:")
        return

    data = await state.get_data()
    tariff = await tariffs_service.create_tariff(
        session, title=data["title"], duration_days=data["days"], price=price
    )
    await state.clear()
    await message.answer(
        f"✅ Тариф добавлен: {texts.admin_tariff_card(tariff)}",
        reply_markup=admin_back_kb("adm:tariffs"),
    )
