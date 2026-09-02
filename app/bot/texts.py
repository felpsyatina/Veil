"""
Все пользовательские тексты бота в одном месте.

Бот одноязычный (русский, см. ТЗ), поэтому полноценный i18n не нужен — но
тексты всё равно вынесены сюда отдельно от хендлеров, чтобы их было легко
найти и поправить, а при необходимости в будущем добавить второй язык.

parse_mode для бота — HTML (см. app/bot/loader.py), поэтому здесь используется
разметка <b>/<i>/<code>, а не Markdown.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.config import settings
from app.db.models import Payment, Server, Subscription, Tariff, User
from app.utils.formatting import days_left, format_dt, format_money

# --------------------------------------------------------------------------- #
# Общее
# --------------------------------------------------------------------------- #

WELCOME = (
    "👋 Привет! Это приватный VPN-сервис.\n\n"
    "🔒 Быстрое и незаметное подключение (VLESS + Reality)\n"
    "🌍 Несколько серверов в одной подписке\n"
    "♾️ Безлимитный трафик\n\n"
    "Выберите действие в меню ниже."
)

BANNED = "🚫 Ваш доступ ограничен. Если считаете, что это ошибка — напишите в поддержку."

ERROR_GENERIC = "⚠️ Что-то пошло не так. Попробуйте ещё раз чуть позже."

MAIN_MENU_HINT = "Выберите раздел:"


def welcome_back(name: str | None) -> str:
    return f"С возвращением{f', {name}' if name else ''}! 👋"


# --------------------------------------------------------------------------- #
# Подписка / тарифы
# --------------------------------------------------------------------------- #

NO_SUBSCRIPTION = (
    "У вас пока нет подписки.\n\n"
    f"🎁 Доступен бесплатный пробный период — {settings.trial_days} дня.\n"
    "Или выберите тариф в разделе «Купить подписку»."
)

TRIAL_ALREADY_USED = "Пробный период уже был использован на этом аккаунте."


def trial_activated(expires_at: dt.datetime) -> str:
    return (
        "🎁 Пробный период активирован!\n\n"
        f"Действует до: <b>{format_dt(expires_at)}</b>\n\n"
        "Откройте «🔌 Моя подписка», чтобы получить ссылку для подключения."
    )


def choose_tariff_prompt() -> str:
    return "Выберите срок подписки:"


def tariff_button_label(tariff: Tariff) -> str:
    return f"{tariff.title} — {format_money(tariff.price)}"


def subscription_status(sub: Subscription | None) -> str:
    if sub is None:
        return NO_SUBSCRIPTION

    status_labels = {
        "trial": "🎁 Пробный период",
        "active": "✅ Активна",
        "expired": "❌ Истекла",
        "cancelled": "🚫 Отменена",
    }
    label = status_labels.get(sub.status.value, sub.status.value)
    lines = [
        f"Статус: <b>{label}</b>",
        f"Действует до: <b>{format_dt(sub.expires_at)}</b>",
    ]
    if sub.status.value in ("active", "trial"):
        left = days_left(sub.expires_at)
        lines.append(f"Осталось дней: <b>{left}</b>")
    lines.append(f"Лимит устройств: <b>{sub.device_limit}</b>")
    return "\n".join(lines)


SUBSCRIPTION_MENU_HINT = "Что дальше?"

NO_SERVERS_AVAILABLE = (
    "Сейчас нет доступных серверов — мы уже знаем и разбираемся. "
    "Загляните чуть позже или напишите в поддержку."
)


def subscription_link_message(link: str) -> str:
    return (
        "📎 <b>Ссылка на подписку</b>\n\n"
        f"<code>{link}</code>\n\n"
        "Вставьте её в приложение (v2rayNG, NekoBox, Streisand, v2rayN и т.д.) "
        "через «Импорт по ссылке» / «Add subscription» — и в приложении появятся "
        "сразу все доступные серверы. Как это сделать на вашей платформе — "
        "смотрите в разделе «📖 Как подключиться»."
    )


def single_server_config_message(server: Server, link: str) -> str:
    flag = f"{server.country_code} " if server.country_code else ""
    return (
        f"🌍 <b>{server.name}</b>\n\n"
        f"<code>{link}</code>\n\n"
        "Скопируйте ссылку целиком и импортируйте в приложение, либо отсканируйте QR ниже."
    )


def server_list_item(server: Server, load: int) -> str:
    dot = "🟢" if server.is_healthy else "🔴"
    return f"{dot} {server.name} · клиентов: {load}"


# --------------------------------------------------------------------------- #
# Оплата
# --------------------------------------------------------------------------- #


def payment_created_manual(payment: Payment) -> str:
    return (
        f"💳 Счёт на <b>{format_money(payment.amount - payment.applied_balance)}</b> создан.\n\n"
        "Способ оплаты пока настраивается вручную — свяжитесь с поддержкой, чтобы "
        "получить актуальные реквизиты, укажите номер платежа "
        f"<code>#{payment.id}</code>. После получения оплаты администратор "
        "подтвердит её, и подписка продлится автоматически."
    )


def payment_created_gateway(payment: Payment, confirmation_url: str) -> str:
    return (
        f"💳 К оплате: <b>{format_money(payment.amount - payment.applied_balance)}</b>\n\n"
        "Нажмите «Оплатить» ниже. После оплаты вернитесь в бота — статус обновится "
        "автоматически, либо нажмите «Проверить оплату»."
    )


def payment_fully_covered_by_balance(applied: Decimal) -> str:
    return (
        f"✅ Оплата полностью списана с бонусного баланса ({format_money(applied)}).\n"
        "Подписка уже продлена!"
    )


PAYMENT_SUCCESS = "✅ Оплата получена! Подписка продлена."
PAYMENT_STILL_PENDING = "⏳ Оплата ещё не поступила. Если вы уже оплатили — подождите немного и проверьте снова."
PAYMENT_CANCELLED = "❌ Платёж отменён."
PAYMENT_NOT_FOUND = "Платёж не найден."


def payment_history_item(payment: Payment) -> str:
    status_labels = {
        "pending": "⏳ ожидает оплаты",
        "succeeded": "✅ оплачен",
        "failed": "⚠️ ошибка",
        "cancelled": "🚫 отменён",
    }
    label = status_labels.get(payment.status.value, payment.status.value)
    return (
        f"#{payment.id} · {format_money(payment.amount)} · {label} · "
        f"{format_dt(payment.created_at)}"
    )


PAYMENT_HISTORY_EMPTY = "Платежей пока не было."

USE_BALANCE_PROMPT = "Списать бонусный баланс при оплате?"


def balance_info(user: User) -> str:
    return f"Бонусный баланс: <b>{format_money(user.referral_balance)}</b>"


# --------------------------------------------------------------------------- #
# Реферальная программа
# --------------------------------------------------------------------------- #


def referral_info(user: User, bot_username: str, invited_count: int) -> str:
    link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}"
    return (
        "🤝 <b>Реферальная программа</b>\n\n"
        f"За каждую оплату приглашённого пользователя вы получаете "
        f"<b>{settings.referral_percent}%</b> на бонусный баланс — им можно "
        "оплачивать свою подписку частично или полностью.\n\n"
        f"Ваша ссылка:\n<code>{link}</code>\n\n"
        f"Приглашено пользователей: <b>{invited_count}</b>\n"
        f"Бонусный баланс: <b>{format_money(user.referral_balance)}</b>"
    )


# --------------------------------------------------------------------------- #
# Поддержка
# --------------------------------------------------------------------------- #

SUPPORT_INTRO = (
    "💬 Опишите проблему одним сообщением — мы ответим прямо здесь, в боте. "
    f"Если что-то срочное, можно также написать {settings.support_username}."
)
SUPPORT_TICKET_CREATED = "✅ Обращение создано. Мы ответим здесь, как только сможем."
SUPPORT_MESSAGE_SENT = "✅ Сообщение отправлено."
SUPPORT_TICKET_CLOSED = "Обращение закрыто. Если вопрос снова возникнет — просто напишите ещё раз."
SUPPORT_NEW_REPLY_NOTICE = "💬 Вам ответили в поддержке:"
SUPPORT_HAS_OPEN_TICKET = "У вас уже есть открытое обращение — просто напишите сообщение, и оно попадёт туда же."


# --------------------------------------------------------------------------- #
# Гайд подключения
# --------------------------------------------------------------------------- #

GUIDE_INTRO = "Выберите вашу платформу:"

GUIDE_IOS = (
    "📱 <b>iOS</b>\n\n"
    "1. Установите приложение <b>Streisand</b> или <b>V2Box</b> из App Store.\n"
    "2. Скопируйте ссылку на подписку (кнопка ниже в разделе «Моя подписка»).\n"
    "3. В приложении: «+» → «Add Subscription» / «Import from clipboard».\n"
    "4. Вставьте ссылку, сохраните — появится список серверов.\n"
    "5. Выберите сервер и нажмите «Connect»."
)

GUIDE_ANDROID = (
    "🤖 <b>Android</b>\n\n"
    "1. Установите <b>v2rayNG</b> или <b>NekoBox for Android</b> (Google Play / GitHub).\n"
    "2. Скопируйте ссылку на подписку.\n"
    "3. В приложении: значок «+» → «Import config from clipboard» "
    "или отдельный пункт «Subscription group» → «Update».\n"
    "4. Выберите сервер и нажмите на кнопку подключения."
)

GUIDE_WINDOWS = (
    "🖥️ <b>Windows</b>\n\n"
    "1. Установите <b>v2rayN</b> (github.com/2dust/v2rayN) или <b>NekoRay</b>.\n"
    "2. Скопируйте ссылку на подписку.\n"
    "3. В программе: «Subscriptions» → «Edit subscriptions» → добавить ссылку → «Update».\n"
    "4. Выберите сервер из списка и нажмите «Set as active» → включите системный прокси/TUN."
)

GUIDE_MACOS = (
    "🍏 <b>macOS</b>\n\n"
    "1. Установите <b>V2Box</b> или <b>Streisand</b> (App Store).\n"
    "2. Скопируйте ссылку на подписку.\n"
    "3. Добавьте её как подписку в приложении (аналогично iOS).\n"
    "4. Выберите сервер и подключитесь."
)

GUIDE_LINUX = (
    "🐧 <b>Linux</b>\n\n"
    "1. Установите клиент с поддержкой Xray/VLESS+Reality, например <b>NekoRay</b> "
    "(github.com/MatsuriDayo/nekoray) или <b>v2rayA</b>.\n"
    "2. Импортируйте ссылку на подписку так же, как на Windows.\n"
    "3. Выберите сервер и включите подключение."
)

GUIDE_QR_HINT = "Также можно отсканировать QR-код конкретного сервера — он доступен в разделе «Моя подписка» → «Выбрать сервер»."


# --------------------------------------------------------------------------- #
# Уведомления (от воркера)
# --------------------------------------------------------------------------- #


def notify_expiring(sub: Subscription, threshold_days: int) -> str:
    word = "день" if threshold_days == 1 else "дня" if threshold_days < 5 else "дней"
    return (
        f"⏰ Подписка заканчивается через {threshold_days} {word} "
        f"({format_dt(sub.expires_at)}).\n\n"
        "Продлите заранее, чтобы не потерять доступ — автопродления нет."
    )


NOTIFY_EXPIRED = (
    "❌ Срок подписки истёк, доступ отключён.\n\n"
    "Продлите подписку в любой момент — конфиги останутся теми же, ничего "
    "перенастраивать не придётся."
)

NOTIFY_TRIAL_EXPIRED = (
    "🎁 Пробный период закончился.\n\n"
    "Понравилось? Оформите подписку в разделе «Купить подписку»."
)


def admin_node_down_alert(server: Server, error: str | None) -> str:
    return (
        f"🔴 Нода <b>{server.name}</b> недоступна.\n"
        f"{f'Ошибка: <code>{error}</code>' if error else ''}\n"
        "Она автоматически исключена из выдачи пользователям до восстановления."
    )


def admin_node_up_alert(server: Server) -> str:
    return f"🟢 Нода <b>{server.name}</b> снова в строю."


# --------------------------------------------------------------------------- #
# Админ
# --------------------------------------------------------------------------- #

ADMIN_MENU_HINT = "Админ-панель:"

ADMIN_ACCESS_DENIED = "Эта команда доступна только администраторам."


def admin_dashboard(stats) -> str:  # stats: app.services.stats.DashboardStats
    return (
        "📊 <b>Статистика</b>\n\n"
        f"👤 Пользователей: <b>{stats.total_users}</b> (забанено: {stats.banned_users})\n"
        f"🆕 Новых сегодня: <b>{stats.new_users_today}</b>\n\n"
        f"✅ Активных подписок: <b>{stats.active_subscriptions}</b>\n"
        f"🎁 На пробном периоде: <b>{stats.trial_subscriptions}</b>\n\n"
        f"💰 Выручка сегодня: <b>{format_money(stats.revenue_today)}</b>\n"
        f"💰 За неделю: <b>{format_money(stats.revenue_week)}</b>\n"
        f"💰 За месяц: <b>{format_money(stats.revenue_month)}</b>\n"
        f"💰 Всего: <b>{format_money(stats.revenue_total)}</b>\n"
        f"🧾 Платежей сегодня: <b>{stats.payments_today}</b>\n\n"
        f"🌍 Серверов: <b>{stats.servers_total}</b> (в строю: {stats.servers_healthy})\n"
        f"💬 Открытых тикетов: <b>{stats.open_tickets}</b>"
    )


def admin_server_card(server: Server, load: int) -> str:
    status = "🟢 активна и в строю" if server.is_active and server.is_healthy else (
        "⚪ отключена админом" if not server.is_active else "🔴 не в строю"
    )
    return (
        f"<b>{server.name}</b> ({server.country_code or '—'})\n"
        f"Статус: {status}\n"
        f"Адрес: <code>{server.host}:{server.port}</code>\n"
        f"Панель: <code>{server.panel_url}</code>\n"
        f"Клиентов на ноде: <b>{load}</b>\n"
        f"Последняя проверка: {format_dt(server.last_check_at) if server.last_check_at else '—'}"
    )


ADMIN_NODE_ADD_INTRO = (
    "➕ <b>Добавление ноды</b>\n\n"
    "Сначала разверните 3x-ui на новом сервере скриптом "
    "<code>deploy/node/install_node.sh</code> (см. README) — он выведет адрес "
    "панели и логин/пароль.\n\n"
    "Отправьте название сервера (например: «🇳🇱 Amsterdam-1»):"
)
ADMIN_NODE_ADD_ASK_COUNTRY = "Код страны (например NL, DE, RU) — можно пропустить командой /skip:"
ADMIN_NODE_ADD_ASK_HOST = "Адрес сервера (домен или IP), который увидят клиенты:"
ADMIN_NODE_ADD_ASK_PORT = "Порт, на котором будет слушать VLESS (например 443):"
ADMIN_NODE_ADD_ASK_PANEL_URL = "Полный URL панели 3x-ui (например https://1.2.3.4:2053/somepath):"
ADMIN_NODE_ADD_ASK_PANEL_USER = "Логин панели:"
ADMIN_NODE_ADD_ASK_PANEL_PASS = "Пароль панели:"
ADMIN_NODE_ADD_CONNECTING = "🔄 Подключаюсь к панели и создаю Reality-инбаунд, подождите..."


def admin_node_added(server: Server, synced_count: int) -> str:
    return (
        f"✅ Нода <b>{server.name}</b> добавлена и настроена.\n"
        f"Подписка автоматически выдана на неё {synced_count} активным пользователям."
    )


def admin_node_add_failed(error: str) -> str:
    return (
        f"❌ Не удалось создать инбаунд на панели: <code>{error}</code>\n\n"
        "Проверьте адрес панели, логин/пароль и доступность порта, затем попробуйте снова "
        "(/cancel — отменить)."
    )


ADMIN_TARIFF_ADD_ASK_TITLE = "Название тарифа (например «6 месяцев»):"
ADMIN_TARIFF_ADD_ASK_DAYS = "Длительность в днях:"
ADMIN_TARIFF_ADD_ASK_PRICE = "Цена в рублях:"


def admin_tariff_card(tariff: Tariff) -> str:
    status = "🟢 активен" if tariff.is_active else "⚪ отключён"
    return f"{tariff.title} · {format_money(tariff.price)} · {tariff.duration_days} дн. · {status}"


ADMIN_USER_SEARCH_PROMPT = "Введите Telegram ID или @username пользователя:"
ADMIN_USER_NOT_FOUND = "Пользователь не найден."


def admin_user_card(user: User, sub: Subscription | None) -> str:
    lines = [
        f"👤 <b>{user.full_name or '—'}</b> (@{user.username or '—'})",
        f"ID: <code>{user.telegram_id}</code>",
        f"Регистрация: {format_dt(user.created_at)}",
        f"Забанен: {'да' if user.is_banned else 'нет'}",
        f"Бонусный баланс: {format_money(user.referral_balance)}",
    ]
    if sub is not None:
        lines.append(f"Подписка: {sub.status.value}, до {format_dt(sub.expires_at)}")
    else:
        lines.append("Подписка: отсутствует")
    return "\n".join(lines)


ADMIN_GRANT_ASK_DAYS = "На сколько дней выдать/продлить подписку? (можно отрицательное число, чтобы сократить)"


def admin_grant_done(sub: Subscription) -> str:
    return f"✅ Готово. Подписка активна до <b>{format_dt(sub.expires_at)}</b>."


def admin_payment_card(payment: Payment, user: User) -> str:
    return (
        f"🧾 <b>Платёж #{payment.id}</b>\n"
        f"Пользователь: @{user.username or '—'} (ID <code>{user.telegram_id}</code>)\n"
        f"К оплате: <b>{format_money(payment.amount - payment.applied_balance)}</b>\n"
        f"Описание: {payment.description or '—'}\n"
        f"Создан: {format_dt(payment.created_at)}"
    )


PENDING_PAYMENTS_EMPTY = "Платежей, ожидающих подтверждения, нет."


def admin_user_banned(user: User) -> str:
    return f"🚫 Пользователь {user.telegram_id} забанен."


def admin_user_unbanned(user: User) -> str:
    return f"✅ Пользователь {user.telegram_id} разбанен."


ADMIN_BROADCAST_PROMPT = "Отправьте сообщение, которое нужно разослать всем пользователям (текст, можно с HTML-разметкой):"
ADMIN_BROADCAST_CONFIRM = "Разослать это сообщение всем пользователям?"


def admin_broadcast_result(sent: int, failed: int) -> str:
    return f"✅ Рассылка завершена. Доставлено: {sent}, не доставлено: {failed}."


ADMIN_TICKETS_EMPTY = "Открытых обращений нет."


def admin_ticket_card(ticket_id: int, user: User) -> str:
    return f"#{ticket_id} · @{user.username or user.telegram_id}"


ADMIN_TICKET_REPLY_PROMPT = "Введите ответ пользователю:"
