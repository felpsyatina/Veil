"""
Админ: управление нодами.

Добавление ноды — пошаговый мастер (FSM): собираем данные, затем логинимся
на панель 3x-ui, создаём там Reality-инбаунд и сразу раздаём ноду всем, у
кого сейчас есть активный доступ (см. provisioning_service).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.filters.admin import IsAdmin
from app.bot.handlers.common import render
from app.bot.keyboards.admin import (
    admin_back_kb,
    admin_node_card_kb,
    admin_node_delete_confirm_kb,
    admin_nodes_kb,
)
from app.bot.states import AdminNodeAddStates
from app.services import nodes as nodes_service
from app.services import provisioning as provisioning_service

router = Router(name="admin_nodes")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:nodes")
async def cb_nodes_list(callback: CallbackQuery, session: AsyncSession) -> None:
    servers = await nodes_service.list_servers(session)
    text = "🌍 Серверы:" if servers else "Серверов пока нет — добавьте первый."
    await render(callback, text, admin_nodes_kb(servers))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:nodecard:"))
async def cb_node_card(callback: CallbackQuery, session: AsyncSession) -> None:
    server_id = int(callback.data.split(":")[-1])
    server = await nodes_service.get_server(session, server_id)
    if server is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    load = await nodes_service.get_client_count(session, server.id)
    await render(callback, texts.admin_server_card(server, load), admin_node_card_kb(server))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:nodetoggle:"))
async def cb_node_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    server_id = int(callback.data.split(":")[-1])
    server = await nodes_service.get_server(session, server_id)
    if server is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    await nodes_service.set_active(session, server, not server.is_active)
    load = await nodes_service.get_client_count(session, server.id)
    await render(callback, texts.admin_server_card(server, load), admin_node_card_kb(server))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:nodecheck:"))
async def cb_node_check(callback: CallbackQuery, session: AsyncSession) -> None:
    server_id = int(callback.data.split(":")[-1])
    server = await nodes_service.get_server(session, server_id)
    if server is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    healthy, error = await nodes_service.check_node_health(server)
    await nodes_service.set_health(session, server, healthy=healthy, error=error)
    load = await nodes_service.get_client_count(session, server.id)
    await render(callback, texts.admin_server_card(server, load), admin_node_card_kb(server))
    await callback.answer("В строю ✅" if healthy else "Недоступна ❌", show_alert=True)


@router.callback_query(F.data.startswith("adm:nodedelyes:"))
async def cb_node_delete_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    server_id = int(callback.data.split(":")[-1])
    server = await nodes_service.get_server(session, server_id)
    if server is not None:
        await nodes_service.delete_server(session, server)
    await render(callback, "🗑 Сервер удалён.", admin_back_kb("adm:nodes"))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:nodedel:"))
async def cb_node_delete_dialog(callback: CallbackQuery) -> None:
    server_id = int(callback.data.split(":")[-1])
    await render(
        callback,
        "Удалить сервер безвозвратно? Он пропадёт из подписок всех пользователей.",
        admin_node_delete_confirm_kb(server_id),
    )
    await callback.answer()


# --------------------------------------------------------------------------- #
# Мастер добавления ноды
# --------------------------------------------------------------------------- #


@router.callback_query(F.data == "adm:nodeadd")
async def cb_node_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminNodeAddStates.name)
    await render(callback, texts.ADMIN_NODE_ADD_INTRO, admin_back_kb("adm:nodes"))
    await callback.answer()


@router.message(AdminNodeAddStates.name, F.text)
async def node_add_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminNodeAddStates.country)
    await message.answer(texts.ADMIN_NODE_ADD_ASK_COUNTRY)


@router.message(AdminNodeAddStates.country, Command("skip"))
async def node_add_country_skip(message: Message, state: FSMContext) -> None:
    await state.update_data(country=None)
    await state.set_state(AdminNodeAddStates.host)
    await message.answer(texts.ADMIN_NODE_ADD_ASK_HOST)


@router.message(AdminNodeAddStates.country, F.text)
async def node_add_country(message: Message, state: FSMContext) -> None:
    await state.update_data(country=message.text.strip().upper()[:4])
    await state.set_state(AdminNodeAddStates.host)
    await message.answer(texts.ADMIN_NODE_ADD_ASK_HOST)


@router.message(AdminNodeAddStates.host, F.text)
async def node_add_host(message: Message, state: FSMContext) -> None:
    await state.update_data(host=message.text.strip())
    await state.set_state(AdminNodeAddStates.port)
    await message.answer(texts.ADMIN_NODE_ADD_ASK_PORT)


@router.message(AdminNodeAddStates.port, F.text)
async def node_add_port(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 65535):
        await message.answer("Порт должен быть числом от 1 до 65535. Попробуйте ещё раз:")
        return
    await state.update_data(port=int(raw))
    await state.set_state(AdminNodeAddStates.panel_url)
    await message.answer(texts.ADMIN_NODE_ADD_ASK_PANEL_URL)


@router.message(AdminNodeAddStates.panel_url, F.text)
async def node_add_panel_url(message: Message, state: FSMContext) -> None:
    await state.update_data(panel_url=message.text.strip())
    await state.set_state(AdminNodeAddStates.panel_user)
    await message.answer(texts.ADMIN_NODE_ADD_ASK_PANEL_USER)


@router.message(AdminNodeAddStates.panel_user, F.text)
async def node_add_panel_user(message: Message, state: FSMContext) -> None:
    await state.update_data(panel_user=message.text.strip())
    await state.set_state(AdminNodeAddStates.panel_pass)
    await message.answer(texts.ADMIN_NODE_ADD_ASK_PANEL_PASS)


@router.message(AdminNodeAddStates.panel_pass, F.text)
async def node_add_panel_pass(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    panel_password = message.text.strip()

    try:
        await message.delete()  # не оставляем пароль висеть в истории чата
    except Exception:  # noqa: BLE001
        pass

    status_msg = await message.answer(texts.ADMIN_NODE_ADD_CONNECTING)

    try:
        provision = await nodes_service.provision_node_inbound(
            panel_url=data["panel_url"],
            panel_username=data["panel_user"],
            panel_password=panel_password,
            remark=data["name"],
            xray_port=data["port"],
        )
    except Exception as exc:  # noqa: BLE001 — показываем ошибку админу как есть
        await status_msg.edit_text(
            texts.admin_node_add_failed(str(exc)[:300]), reply_markup=admin_back_kb("adm:nodes")
        )
        return

    server = await nodes_service.create_server(
        session,
        name=data["name"],
        country_code=data.get("country"),
        host=data["host"],
        port=data["port"],
        panel_url=data["panel_url"],
        panel_username=data["panel_user"],
        panel_password=panel_password,
        provision=provision,
    )
    synced = await provisioning_service.provision_new_node_for_existing_subscriptions(session, server)
    await state.clear()
    await status_msg.edit_text(
        texts.admin_node_added(server, synced), reply_markup=admin_back_kb("adm:nodes")
    )
