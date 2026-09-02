"""Раздел «Как подключиться» — пошаговый гайд по платформам."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot import texts
from app.bot.handlers.common import render
from app.bot.keyboards.user import back_kb, guide_menu_kb

router = Router(name="help_guide")

_GUIDE_TEXTS = {
    "ios": texts.GUIDE_IOS,
    "android": texts.GUIDE_ANDROID,
    "windows": texts.GUIDE_WINDOWS,
    "macos": texts.GUIDE_MACOS,
    "linux": texts.GUIDE_LINUX,
}


@router.callback_query(F.data == "guide:menu")
async def cb_guide_menu(callback: CallbackQuery) -> None:
    await render(callback, texts.GUIDE_INTRO, guide_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("guide:os:"))
async def cb_guide_os(callback: CallbackQuery) -> None:
    os_key = callback.data.split(":")[-1]
    body = _GUIDE_TEXTS.get(os_key, texts.GUIDE_INTRO)
    await render(callback, f"{body}\n\n{texts.GUIDE_QR_HINT}", back_kb("guide:menu"))
    await callback.answer()
