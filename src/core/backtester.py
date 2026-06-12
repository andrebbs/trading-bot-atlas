"""
Backtester — ATLAS v2
src/core/backtester.py
"""
import pandas as pd
import logging

from src.core.analyzer import TradingAnalyzer
from src.core.entry_sniper import EntrySniper
from src.core.position_sizing import PositionSizing

logger = logging.getLogger(__name__)

class Backtester:
    def __init__(self, initial_balance=1000, risk_per_trade=0.01):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.sniper = EntrySniper()
        self.position = PositionSizing(risk_per_trade=risk_per_trade)
        self.trades = []

    def run(self, df: pd.DataFrame):
        logger.info(f"Iniciando backtest em {len(df)} candles...")

        # Pula os primeiros 100 candles para garantir que os indicadores (EMA, Wyckoff, SMC) tenham histÃ³rico
        for i in range(100, len(df)):
            data = df.iloc[:i].copy()

            analyzer = TradingAnalyzer(data)
            signal = analyzer.get_current_signal()

            if signal.get("signal") not in ["BUY", "SELL"]:
                continue

            direction = signal["signal"]
            entry_data = self.sniper.find_entry(data, direction)

            if not entry_data["valid"]:
                continue

            entry = entry_data["entry_price"]
            sl = entry_data["stop_loss"]
            tp = entry_data["take_profit"]

            future_df = df.iloc[i:]
            trade = self.simulate_trade(future_df, direction, entry, sl, tp)

            if trade:
                trade["index"] = df.index[i] if not df.index.empty else i
                self.execute_trade(trade)

        return self.results()

    def simulate_trade(self, future_df, direction, entry, sl, tp):
        for idx, row in future_df.iterrows():
            high = row["high"]
            low = row["low"]

            if direction == "BUY":
                if low <= sl:
                    return {"result": "LOSS", "entry": entry, "sl": sl, "tp": tp, "exit_idx": idx}
                if high >= tp:
                    return {"result": "WIN", "entry": entry, "sl": sl, "tp": tp, "exit_idx": idx}
            else:
                if high >= sl:
                    return {"result": "LOSS", "entry": entry, "sl": sl, "tp": tp, "exit_idx": idx}
                if low <= tp:
                    return {"result": "WIN", "entry": entry, "sl": sl, "tp": tp, "exit_idx": idx}

        return None

    def execute_trade(self, trade):
        pos = self.position.calculate_trade(
            self.balance, trade["entry"], trade["sl"], trade["tp"]
        )
        risk = pos["risk_amount"]

        if trade["result"] == "WIN":
            profit = risk * pos["risk_reward"]
            self.balance += profit
        else:
            self.balance -= risk

        self.trades.append(trade)

    def results(self):
        total = len(self.trades)
        wins = sum(1 for t in self.trades if t["result"] == "WIN")
        losses = total - wins
        winrate = (wins / total * 100) if total > 0 else 0

        return {
            "initial_balance": self.initial_balance,
            "final_balance": round(self.balance, 2),
            "net_profit": round(self.balance - self.initial_balance, 2),
            "trades": total,
            "wins": wins,
            "losses": losses,
            "winrate": round(winrate, 2)
        }
