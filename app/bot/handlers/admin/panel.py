"""Главное меню админ-панели + раздел статистики."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.filters.admin import IsAdmin
from app.bot.handlers.common import render
from app.bot.keyboards.admin import admin_back_kb, admin_menu_kb
from app.services import stats as stats_service

router = Router(name="admin_panel")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.ADMIN_MENU_HINT, reply_markup=admin_menu_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Универсальная отмена любого админского мастера (добавление ноды/тарифа,
    поиск пользователя, рассылка, ответ на тикет и т.д.) — очищает FSM-состояние
    независимо от того, в каком именно шаге мастера сейчас находится админ.
    Регистрируется на этом (первом в цепочке) роутере, чтобы перехватывать
    команду раньше специфичных для конкретного состояния хендлеров в других
    admin-роутерах.
    """
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Отменено.", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm:menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await render(callback, texts.ADMIN_MENU_HINT, admin_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:stats")
async def cb_admin_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    dashboard = await stats_service.get_dashboard_stats(session)
    await render(callback, texts.admin_dashboard(dashboard), admin_back_kb())
    await callback.answer()
