"""
Асинхронный клиент к API панели 3x-ui (MHSanaei/3x-ui).

⚠️ ВАЖНО ПРО СОВМЕСТИМОСТЬ API
3x-ui — активно развивающийся проект с несколькими форками, и в отличие от
эндпоинтов CRUD над инбаундами/клиентами (они стабильны и задокументированы
в официальной wiki: Configuration → API), путь создания Reality-инбаунда
собран по официальной схеме xray-core (поля settings/streamSettings/sniffing
хранятся как JSON-строки). Прежде чем полагаться на это в проде:
  1. Разверните один тестовый инбаунд руками через веб-панель.
  2. Откройте DevTools → Network при сохранении и сверьте тело запроса
     POST /panel/api/inbounds/add с payload в create_reality_inbound() ниже.
  3. Поправьте при необходимости — вся сборка payload сосредоточена в одном
     месте специально для этого.

Документированные (подтверждённые) эндпоинты (wiki проекта, раздел
Configuration → API):
    POST /login
    GET  /panel/api/inbounds/list
    GET  /panel/api/inbounds/get/:id
    GET  /panel/api/inbounds/getClientTraffics/:email
    POST /panel/api/inbounds/add
    POST /panel/api/inbounds/del/:id
    POST /panel/api/inbounds/update/:id
    POST /panel/api/inbounds/addClient
    POST /panel/api/inbounds/clearClientIps/:email

updateClient / delClient ниже реализованы по устоявшемуся в проекте паттерну
(используется сторонними обёртками — Node.js/PHP клиентами к 3x-ui), но не
были явно перечислены в обрезанной версии таблицы wiki — тоже стоит сверить
при первом запуске.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from dataclasses import dataclass, field

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class XUIError(Exception):
    """Панель ответила success=false или вернула некорректные данные."""


class XUIConnectionError(XUIError):
    """Сетевая ошибка / панель недоступна после повторных попыток."""


_RETRYABLE = (httpx.TransportError, httpx.TimeoutException)


@dataclass
class XUIClientConfig:
    """Описание одного VLESS-клиента внутри инбаунда 3x-ui."""

    id: str  # UUID клиента (совпадает с Subscription.xui_uuid)
    email: str
    flow: str = "xtls-rprx-vision"
    limit_ip: int = 1
    total_gb: int = 0  # 0 = без лимита трафика
    expiry_time_ms: int = 0  # unix ms, 0 = без ограничения по времени
    enable: bool = True
    tg_id: str = ""
    sub_id: str = ""
    comment: str = ""
    reset: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "flow": self.flow,
            "email": self.email,
            "limitIp": self.limit_ip,
            "totalGB": self.total_gb,
            "expiryTime": self.expiry_time_ms,
            "enable": self.enable,
            "tgId": self.tg_id,
            "subId": self.sub_id,
            "comment": self.comment,
            "reset": self.reset,
        }


@dataclass
class RealityInboundResult:
    inbound_id: int
    raw: dict = field(default_factory=dict)


class XUIClient:
    """Клиент к одной ноде (одному инстансу панели 3x-ui).

    Использование:
        async with XUIClient(panel_url, username, password) as xui:
            await xui.add_client(inbound_id, client_cfg)
    """

    def __init__(self, panel_url: str, username: str, password: str, timeout: float = 15.0):
        self._username = username
        self._password = password
        self._client = httpx.AsyncClient(
            base_url=panel_url.rstrip("/"),
            timeout=timeout,
            follow_redirects=True,
        )
        self._logged_in = False

    async def __aenter__(self) -> "XUIClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Внутренние хелперы
    # ------------------------------------------------------------------ #

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(_RETRYABLE),
    )
    async def _raw_request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            return await self._client.request(method, path, **kwargs)
        except _RETRYABLE as exc:
            logger.warning("3x-ui %s %s: сетевая ошибка, повтор (%s)", method, path, exc)
            raise

    @staticmethod
    def _parse(resp: httpx.Response) -> dict:
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            raise XUIError(f"Панель вернула не-JSON ответ (HTTP {resp.status_code})") from exc
        if isinstance(data, dict) and not data.get("success", True):
            raise XUIError(data.get("msg") or "панель ответила success=false")
        return data if isinstance(data, dict) else {"obj": data}

    async def _ensure_login(self) -> None:
        if not self._logged_in:
            await self.login()

    async def _authed_request(self, method: str, path: str, **kwargs: object) -> dict:
        await self._ensure_login()
        try:
            resp = await self._raw_request(method, path, **kwargs)
        except _RETRYABLE as exc:
            raise XUIConnectionError(f"Нода недоступна: {exc}") from exc
        if resp.status_code == 401:
            # Сессия истекла — логинимся заново и повторяем один раз.
            self._logged_in = False
            await self._ensure_login()
            resp = await self._raw_request(method, path, **kwargs)
        return self._parse(resp)

    # ------------------------------------------------------------------ #
    # Аутентификация
    # ------------------------------------------------------------------ #

    async def login(self) -> None:
        try:
            resp = await self._raw_request(
                "POST", "/login", json={"username": self._username, "password": self._password}
            )
        except _RETRYABLE as exc:
            raise XUIConnectionError(f"Нода недоступна при логине: {exc}") from exc
        self._parse(resp)  # бросит XUIError, если логин/пароль неверны
        self._logged_in = True

    async def health_check(self) -> bool:
        try:
            await self.login()
            return True
        except Exception as exc:  # noqa: BLE001 — health-check не должен падать
            logger.info("Health check не пройден: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Инбаунды
    # ------------------------------------------------------------------ #

    async def list_inbounds(self) -> list[dict]:
        data = await self._authed_request("GET", "/panel/api/inbounds/list")
        return data.get("obj") or []

    async def get_inbound(self, inbound_id: int) -> dict:
        data = await self._authed_request("GET", f"/panel/api/inbounds/get/{inbound_id}")
        return data.get("obj") or {}

    async def create_reality_inbound(
        self,
        *,
        remark: str,
        port: int,
        private_key: str,
        public_key: str,
        short_ids: list[str],
        server_names: list[str],
        dest: str,
        fingerprint: str = "chrome",
    ) -> RealityInboundResult:
        """Создаёт VLESS + Reality (TCP) инбаунд без клиентов — клиенты добавляются отдельно."""
        settings = json.dumps({"clients": [], "decryption": "none", "fallbacks": []})
        stream_settings = json.dumps(
            {
                "network": "tcp",
                "security": "reality",
                "realitySettings": {
                    "show": False,
                    "xver": 0,
                    "dest": dest,
                    "serverNames": server_names,
                    "privateKey": private_key,
                    "minClient": "",
                    "maxClient": "",
                    "maxTimediff": 0,
                    "shortIds": short_ids,
                    "settings": {
                        "publicKey": public_key,
                        "fingerprint": fingerprint,
                        "serverName": "",
                        "spiderX": "/",
                    },
                },
            }
        )
        sniffing = json.dumps(
            {
                "enabled": True,
                "destOverride": ["http", "tls", "quic"],
                "metadataOnly": False,
                "routeOnly": False,
            }
        )
        payload = {
            "up": 0,
            "down": 0,
            "total": 0,
            "remark": remark,
            "enable": True,
            "expiryTime": 0,
            "listen": "",
            "port": port,
            "protocol": "vless",
            "settings": settings,
            "streamSettings": stream_settings,
            "sniffing": sniffing,
        }
        data = await self._authed_request("POST", "/panel/api/inbounds/add", json=payload)
        obj = data.get("obj") or {}
        inbound_id = obj.get("id")
        if inbound_id is None:
            # Некоторые версии не возвращают созданный объект — подстраховываемся списком.
            inbounds = await self.list_inbounds()
            matches = [i for i in inbounds if i.get("remark") == remark]
            if not matches:
                raise XUIError(
                    "Инбаунд создан, но панель не вернула его id. "
                    "Проверьте вручную в веб-панели и уточните ответ API."
                )
            inbound_id = matches[-1]["id"]
        return RealityInboundResult(inbound_id=int(inbound_id), raw=obj)

    async def delete_inbound(self, inbound_id: int) -> None:
        await self._authed_request("POST", f"/panel/api/inbounds/del/{inbound_id}")

    # ------------------------------------------------------------------ #
    # Клиенты
    # ------------------------------------------------------------------ #

    async def add_client(self, inbound_id: int, client: XUIClientConfig) -> None:
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client.to_dict()]})}
        await self._authed_request("POST", "/panel/api/inbounds/addClient", json=payload)

    async def update_client(self, inbound_id: int, client: XUIClientConfig) -> None:
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client.to_dict()]})}
        await self._authed_request(
            "POST", f"/panel/api/inbounds/updateClient/{client.id}", json=payload
        )

    async def delete_client(self, inbound_id: int, client_uuid: str) -> None:
        await self._authed_request(
            "POST", f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
        )

    async def get_client_traffic(self, email: str) -> dict | None:
        data = await self._authed_request(
            "GET", f"/panel/api/inbounds/getClientTraffics/{email}"
        )
        return data.get("obj")


def expiry_ms_from_datetime(value: dt.datetime | None) -> int:
    """UTC datetime → unix-время в миллисекундах (формат expiryTime у 3x-ui)."""
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return int(value.timestamp() * 1000)


def now_ms() -> int:
    return int(time.time() * 1000)
