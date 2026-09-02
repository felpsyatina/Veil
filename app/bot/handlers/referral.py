"""Раздел «Реферальная программа»."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.handlers.common import render
from app.bot.keyboards.user import back_kb
from app.db.models import User
from app.services import users as users_service

router = Router(name="referral")


@router.callback_query(F.data == "ref:menu")
async def cb_referral_menu(
    callback: CallbackQuery, user: User, session: AsyncSession, bot_username: str
) -> None:
    invited_count = await users_service.count_referred(session, user.id)
    text = texts.referral_info(user, bot_username, invited_count)
    await render(callback, text, back_kb("menu:main"))
    await callback.answer()
