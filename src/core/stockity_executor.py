"""Stockity/Binomo binary-options executor via WebSocket (Crypto IDX).

Mirrors the safety posture of ``src.core.novadexy_executor``: disabled by
default, explicit env flags required, and LIVE mode needs a second
confirmation flag so real-money orders are never sent by accident.

The underlying protocol implementation lives in the vendored
``src.vendor.stockity_websocket`` package (a patched ``websocket-client``
fork required by the Stockity/Binomo Phoenix-channel protocol).
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import requests

from src.vendor import stockity_websocket as websocket

logger = logging.getLogger(__name__)

DEFAULT_PLATFORM = "stockity.com"
DEFAULT_ASSET_RIC = "Z-CRY/IDX"  # Crypto IDX composite asset

# Known crypto symbol aliases -> Stockity asset RIC. Extend as new pairs
# are validated on the broker; unmapped symbols fall back to
# STOCKITY_DEFAULT_ASSET_RIC (Crypto IDX) so the bot never silently trades
# an unintended asset.
SYMBOL_RIC_MAP = {
    "CRYPTO IDX": "Z-CRY/IDX",
    "CRYPTO-IDX": "Z-CRY/IDX",
    "CRYPTOIDX": "Z-CRY/IDX",
    "Z-CRY/IDX": "Z-CRY/IDX",
}


def normalize_asset_ric(symbol: str, default_ric: str = DEFAULT_ASSET_RIC) -> str:
    """Map a bot symbol to the Stockity asset RIC, defaulting to Crypto IDX."""
    if not isinstance(symbol, str) or not symbol.strip():
        return default_ric
    raw = symbol.strip().upper().replace("_", " ")
    return SYMBOL_RIC_MAP.get(raw, default_ric)


def direction_to_trend(direction: "str | int") -> str:
    """Convert BUY/SELL/1/0 style directions into Stockity's call/put."""
    if isinstance(direction, bool):
        raise ValueError("direction inválida")
    if direction in (0, 1):
        return "call" if int(direction) == 1 else "put"
    value = str(direction).strip().upper()
    if value in {"BUY", "UP", "CALL", "COMPRA", "1"}:
        return "call"
    if value in {"SELL", "DOWN", "PUT", "VENDA", "0"}:
        return "put"
    raise ValueError("direction deve ser BUY/SELL, CALL/PUT ou 1/0")


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _log(msg: str) -> None:
    logger.info("[STOCKITY] %s", msg)


@dataclass(frozen=True)
class StockitySettings:
    enabled: bool
    mode: str  # demo | live
    confirm_live: bool
    platform: str
    email: str
    password: str
    default_amount_cents: int
    default_expiration_minutes: int
    default_asset_ric: str
    connect_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "StockitySettings":
        mode = os.getenv("STOCKITY_MODE", "demo").strip().lower()
        if mode not in {"demo", "live"}:
            raise ValueError("STOCKITY_MODE aceita somente demo ou live")
        return cls(
            enabled=_flag("STOCKITY_ENABLED"),
            mode=mode,
            confirm_live=_flag("STOCKITY_CONFIRM_LIVE"),
            platform=os.getenv("STOCKITY_PLATFORM", DEFAULT_PLATFORM).strip() or DEFAULT_PLATFORM,
            email=os.getenv("STOCKITY_EMAIL", "").strip(),
            password=os.getenv("STOCKITY_PASSWORD", "").strip(),
            default_amount_cents=int(os.getenv("STOCKITY_DEFAULT_AMOUNT_CENTS", "500")),
            default_expiration_minutes=int(os.getenv("STOCKITY_DEFAULT_EXPIRATION_MINUTES", "1")),
            default_asset_ric=os.getenv("STOCKITY_DEFAULT_ASSET_RIC", DEFAULT_ASSET_RIC).strip() or DEFAULT_ASSET_RIC,
            connect_timeout_seconds=float(os.getenv("STOCKITY_CONNECT_TIMEOUT_SECONDS", "10")),
        )

    @property
    def wallet_type(self) -> str:
        return "real" if self.mode == "live" else "demo"


