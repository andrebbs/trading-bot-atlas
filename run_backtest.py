import pandas as pd
import numpy as np

from src.core.backtester import Backtester


# ==============================
# CONFIG
# ==============================

CSV_PATH = "data/solusdt_5m.csv"   # <-- ajuste aqui
INITIAL_BALANCE = 1000


# ==============================
# LOAD DATA
# ==============================

def load_data(path):
    df = pd.read_csv(path)

    # padronizar colunas
    df.columns = [c.lower() for c in df.columns]

    required = ["open", "high", "low", "close"]
    for col in required:
        if col not in df.columns:
            raise Exception(f"Coluna faltando: {col}")

    return df


# ==============================
# DRAWDOWN
# ==============================

def calculate_drawdown(equity_curve):
    peak = equity_curve[0]
    max_dd = 0

    for value in equity_curve:
        if value > peak:
            peak = value

        dd = (peak - value) / peak

        if dd > max_dd:
            max_dd = dd

    return max_dd * 100


# ==============================
# RUN BACKTEST
# ==============================

def run():

    df = load_data(CSV_PATH)

    bt = Backtester(initial_balance=INITIAL_BALANCE)

    equity_curve = [INITIAL_BALANCE]

    print(f"\n📊 Rodando backtest em {len(df)} candles...\n")

    for i in range(150, len(df)):

        data = df.iloc[:i].copy()

        result = bt.run(data)

        equity_curve.append(result["final_balance"])

    results = bt.results()

    drawdown = calculate_drawdown(equity_curve)

    print("\n" + "="*50)
    print("📊 RESULTADO FINAL")
    print("="*50)

    print(f"Saldo inicial: ${results['initial_balance']}")
    print(f"Saldo final:   ${results['final_balance']}")
    print(f"Lucro:         ${results['net_profit']}")

    print(f"\nTrades:   {results['trades']}")
    print(f"Wins:     {results['wins']}")
    print(f"Losses:   {results['losses']}")
    print(f"Winrate:  {results['winrate']}%")

    print(f"\n📉 Drawdown máximo: {drawdown:.2f}%")

    print("="*50)


if __name__ == "__main__":
    run()
