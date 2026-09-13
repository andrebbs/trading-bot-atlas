"""Buffer e gerenciador de fluxo de candles M1 fechados."""
from __future__ import annotations

from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional
from src.core.lot_defense import Candle


class ClosedCandleBuffer:
    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self._buffers: Dict[str, deque[Candle]] = {}
        self._last_closed_timestamp: Dict[str, datetime] = {}

    def add_closed_candle(self, symbol: str, candle: Candle) -> bool:
        symbol = symbol.upper().strip()
        if symbol not in self._buffers:
            self._buffers[symbol] = deque(maxlen=self.max_history)

        last_ts = self._last_closed_timestamp.get(symbol)
        if last_ts is not None and candle.timestamp <= last_ts:
            return False

        self._buffers[symbol].append(candle)
        self._last_closed_timestamp[symbol] = candle.timestamp
        return True

    def get_candles(self, symbol: str) -> List[Candle]:
        symbol = symbol.upper().strip()
        buf = self._buffers.get(symbol)
        return list(buf) if buf else []

    def count(self, symbol: str) -> int:
        symbol = symbol.upper().strip()
        buf = self._buffers.get(symbol)
        return len(buf) if buf else 0
