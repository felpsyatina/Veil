"""/start и главное меню."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import texts
from app.bot.handlers.common import render
from app.bot.keyboards.user import main_menu_kb
from app.config import settings
from app.db.models import User

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, user_created: bool, state: FSMContext) -> None:
    await state.clear()
    is_admin = message.from_user.id in settings.admin_ids
    text = texts.WELCOME if user_created else texts.welcome_back(user.full_name)
    await message.answer(
        text,
        reply_markup=main_menu_kb(is_admin=is_admin, trial_available=not user.trial_used),
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery, user: User, state: FSMContext) -> None:
    await state.clear()
    is_admin = callback.from_user.id in settings.admin_ids
    await render(
        callback,
        texts.MAIN_MENU_HINT,
        main_menu_kb(is_admin=is_admin, trial_available=not user.trial_used),
    )
    await callback.answer()
