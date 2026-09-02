"""Админ: поиск пользователя, бан/разбан, ручная выдача/продление подписки."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.filters.admin import IsAdmin
from app.bot.handlers.common import render
from app.bot.keyboards.admin import admin_back_kb, admin_user_card_kb
from app.bot.states import AdminGrantStates, AdminUserSearchStates
from app.services import provisioning as provisioning_service
from app.services import subscriptions as subscriptions_service
from app.services import users as users_service

router = Router(name="admin_users")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _show_user_card(target, session: AsyncSession):
    sub = await subscriptions_service.get_by_user(session, target.id)
    return texts.admin_user_card(target, sub), admin_user_card_kb(target)


@router.callback_query(F.data == "adm:users")
async def cb_users_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminUserSearchStates.query)
    await render(callback, texts.ADMIN_USER_SEARCH_PROMPT, admin_back_kb())
    await callback.answer()


@router.message(AdminUserSearchStates.query, F.text)
async def on_user_search(message: Message, session: AsyncSession, state: FSMContext) -> None:
    target = await users_service.find_by_query(session, message.text)
    if target is None:
        await message.answer(texts.ADMIN_USER_NOT_FOUND)
        return
    await state.clear()
    text, kb = await _show_user_card(target, session)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:userban:"))
async def cb_user_ban(callback: CallbackQuery, session: AsyncSession) -> None:
    user_id = int(callback.data.split(":")[-1])
    target = await users_service.get_by_id(session, user_id)
    if target is None:
        await callback.answer("Не найден", show_alert=True)
        return
    await users_service.set_banned(session, target, True)
    text, kb = await _show_user_card(target, session)
    await render(callback, text, kb)
    await callback.answer(texts.admin_user_banned(target))


@router.callback_query(F.data.startswith("adm:userunban:"))
async def cb_user_unban(callback: CallbackQuery, session: AsyncSession) -> None:
    user_id = int(callback.data.split(":")[-1])
    target = await users_service.get_by_id(session, user_id)
    if target is None:
        await callback.answer("Не найден", show_alert=True)
        return
    await users_service.set_banned(session, target, False)
    text, kb = await _show_user_card(target, session)
    await render(callback, text, kb)
    await callback.answer(texts.admin_user_unbanned(target))


@router.callback_query(F.data.startswith("adm:usergrant:"))
async def cb_user_grant_start(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = int(callback.data.split(":")[-1])
    await state.set_state(AdminGrantStates.days)
    await state.update_data(user_id=user_id)
    await render(callback, texts.ADMIN_GRANT_ASK_DAYS, admin_back_kb())
    await callback.answer()


@router.message(AdminGrantStates.days, F.text)
async def on_grant_days(message: Message, session: AsyncSession, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.lstrip("-").isdigit() or int(raw) == 0:
        await message.answer("Введите ненулевое целое число дней:")
        return
    days = int(raw)
    data = await state.get_data()
    target = await users_service.get_by_id(session, data["user_id"])
    if target is None:
        await message.answer(texts.ADMIN_USER_NOT_FOUND)
        await state.clear()
        return

    sub = await subscriptions_service.get_or_create_for_purchase(session, target)
    await subscriptions_service.extend_days(session, sub, days)
    await provisioning_service.sync_subscription_everywhere(session, sub, target.telegram_id)
    await state.clear()

    await message.answer(texts.admin_grant_done(sub), reply_markup=admin_user_card_kb(target))
    try:
        await message.bot.send_message(
            target.telegram_id,
            f"🎁 Администратор изменил срок вашей подписки. {texts.admin_grant_done(sub)}",
        )
    except Exception:  # noqa: BLE001 — пользователь мог заблокировать бота
        pass