class _StockityClient:
    """Thin, thread-based WebSocket client for the Stockity/Binomo API.

    Ported from the vendored ``example.py``/``lib.py`` reference
    implementation, kept minimal (login + bid + fire-and-forget result
    tracking) since the bot only needs to place orders, not manage a full
    trading UI.
    """

    def __init__(self, email: str, password: str, platform: str):
        self.platform = platform
        self.device_id = uuid.uuid4().hex
        self.bids: list[dict[str, Any]] = []
        self.ws: Optional[Any] = None
        self._ready = threading.Event()
        self.headers = {
            "cookie": f"authtoken=; device_type=web; device_id={self.device_id};",
            "device-id": self.device_id,
            "origin": f"https://{self.platform}",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            ),
            "user-timezone": "UTC",
        }
        self._login(email, password)
        threading.Thread(target=self._run, name="stockity-ws", daemon=True).start()

    def _login(self, email: str, password: str) -> None:
        headers = {
            "cookie": f"authtoken=; device_type=web; device_id={self.device_id}",
            "device-id": self.device_id,
            "device-type": "web",
            "origin": f"https://{self.platform}",
            "referer": f"https://{self.platform}/",
            "user-agent": self.headers["user-agent"],
            "user-timezone": "UTC",
        }
        payload = {"email": email, "password": password}
        resp = requests.post(
            f"https://api.{self.platform}/passport/v2/sign_in?locale=en",
            headers=headers,
            json=payload,
            timeout=15,
        ).json()
        if "data" not in resp or "authtoken" not in resp.get("data", {}):
            raise RuntimeError(f"Stockity login falhou: {resp}")
        token = resp["data"]["authtoken"]
        self.headers["cookie"] = f"authtoken={token}; device_type=web; device_id={self.device_id};"
        self.headers["authorization-token"] = token

    def _on_open(self, ws) -> None:
        _log("Conexão WebSocket aberta")
        ws.send({"topic": "connection", "event": "phx_join", "payload": {}, "ref": "", "join_ref": "6"})
        ws.send({"topic": "bo", "event": "phx_join", "payload": {}, "ref": "", "join_ref": "9"})
        ws.send({"topic": "account", "event": "phx_join", "payload": {}, "ref": "", "join_ref": "9"})
        ws.send({"topic": "asset", "event": "phx_join", "payload": {}, "ref": "", "join_ref": "26"})
        self.ws = ws
        self._ready.set()

    def _on_message(self, ws, message) -> None:
        try:
            message = json.loads(message)
        except (TypeError, ValueError):
            return
        try:
            event = message.get("event")
            if event == "opened":
                uuid_val = message.get("payload", {}).get("uuid")
                for item in self.bids:
                    if item.get("uuid") == uuid_val:
                        item["payload"] = message["payload"]
            elif event == "close_deal_batch":
                payload = message.get("payload", {})
                for item in self.bids:
                    open_payload = item.get("payload")
                    if not open_payload:
                        continue
                    if open_payload.get("finished_at") != payload.get("finished_at"):
                        continue
                    if item.get("asset_ric") != payload.get("ric"):
                        continue
                    end_rate = payload.get("end_rate")
                    open_rate = open_payload.get("open_rate")
                    if end_rate is None or open_rate is None:
                        continue
                    if end_rate > open_rate:
                        result = "call"
                    elif end_rate < open_rate:
                        result = "put"
                    else:
                        result = "draw"
                    if result == "draw":
                        item["status"] = "draw"
                    elif result == item.get("trend"):
                        item["status"] = "win"
                    else:
                        item["status"] = "lose"
                    item["result"] = result
                    _log(f"Resultado: {item['status'].upper()} | {item.get('asset_ric')}")
            elif message.get("ref") and "payload" in message and "response" in message["payload"]:
                for item in self.bids:
                    if item.get("ref") != message.get("ref"):
                        continue
                    response = message["payload"]["response"]
                    if message.get("event") == "phx_reply" and "uuid" in response:
                        item["uuid"] = response["uuid"]
                    elif message.get("event") == "phx_reply" and "reasons" in response:
                        item["error"] = json.dumps(response["reasons"])
                        _log(f"Falha ao abrir ordem: {item['error']}")
        except Exception:  # defensive: never crash the ws thread
            logger.exception("[STOCKITY] Erro processando mensagem")

    def _parse_expire_at(self, expiration_minutes: int) -> int:
        minute = expiration_minutes
        if minute == 1 and int(datetime.datetime.now().strftime("%S")) >= 30:
            minute = 2
        now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:00")
        base = datetime.datetime.strptime(now, "%d/%m/%Y %H:%M:%S")
        expires = base + datetime.timedelta(minutes=minute)
        return int(time.mktime(expires.timetuple()))

    def bid(self, trend: str, amount_cents: int, asset_ric: str, wallet_type: str, expiration_minutes: int) -> str:
        if not self.ws:
            raise RuntimeError("WebSocket Stockity ainda não está pronto")
        data = {
            "wallet_type": wallet_type,
            "amount": amount_cents,
            "asset_ric": asset_ric,
            "trend": trend,
        }
        self.ws.send(
            {
                "topic": "bo",
                "event": "create",
                "payload": {
                    "created_at": int(time.time() * 1000),
                    "ric": asset_ric,
                    "deal_type": wallet_type,
                    "expire_at": self._parse_expire_at(expiration_minutes),
                    "option_type": "turbo",
                    "trend": trend,
                    "tournament_id": None,
                    "is_state": False,
                    "amount": amount_cents,
                },
                "ref": "",
                "join_ref": "9",
            }
        )
        data["ref"] = self.ws.ref
        self.bids.append(data)
        return str(data["ref"])

    def wait_ready(self, timeout: float) -> bool:
        return self._ready.wait(timeout)

    def _run(self) -> None:
        ws = websocket.WebSocketApp(
            f"wss://ws.{self.platform}/?v=2&vsn=2.0.0",
            header=self.headers,
            on_message=self._on_message,
            on_open=self._on_open,
        )
        ws.run_forever(
            ping_interval=15,
            reconnect=5,
            ping_payload=[
                {"topic": "phoenix", "event": "heartbeat", "payload": {}, "ref": ""},
                {"topic": "connection", "event": "ping", "payload": {}, "ref": "", "join_ref": "6"},
            ],
        )


