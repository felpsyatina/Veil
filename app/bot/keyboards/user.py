"""Инлайн-клавиатуры пользовательской части бота."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.texts import tariff_button_label
from app.db.models import Payment, Server, Tariff


def main_menu_kb(*, is_admin: bool, trial_available: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔌 Моя подписка", callback_data="sub:menu")
    b.button(text="🛒 Купить подписку", callback_data="buy:list")
    if trial_available:
        b.button(text="🎁 Пробный период", callback_data="buy:trial")
    b.button(text="🤝 Реферальная программа", callback_data="ref:menu")
    b.button(text="📖 Как подключиться", callback_data="guide:menu")
    b.button(text="💬 Поддержка", callback_data="sup:menu")
    if is_admin:
        b.button(text="⚙️ Админ-панель", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


def back_kb(callback_data: str = "menu:main", text: str = "⬅️ Назад") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=text, callback_data=callback_data)
    return b.as_markup()


def subscription_menu_kb(*, has_subscription: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_subscription:
        b.button(text="📎 Ссылка на подписку", callback_data="sub:link")
        b.button(text="🚀 Автовыбор сервера", callback_data="sub:auto")
        b.button(text="🌍 Выбрать сервер", callback_data="sub:servers")
        b.button(text="🧾 История платежей", callback_data="sub:history")
        b.button(text="🛒 Продлить подписку", callback_data="buy:list")
    else:
        b.button(text="🛒 Купить подписку", callback_data="buy:list")
    b.button(text="⬅️ Назад", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


def tariffs_kb(tariffs: list[Tariff]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in tariffs:
        b.button(text=tariff_button_label(t), callback_data=f"buy:tariff:{t.id}")
    b.button(text="⬅️ Назад", callback_data="sub:menu")
    b.adjust(1)
    return b.as_markup()


def payment_kb(payment: Payment, confirmation_url: str | None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if payment.provider.lower() != "manual" and confirmation_url:
        b.button(text="💳 Оплатить", url=confirmation_url)
        b.button(text="🔄 Проверить оплату", callback_data=f"pay:check:{payment.id}")
    else:
        b.button(text="💬 Написать в поддержку", callback_data="sup:menu")
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


def server_list_kb(servers: list[Server]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in servers:
        b.button(text=s.name, callback_data=f"sub:server:{s.id}")
    b.button(text="⬅️ Назад", callback_data="sub:menu")
    b.adjust(1)
    return b.as_markup()


def guide_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📱 iOS", callback_data="guide:os:ios")
    b.button(text="🤖 Android", callback_data="guide:os:android")
    b.button(text="🖥️ Windows", callback_data="guide:os:windows")
    b.button(text="🍏 macOS", callback_data="guide:os:macos")
    b.button(text="🐧 Linux", callback_data="guide:os:linux")
    b.button(text="⬅️ Назад", callback_data="menu:main")
    b.adjust(2, 2, 1, 1)
    return b.as_markup()


def support_ticket_kb(ticket_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Закрыть обращение", callback_data=f"sup:close:{ticket_id}")
    b.button(text="⬅️ В меню", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()
