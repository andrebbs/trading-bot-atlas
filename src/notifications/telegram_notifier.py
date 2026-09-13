"""Serviço de despacho de alertas para Telegram com deduplicação."""
from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from src.core.lot_defense import LotSignal

logger = logging.getLogger(__name__)


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str
    enabled: bool = True


class TelegramNotifier:
    def __init__(self, config: Optional[TelegramConfig] = None):
        self.config = config or TelegramConfig(bot_token="", chat_id="", enabled=False)
        self._sent_signals: Set[str] = set()
        self.history: List[LotSignal] = []

    def format_signal_message(self, signal: LotSignal) -> str:
        return signal.message

    def send_signal(self, signal: LotSignal) -> bool:
        signal_key = f"{signal.symbol}_{signal.timestamp.isoformat()}_{signal.action.value}_{signal.price}"
        if signal_key in self._sent_signals:
            return False

        self._sent_signals.add(signal_key)
        self.history.append(signal)

        if not self.config.enabled or not self.config.bot_token or not self.config.chat_id:
            return True

        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        payload = {
            "chat_id": self.config.chat_id,
            "text": signal.message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except Exception:
            return False