class StockityExecutor:
    """Fire-and-forget order placement on Stockity/Binomo (Crypto IDX)."""

    def __init__(self, settings: Optional[StockitySettings] = None):
        self.settings = settings or StockitySettings.from_env()
        self._client: Optional[_StockityClient] = None
        self._lock = threading.Lock()

    def _validate(self) -> None:
        if not self.settings.enabled:
            raise RuntimeError("STOCKITY_ENABLED=false; execução bloqueada")
        if not self.settings.email or not self.settings.password:
            raise RuntimeError("STOCKITY_EMAIL/STOCKITY_PASSWORD ausentes")
        if self.settings.mode == "live" and not self.settings.confirm_live:
            raise RuntimeError(
                "STOCKITY_MODE=live requer STOCKITY_CONFIRM_LIVE=true (dinheiro real)"
            )

    def _get_client(self) -> _StockityClient:
        with self._lock:
            if self._client is None:
                self._client = _StockityClient(
                    self.settings.email, self.settings.password, self.settings.platform
                )
            client = self._client
        if not client.wait_ready(self.settings.connect_timeout_seconds):
            raise RuntimeError("Timeout conectando ao WebSocket da Stockity")
        return client

    def place_order(
        self,
        symbol: str,
        direction: "str | int",
        amount_cents: Optional[int] = None,
        expiration_minutes: Optional[int] = None,
        asset_ric: Optional[str] = None,
    ) -> dict:
        """Place a fire-and-forget bid; does not wait for win/loss result."""
        trend = direction_to_trend(direction)
        amount = int(amount_cents if amount_cents is not None else self.settings.default_amount_cents)
        expiry = int(
            expiration_minutes if expiration_minutes is not None else self.settings.default_expiration_minutes
        )
        ric = asset_ric or normalize_asset_ric(symbol, self.settings.default_asset_ric)
        if amount <= 0 or expiry <= 0:
            raise ValueError("amount_cents e expiration_minutes devem ser positivos")

        payload_preview = {
            "asset_ric": ric,
            "trend": trend,
            "amount_cents": amount,
            "expiration_minutes": expiry,
            "wallet_type": self.settings.wallet_type,
        }

        try:
            self._validate()
        except RuntimeError as exc:
            return {"ok": False, "mode": self.settings.mode.upper(), "error": str(exc), "payload": payload_preview}

        try:
            client = self._get_client()
            ref = client.bid(
                trend=trend,
                amount_cents=amount,
                asset_ric=ric,
                wallet_type=self.settings.wallet_type,
                expiration_minutes=expiry,
            )
            _log(
                f"Ordem enviada ({self.settings.wallet_type.upper()}): {trend} {ric} "
                f"amount={amount} ref={ref}"
            )
            return {
                "ok": True,
                "mode": self.settings.mode.upper(),
                "executed": True,
                "ref": ref,
                "payload": payload_preview,
            }
        except Exception as exc:  # network/websocket failures
            logger.exception("[STOCKITY] Falha ao enviar ordem")
            return {"ok": False, "mode": self.settings.mode.upper(), "error": str(exc), "payload": payload_preview}

    async def place_order_async(self, **kwargs: Any) -> dict:
        return await asyncio.to_thread(self.place_order, **kwargs)


def get_executor() -> StockityExecutor:
    return StockityExecutor()
