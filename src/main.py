"""Ponto de entrada (CLI & Orquestrador) do Bot Lógica do Preço M1 / OTC."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List

from src.core.lot_defense import Candle, LotDefenseAnalyzer, detect_lots
from src.feed.candle_buffer import ClosedCandleBuffer
from src.notifications.telegram_notifier import TelegramConfig, TelegramNotifier
from src.execution.paper_trader import PaperTrader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("LotDefenseBot")


class PriceLogicEngine:
    def __init__(
        self,
        symbols: List[str],
        telegram_token: str = "",
        telegram_chat_id: str = "",
        min_defenses: int = 3,
        paper_trading: bool = True,
    ):
        self.symbols = [s.upper().strip() for s in symbols]
        self.buffer = ClosedCandleBuffer(max_history=100)
        self.analyzers = {s: LotDefenseAnalyzer(symbol=s, min_defenses=min_defenses) for s in self.symbols}
        
        tg_config = TelegramConfig(
            bot_token=telegram_token,
            chat_id=telegram_chat_id,
            enabled=bool(telegram_token and telegram_chat_id),
        )
        self.notifier = TelegramNotifier(tg_config)
        self.paper_trader = PaperTrader() if paper_trading else None

    def on_closed_candle(self, symbol: str, candle: Candle) -> None:
        symbol = symbol.upper().strip()
        if symbol not in self.analyzers:
            return

        if self.paper_trader:
            resolved_trades = self.paper_trader.process_closed_candle(symbol, candle)
            for t in resolved_trades:
                logger.info(
                    "🎯 Operação Finalizada [%s]: %s | Res: %s | PnL: %s",
                    t.symbol, t.action.value, t.result.value, t.profit
                )

        if not self.buffer.add_closed_candle(symbol, candle):
            return

        candles = self.buffer.get_candles(symbol)
        if len(candles) < 3:
            return

        lots = detect_lots(candles[:-1])
        analyzer = self.analyzers[symbol]
        signal = analyzer.evaluate_last_candle_for_signal(candles, lots)

        if signal is not None:
            logger.info("🚨 SINAL CONFIRMADO: %s %s em %s", signal.symbol, signal.action.value, signal.price)
            self.notifier.send_signal(signal)
            if self.paper_trader:
                self.paper_trader.open_trade_from_signal(signal)
