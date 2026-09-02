"""Состояния FSM для многошаговых диалогов бота."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SupportStates(StatesGroup):
    waiting_message = State()


class AdminNodeAddStates(StatesGroup):
    name = State()
    country = State()
    host = State()
    port = State()
    panel_url = State()
    panel_user = State()
    panel_pass = State()


class AdminTariffAddStates(StatesGroup):
    title = State()
    days = State()
    price = State()


class AdminUserSearchStates(StatesGroup):
    query = State()


class AdminGrantStates(StatesGroup):
    days = State()


class AdminBroadcastStates(StatesGroup):
    message = State()


class AdminTicketReplyStates(StatesGroup):
    text = State()
