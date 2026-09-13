"""Mecanismo de Paper Trading (Simulação M1) para Lógica do Preço."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from src.core.lot_defense import Candle, LotSide, LotSignal


class TradeResult(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    DOJI = "DOJI"


@dataclass
class PaperTrade:
    id: str
    symbol: str
    action: LotSide
    entry_time: datetime
    entry_price: Decimal
    defense_count: int
    stake: Decimal
    payout_rate: Decimal = Decimal("0.85")
    status: str = "OPEN"
    exit_time: Optional[datetime] = None
    exit_price: Optional[Decimal] = None
    result: Optional[TradeResult] = None
    profit: Decimal = Decimal("0.0")


class PaperTrader:
    def __init__(self, default_stake: Decimal = Decimal("10.0"), default_payout: Decimal = Decimal("0.85")):
        self.default_stake = default_stake
        self.default_payout = default_payout
        self.open_trades: Dict[str, List[PaperTrade]] = {}
        self.closed_trades: List[PaperTrade] = []

    def open_trade_from_signal(self, signal: LotSignal, stake: Optional[Decimal] = None) -> PaperTrade:
        symbol = signal.symbol.upper().strip()
        trade = PaperTrade(
            id=f"{symbol}-{signal.timestamp.isoformat()}-{signal.action.value}",
            symbol=symbol,
            action=signal.action,
            entry_time=signal.timestamp,
            entry_price=signal.price,
            defense_count=signal.defense_count,
            stake=stake or self.default_stake,
            payout_rate=self.default_payout,
        )
        self.open_trades.setdefault(symbol, []).append(trade)
        return trade

    def process_closed_candle(self, symbol: str, candle: Candle) -> List[PaperTrade]:
        symbol = symbol.upper().strip()
        pending = self.open_trades.get(symbol, [])
        if not pending:
            return []

        resolved: List[PaperTrade] = []
        still_open: List[PaperTrade] = []

        for trade in pending:
            if candle.timestamp > trade.entry_time:
                trade.exit_time = candle.timestamp
                trade.exit_price = candle.close

                if trade.action is LotSide.BUY:
                    if candle.close > trade.entry_price:
                        trade.result, trade.profit = TradeResult.WIN, trade.stake * trade.payout_rate
                    elif candle.close < trade.entry_price:
                        trade.result, trade.profit = TradeResult.LOSS, -trade.stake
                    else:
                        trade.result, trade.profit = TradeResult.DOJI, Decimal("0.0")
                else:
                    if candle.close < trade.entry_price:
                        trade.result, trade.profit = TradeResult.WIN, trade.stake * trade.payout_rate
                    elif candle.close > trade.entry_price:
                        trade.result, trade.profit = TradeResult.LOSS, -trade.stake
                    else:
                        trade.result, trade.profit = TradeResult.DOJI, Decimal("0.0")

                trade.status = "CLOSED"
                self.closed_trades.append(trade)
                resolved.append(trade)
            else:
                still_open.append(trade)

        self.open_trades[symbol] = still_open
        return resolved

    def get_statistics(self) -> dict:
        total = len(self.closed_trades)
        if total == 0:
            return {
                "total_trades": 0, "wins": 0, "losses": 0, "dojis": 0,
                "win_rate_percent": 0.0, "total_profit": Decimal("0.0"),
            }
        wins = sum(1 for t in self.closed_trades if t.result is TradeResult.WIN)
        losses = sum(1 for t in self.closed_trades if t.result is TradeResult.LOSS)
        dojis = sum(1 for t in self.closed_trades if t.result is TradeResult.DOJI)
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
        total_profit = sum((t.profit for t in self.closed_trades), Decimal("0.0"))
        return {
            "total_trades": total, "wins": wins, "losses": losses, "dojis": dojis,
            "win_rate_percent": round(win_rate, 2), "total_profit": total_profit,
        }
