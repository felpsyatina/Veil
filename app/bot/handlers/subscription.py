"""«Моя подписка» (ссылка, автовыбор, список серверов, история) + покупка/триал."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.handlers.common import render
from app.bot.keyboards.user import (
    back_kb,
    payment_kb,
    server_list_kb,
    subscription_menu_kb,
    tariffs_kb,
)
from app.config import settings
from app.db.models import User
from app.services import nodes as nodes_service
from app.services import provisioning as provisioning_service
from app.services import subscription_links as subscription_links_service
from app.services import subscriptions as subscriptions_service
from app.services import tariffs as tariffs_service
from app.services import users as users_service
from app.services.payments import PaymentCreationError, create_payment_for_tariff, list_payment_history
from app.utils.qrcode_gen import make_qr_png

router = Router(name="subscription")


def _has_access(sub) -> bool:
    return sub is not None and sub.status.value in ("active", "trial")


@router.callback_query(F.data == "sub:menu")
async def cb_sub_menu(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    sub = await subscriptions_service.get_by_user(session, user.id)
    await render(callback, texts.subscription_status(sub), subscription_menu_kb(has_subscription=sub is not None))
    await callback.answer()


@router.callback_query(F.data == "sub:link")
async def cb_sub_link(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    sub = await subscriptions_service.get_by_user(session, user.id)
    if not _has_access(sub):
        await callback.answer("Подписка не активна", show_alert=True)
        return
    base = settings.subscription_base_url.rstrip("/")
    link = f"{base}/sub/{sub.subscription_token}"
    await render(callback, texts.subscription_link_message(link), back_kb("sub:menu"))
    await callback.answer()


@router.callback_query(F.data == "sub:auto")
async def cb_sub_auto(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    sub = await subscriptions_service.get_by_user(session, user.id)
    if not _has_access(sub):
        await callback.answer("Подписка не активна", show_alert=True)
        return
    server = await subscription_links_service.pick_auto_server(session, sub)
    if server is None:
        await render(callback, texts.NO_SERVERS_AVAILABLE, back_kb("sub:menu"))
        await callback.answer()
        return
    link = subscription_links_service.build_server_link(server, sub)
    qr = make_qr_png(link)
    await callback.message.answer_photo(
        BufferedInputFile(qr, filename="config.png"),
        caption=texts.single_server_config_message(server, link),
        reply_markup=back_kb("sub:menu"),
    )
    await callback.answer()


@router.callback_query(F.data == "sub:servers")
async def cb_sub_servers(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    sub = await subscriptions_service.get_by_user(session, user.id)
    if not _has_access(sub):
        await callback.answer("Подписка не активна", show_alert=True)
        return
    servers = await subscription_links_service.list_selectable_servers(session, sub)
    if not servers:
        await render(callback, texts.NO_SERVERS_AVAILABLE, back_kb("sub:menu"))
        await callback.answer()
        return
    loads = {s.id: await nodes_service.get_client_count(session, s.id) for s in servers}
    text = "🌍 Доступные серверы:\n\n" + "\n".join(
        texts.server_list_item(s, loads[s.id]) for s in servers
    )
    await render(callback, text, server_list_kb(servers))
    await callback.answer()


@router.callback_query(F.data.startswith("sub:server:"))
async def cb_sub_server_pick(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    server_id = int(callback.data.split(":")[-1])
    sub = await subscriptions_service.get_by_user(session, user.id)
    if not _has_access(sub):
        await callback.answer("Подписка не активна", show_alert=True)
        return
    server = await nodes_service.get_server(session, server_id)
    if server is None:
        await callback.answer("Сервер не найден", show_alert=True)
        return
    link = subscription_links_service.build_server_link(server, sub)
    qr = make_qr_png(link)
    await callback.message.answer_photo(
        BufferedInputFile(qr, filename="config.png"),
        caption=texts.single_server_config_message(server, link),
        reply_markup=back_kb("sub:menu"),
    )
    await callback.answer()


@router.callback_query(F.data == "sub:history")
async def cb_sub_history(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    payments = await list_payment_history(session, user.id)
    if not payments:
        text = texts.PAYMENT_HISTORY_EMPTY
    else:
        text = "🧾 <b>История платежей</b>\n\n" + "\n".join(
            texts.payment_history_item(p) for p in payments
        )
    await render(callback, text, back_kb("sub:menu"))
    await callback.answer()


@router.callback_query(F.data == "buy:list")
async def cb_buy_list(callback: CallbackQuery, session: AsyncSession) -> None:
    tariffs = await tariffs_service.list_tariffs(session, only_active=True)
    if not tariffs:
        await callback.answer("Тарифы временно недоступны, загляните позже", show_alert=True)
        return
    await render(callback, texts.choose_tariff_prompt(), tariffs_kb(tariffs))
    await callback.answer()


@router.callback_query(F.data == "buy:trial")
async def cb_buy_trial(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    if user.trial_used or await subscriptions_service.get_by_user(session, user.id) is not None:
        await callback.answer(texts.TRIAL_ALREADY_USED, show_alert=True)
        return
    sub = await subscriptions_service.create_trial(session, user)
    await users_service.mark_trial_used(session, user)
    await provisioning_service.provision_on_all_active_servers(session, sub, user.telegram_id)
    await render(callback, texts.trial_activated(sub.expires_at), back_kb("menu:main"))
    await callback.answer()


@router.callback_query(F.data.startswith("buy:tariff:"))
async def cb_buy_tariff(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    tariff_id = int(callback.data.split(":")[-1])
    tariff = await tariffs_service.get_tariff(session, tariff_id)
    if tariff is None or not tariff.is_active:
        await callback.answer("Тариф недоступен", show_alert=True)
        return

    try:
        payment, result = await create_payment_for_tariff(session, user, tariff, use_balance=True)
    except PaymentCreationError:
        await render(callback, texts.ERROR_GENERIC, back_kb("sub:menu"))
        await callback.answer()
        return

    if result is None:
        await render(
            callback,
            texts.payment_fully_covered_by_balance(payment.applied_balance),
            back_kb("menu:main"),
        )
    elif payment.provider.lower() == "manual":
        await render(callback, texts.payment_created_manual(payment), payment_kb(payment, None))
    else:
        await render(
            callback,
            texts.payment_created_gateway(payment, result.confirmation_url),
            payment_kb(payment, result.confirmation_url),
        )
    await callback.answer()
