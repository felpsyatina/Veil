"""
Админ: рассылка сообщения всем пользователям.

Отправка с небольшой паузой между сообщениями и обработкой RetryAfter —
у Telegram есть общий лимит на исходящие сообщения, и без троттлинга
рассылка на сотни пользователей упрётся в flood control.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.filters.admin import IsAdmin
from app.bot.handlers.common import render
from app.bot.keyboards.admin import admin_back_kb, admin_broadcast_confirm_kb
from app.bot.states import AdminBroadcastStates
from app.services import users as users_service

logger = logging.getLogger(__name__)
router = Router(name="admin_broadcast")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:bcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBroadcastStates.message)
    await render(callback, texts.ADMIN_BROADCAST_PROMPT, admin_back_kb())
    await callback.answer()


@router.message(AdminBroadcastStates.message, F.text)
async def on_broadcast_text(message: Message, state: FSMContext) -> None:
    await state.update_data(text=message.html_text)
    await message.answer(
        f"Предпросмотр:\n\n{message.html_text}\n\n{texts.ADMIN_BROADCAST_CONFIRM}",
        reply_markup=admin_broadcast_confirm_kb(),
    )


@router.callback_query(AdminBroadcastStates.message, F.data == "adm:bcastsend")
async def cb_broadcast_send(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    data = await state.get_data()
    text = data.get("text")
    await state.clear()
    if not text:
        await callback.answer("Сообщение не найдено, начните заново", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_text("📢 Рассылка запущена, это может занять некоторое время...")

    user_ids = await users_service.list_all_telegram_ids(session)
    sent, failed = 0, 0
    for tg_id in user_ids:
        try:
            await callback.bot.send_message(tg_id, text)
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await callback.bot.send_message(tg_id, text)
                sent += 1
            except Exception:  # noqa: BLE001
                failed += 1
        except TelegramForbiddenError:
            failed += 1  # пользователь заблокировал бота
        except Exception as exc:  # noqa: BLE001
            logger.warning("Broadcast: не удалось отправить %s: %s", tg_id, exc)
            failed += 1
        await asyncio.sleep(0.05)  # ~20 сообщений/сек — с запасом от лимитов Telegram

    await callback.message.answer(
        texts.admin_broadcast_result(sent, failed), reply_markup=admin_back_kb()
    )
