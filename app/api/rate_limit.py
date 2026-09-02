"""Общий экземпляр Limiter — в отдельном модуле, чтобы routes/*.py и main.py
могли импортировать его без циклических зависимостей."""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
