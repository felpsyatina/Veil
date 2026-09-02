"""
Инлайн-клавиатуры админ-панели.

callback_data специально использует непересекающиеся префиксы
(adm:nodecard: / adm:nodetoggle: / adm:nodedel: и т.д.), а не общий
adm:node:<действие>:<id> — так каждый хендлер матчится строго через
startswith() без риска зацепить чужой колбэк с тем же префиксом.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.texts import admin_tariff_card
from app.db.models import Payment, Server, SupportTicket, Tariff, User


def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика", callback_data="adm:stats")
    b.button(text="🌍 Серверы", callback_data="adm:nodes")
    b.button(text="💳 Тарифы", callback_data="adm:tariffs")
    b.button(text="🧾 Ожидают оплаты", callback_data="adm:pending")
    b.button(text="👤 Пользователи", callback_data="adm:users")
    b.button(text="💬 Тикеты", callback_data="adm:tickets")
    b.button(text="📢 Рассылка", callback_data="adm:bcast")
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


def admin_back_kb(callback_data: str = "adm:menu") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=callback_data)
    return b.as_markup()


def admin_nodes_kb(servers: list[Server]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in servers:
        dot = "🟢" if s.is_active and s.is_healthy else ("⚪" if not s.is_active else "🔴")
        b.button(text=f"{dot} {s.name}", callback_data=f"adm:nodecard:{s.id}")
    b.button(text="➕ Добавить ноду", callback_data="adm:nodeadd")
    b.button(text="⬅️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def admin_node_card_kb(server: Server) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    toggle_text = "⏸ Отключить" if server.is_active else "▶️ Включить"
    b.button(text=toggle_text, callback_data=f"adm:nodetoggle:{server.id}")
    b.button(text="🔄 Проверить доступность", callback_data=f"adm:nodecheck:{server.id}")
    b.button(text="🗑 Удалить", callback_data=f"adm:nodedel:{server.id}")
    b.button(text="⬅️ Назад", callback_data="adm:nodes")
    b.adjust(1)
    return b.as_markup()


def admin_node_delete_confirm_kb(server_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❗️ Да, удалить", callback_data=f"adm:nodedelyes:{server_id}")
    b.button(text="Отмена", callback_data=f"adm:nodecard:{server_id}")
    b.adjust(1)
    return b.as_markup()


def admin_tariffs_kb(tariffs: list[Tariff]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in tariffs:
        b.button(text=admin_tariff_card(t), callback_data=f"adm:tariffcard:{t.id}")
    b.button(text="➕ Добавить тариф", callback_data="adm:tariffadd")
    b.button(text="⬅️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def admin_tariff_card_kb(tariff: Tariff) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    toggle_text = "⏸ Отключить" if tariff.is_active else "▶️ Включить"
    b.button(text=toggle_text, callback_data=f"adm:tarifftoggle:{tariff.id}")
    b.button(text="⬅️ Назад", callback_data="adm:tariffs")
    b.adjust(1)
    return b.as_markup()


def admin_user_card_kb(user: User) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    ban_text = "✅ Разбанить" if user.is_banned else "🚫 Забанить"
    ban_cb = f"adm:userunban:{user.id}" if user.is_banned else f"adm:userban:{user.id}"
    b.button(text=ban_text, callback_data=ban_cb)
    b.button(text="🎁 Выдать/продлить подписку", callback_data=f"adm:usergrant:{user.id}")
    b.button(text="⬅️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def admin_pending_payments_kb(payments: list[Payment]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for p in payments:
        amount = p.amount - p.applied_balance
        b.button(text=f"#{p.id} · {amount} ₽", callback_data=f"adm:paycard:{p.id}")
    b.button(text="⬅️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def admin_payment_card_kb(payment_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить оплату", callback_data=f"adm:payconfirm:{payment_id}")
    b.button(text="❌ Отклонить", callback_data=f"adm:paycancel:{payment_id}")
    b.button(text="⬅️ Назад", callback_data="adm:pending")
    b.adjust(1)
    return b.as_markup()


def admin_tickets_kb(tickets: list[SupportTicket], labels: dict[int, str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in tickets:
        label = labels.get(t.id, str(t.id))
        b.button(text=f"#{t.id} · {label}", callback_data=f"adm:ticketcard:{t.id}")
    b.button(text="⬅️ Назад", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def admin_ticket_card_kb(ticket_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✍️ Ответить", callback_data=f"adm:ticketreply:{ticket_id}")
    b.button(text="✅ Закрыть", callback_data=f"adm:ticketclose:{ticket_id}")
    b.button(text="⬅️ Назад", callback_data="adm:tickets")
    b.adjust(1)
    return b.as_markup()


def admin_broadcast_confirm_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Отправить всем", callback_data="adm:bcastsend")
    b.button(text="❌ Отмена", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()
