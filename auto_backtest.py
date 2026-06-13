#!/usr/bin/env python3
"""
ATLAS Auto-Backtest — Versão Otimizada
Estratégias: SMC + Wyckoff + Analyzer
Correções de performance: sem loops O(n²), indicadores pré-calculados, sem I/O dentro do loop
"""

import time
import sys
import os
import json
import math
from datetime import datetime, timezone
from collections import deque

# ─────────────────────────────────────────────
# DEPENDÊNCIAS OPCIONAIS
# ─────────────────────────────────────────────
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("⚠️  'requests' não instalado. Use: pip install requests")

try:
    import pandas as pd
    import numpy as np
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("⚠️  'pandas' / 'numpy' não instalado. Use: pip install pandas numpy")


# ═══════════════════════════════════════════════════════════════
# CONFIGURAÇÕES
# ═══════════════════════════════════════════════════════════════
CONFIG = {
    "symbol":        "SOLUSDT",
    "interval":      "5m",
    "candles_req":   2000,       # quantos candles pedir à API
    "candles_use":   1000,       # quantos usar no backtest
    "capital_ini":   1000.0,     # capital inicial em USDT
    "risk_per_trade":0.01,       # 1% de risco por trade
    "sl_atr_mult":   1.5,        # Stop Loss = 1.5 × ATR
    "tp_atr_mult":   3.0,        # Take Profit = 3.0 × ATR
    "atr_period":    14,
    "ema_fast":      9,
    "ema_slow":      21,
    "ema_trend":     50,
    "rsi_period":    14,
    "vol_ma_period": 20,
    "swing_window":  5,          # janela para detectar swing highs/lows
    "save_results":  True,
    "results_file":  "backtest_results.json",
}


# ═══════════════════════════════════════════════════════════════
# 1. DOWNLOAD DE DADOS
# ═══════════════════════════════════════════════════════════════
def download_candles(symbol: str, interval: str, limit: int) -> list:
    """Baixa candles da Binance (endpoint público, sem API key)."""
    if not HAS_REQUESTS:
        raise RuntimeError("requests não disponível.")

    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)}

    print(f"📡 Baixando últimos {limit} candles de {symbol} ({interval})...")
    t0 = time.time()

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        raise RuntimeError(f"Erro ao baixar candles: {e}")

    candles = []
    for k in raw:
        candles.append({
            "ts":     int(k[0]),
            "open":   float(k[1]),
            "high":   float(k[2]),
            "low":    float(k[3]),
            "close":  float(k[4]),
            "volume": float(k[5]),
        })

    print(f"✅ Download concluído: {len(candles)} candles em {time.time()-t0:.1f}s\n")
    return candles


def load_candles_csv(path: str) -> list:
    """Fallback: carrega candles de um CSV local (colunas: ts,open,high,low,close,volume)."""
    if not HAS_PANDAS:
        raise RuntimeError("pandas não disponível para ler CSV.")
    df = pd.read_csv(path)
    return df.to_dict("records")


# ═══════════════════════════════════════════════════════════════
# 2. PRÉ-CÁLCULO DE INDICADORES  (O(n) — fora do loop principal)
# ═══════════════════════════════════════════════════════════════
def compute_ema(closes: list, period: int) -> list:
    """EMA vetorizada — calculada UMA vez para toda a série."""
    ema = [None] * len(closes)
    k = 2 / (period + 1)
    # seed = SMA dos primeiros `period` valores
    seed_idx = period - 1
    if seed_idx >= len(closes):
        return ema
    ema[seed_idx] = sum(closes[:period]) / period
    for i in range(seed_idx + 1, len(closes)):
        ema[i] = closes[i] * k + ema[i - 1] * (1 - k)
    return ema


def compute_rsi(closes: list, period: int) -> list:
    """RSI clássico de Wilder — O(n)."""
    rsi = [None] * len(closes)
    if len(closes) <= period:
        return rsi

    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for i in range(period, len(closes)):
        if i > period:
            diff = closes[i] - closes[i - 1]
            gain = max(diff, 0)
            loss = max(-diff, 0)
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100 - (100 / (1 + rs))

    return rsi


def compute_atr(highs: list, lows: list, closes: list, period: int) -> list:
    """ATR de Wilder — O(n)."""
    atr = [None] * len(closes)
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    if len(trs) < period:
        return atr

    # seed
    atr[period] = sum(trs[:period]) / period
    for i in range(period + 1, len(closes)):
        atr[i] = (atr[i - 1] * (period - 1) + trs[i - 1]) / period

    return atr


def compute_volume_ma(volumes: list, period: int) -> list:
    """Média móvel simples do volume — O(n)."""
    vol_ma = [None] * len(volumes)
    window_sum = sum(volumes[:period])
    if period <= len(volumes):
        vol_ma[period - 1] = window_sum / period
    for i in range(period, len(volumes)):
        window_sum += volumes[i] - volumes[i - period]
        vol_ma[i] = window_sum / period
    return vol_ma


def detect_swing_points(highs: list, lows: list, window: int) -> tuple:
    """
    Detecta swing highs e swing lows — pré-calculado UMA vez.
    Retorna duas listas booleanas do tamanho de highs/lows.
    """
    n = len(highs)
    is_swing_high = [False] * n
    is_swing_low  = [False] * n

    for i in range(window, n - window):
        # swing high: pico local
        if highs[i] == max(highs[i - window: i + window + 1]):
            is_swing_high[i] = True
        # swing low: vale local
        if lows[i] == min(lows[i - window: i + window + 1]):
            is_swing_low[i] = True

    return is_swing_high, is_swing_low


def precompute_all(candles: list, cfg: dict) -> dict:
    """
    Calcula TODOS os indicadores UMA única vez antes do loop principal.
    Retorna um dict com arrays alinhados ao índice dos candles.
    """
    print("📊 Pré-calculando indicadores... ", end="", flush=True)
    t0 = time.time()

    closes  = [c["close"]  for c in candles]
    highs   = [c["high"]   for c in candles]
    lows    = [c["low"]    for c in candles]
    volumes = [c["volume"] for c in candles]

    ind = {
        "closes":       closes,
        "highs":        highs,
        "lows":         lows,
        "volumes":      volumes,
        "ema_fast":     compute_ema(closes, cfg["ema_fast"]),
        "ema_slow":     compute_ema(closes, cfg["ema_slow"]),
        "ema_trend":    compute_ema(closes, cfg["ema_trend"]),
        "rsi":          compute_rsi(closes, cfg["rsi_period"]),
        "atr":          compute_atr(highs, lows, closes, cfg["atr_period"]),
        "vol_ma":       compute_volume_ma(volumes, cfg["vol_ma_period"]),
    }
    sh, sl = detect_swing_points(highs, lows, cfg["swing_window"])
    ind["is_swing_high"] = sh
    ind["is_swing_low"]  = sl

    print(f"concluído em {time.time()-t0:.2f}s")
    return ind


# ═══════════════════════════════════════════════════════════════
# 3. ESTRATÉGIAS SMC + WYCKOFF  (leitura O(1) por candle)
# ═══════════════════════════════════════════════════════════════
def smc_signal(i: int, ind: dict) -> str:
    """
    Smart Money Concepts simplificado.
    Sinal baseado em: break of structure + EMA trend + volume acima da média.
    Retorna 'LONG', 'SHORT' ou None.
    """
    if i < 2:
        return None

    ema_f    = ind["ema_fast"][i]
    ema_s    = ind["ema_slow"][i]
    ema_t    = ind["ema_trend"][i]
    vol      = ind["volumes"][i]
    vol_ma   = ind["vol_ma"][i]
    close    = ind["closes"][i]
    prev_high= ind["highs"][i - 1]
    prev_low = ind["lows"][i - 1]
    swing_h  = ind["is_swing_high"][i - 1]
    swing_l  = ind["is_swing_low"][i - 1]

    if any(v is None for v in [ema_f, ema_s, ema_t, vol_ma]):
        return None

    bullish_trend = ema_f > ema_s > ema_t
    bearish_trend = ema_f < ema_s < ema_t
    high_vol      = vol > vol_ma * 1.2

    # Break of Structure LONG: rompe swing high com trend bullish e volume
    if bullish_trend and swing_h and close > prev_high and high_vol:
        return "LONG"

    # Break of Structure SHORT: rompe swing low com trend bearish e volume
    if bearish_trend and swing_l and close < prev_low and high_vol:
        return "SHORT"

    return None


def wyckoff_phase(i: int, ind: dict, lookback: int = 30) -> str:
    """
    Identifica fase Wyckoff aproximada com base nos últimos `lookback` candles.
    Retorna: 'ACCUMULATION', 'MARKUP', 'DISTRIBUTION', 'MARKDOWN', 'UNKNOWN'
    Complexidade: O(lookback) — constante em relação ao total de candles.
    """
    if i < lookback:
        return "UNKNOWN"

    closes_w  = ind["closes"][i - lookback: i + 1]
    volumes_w = ind["volumes"][i - lookback: i + 1]

    price_range   = max(closes_w) - min(closes_w)
    avg_price     = sum(closes_w) / len(closes_w)
    price_change  = closes_w[-1] - closes_w[0]
    avg_vol       = sum(volumes_w) / len(volumes_w)
    recent_vol    = sum(volumes_w[-5:]) / 5

    tight_range   = price_range < avg_price * 0.03   # < 3% de range
    expanding_vol = recent_vol > avg_vol * 1.3

    if tight_range and expanding_vol and price_change > 0:
        return "ACCUMULATION"
    if not tight_range and price_change > avg_price * 0.02:
        return "MARKUP"
    if tight_range and expanding_vol and price_change < 0:
        return "DISTRIBUTION"
    if not tight_range and price_change < -avg_price * 0.02:
        return "MARKDOWN"

    return "UNKNOWN"


def combined_signal(i: int, ind: dict, cfg: dict) -> str:
    """
    Combina SMC + Wyckoff para gerar sinal final.
    """
    smc  = smc_signal(i, ind)
    if smc is None:
        return None

    phase = wyckoff_phase(i, ind)

    rsi_val = ind["rsi"][i]
    if rsi_val is None:
        return None

    if smc == "LONG":
        if phase in ("ACCUMULATION", "MARKUP") and rsi_val < 70:
            return "LONG"
    elif smc == "SHORT":
        if phase in ("DISTRIBUTION", "MARKDOWN") and rsi_val > 30:
            return "SHORT"

    return None


# ═══════════════════════════════════════════════════════════════
# 4. ENGINE DE BACKTEST  (loop principal O(n))
# ═══════════════════════════════════════════════════════════════
class Trade:
    __slots__ = ("direction", "entry", "sl", "tp", "entry_idx",
                 "exit_idx", "exit_price", "pnl", "result")

    def __init__(self, direction, entry, sl, tp, entry_idx):
        self.direction  = direction
        self.entry      = entry
        self.sl         = sl
        self.tp         = tp
        self.entry_idx  = entry_idx
        self.exit_idx   = None
        self.exit_price = None
        self.pnl        = 0.0
        self.result     = None   # "WIN" | "LOSS"


def run_backtest(candles: list, ind: dict, cfg: dict) -> dict:
    """
    Loop principal de backtest — O(n), sem chamadas I/O ou recálculos internos.
    """
    n          = len(candles)
    capital    = cfg["capital_ini"]
    risk_amt   = capital * cfg["risk_per_trade"]
    trades     = []
    open_trade = None
    equity     = [capital]

    progress_step = max(1, n // 10)

    print(f"\n📊 Processando estratégias SMC + Wyckoff + Analyzer...")
    print(f"⏳ Isso pode levar alguns segundos. Aguarde...\n")
    t0 = time.time()

    for i in range(1, n):
        if i % progress_step == 0:
            pct = int(i / n * 100)
            elapsed = time.time() - t0
            eta = (elapsed / i) * (n - i)
            print(f"   ... Escaneados {i}/{n} candles  "
                  f"({pct}%)  |  {elapsed:.1f}s decorridos  |  ETA ~{eta:.1f}s")

        high  = ind["highs"][i]
        low   = ind["lows"][i]
        close = ind["closes"][i]
        atr   = ind["atr"][i]

        # ── Gerenciar trade aberto ──────────────────────────────
        if open_trade is not None:
            hit_sl = hit_tp = False

            if open_trade.direction == "LONG":
                hit_sl = low  <= open_trade.sl
                hit_tp = high >= open_trade.tp
            else:  # SHORT
                hit_sl = high >= open_trade.sl
                hit_tp = low  <= open_trade.tp

            if hit_tp or hit_sl:
                exit_price = open_trade.tp if hit_tp else open_trade.sl
                result     = "WIN"          if hit_tp else "LOSS"

                if open_trade.direction == "LONG":
                    pnl = (exit_price - open_trade.entry) / open_trade.entry
                else:
                    pnl = (open_trade.entry - exit_price) / open_trade.entry

                # Dimensionamento de posição simples (risco fixo)
                sl_dist = abs(open_trade.entry - open_trade.sl)
                if sl_dist > 0:
                    position_size = risk_amt / (sl_dist / open_trade.entry * open_trade.entry)
                else:
                    position_size = 0

                trade_pnl = pnl * position_size
                capital  += trade_pnl

                open_trade.exit_idx   = i
                open_trade.exit_price = exit_price
                open_trade.pnl        = trade_pnl
                open_trade.result     = result
                trades.append(open_trade)
                open_trade = None
                risk_amt   = capital * cfg["risk_per_trade"]  # re-calcula risco

            equity.append(capital)
            continue

        # ── Buscar novo sinal ───────────────────────────────────
        if atr is None or atr == 0:
            equity.append(capital)
            continue

        signal = combined_signal(i, ind, cfg)

        if signal == "LONG":
            sl = close - atr * cfg["sl_atr_mult"]
            tp = close + atr * cfg["tp_atr_mult"]
            open_trade = Trade("LONG", close, sl, tp, i)

        elif signal == "SHORT":
            sl = close + atr * cfg["sl_atr_mult"]
            tp = close - atr * cfg["tp_atr_mult"]
            open_trade = Trade("SHORT", close, sl, tp, i)

        equity.append(capital)

    elapsed = time.time() - t0
    print(f"\n✅ Backtest concluído em {elapsed:.2f}s")
    return {"trades": trades, "equity": equity, "capital_final": capital, "elapsed": elapsed}


# ═══════════════════════════════════════════════════════════════
# 5. RELATÓRIO DE RESULTADOS
# ═══════════════════════════════════════════════════════════════
def compute_max_drawdown(equity: list) -> float:
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def print_report(result: dict, cfg: dict) -> dict:
    trades        = result["trades"]
    equity        = result["equity"]
    capital_ini   = cfg["capital_ini"]
    capital_final = result["capital_final"]

    wins   = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    n      = len(trades)

    win_rate   = (len(wins) / n * 100) if n > 0 else 0
    total_pnl  = capital_final - capital_ini
    pct_return = (total_pnl / capital_ini) * 100
    max_dd     = compute_max_drawdown(equity) * 100

    avg_win  = (sum(t.pnl for t in wins)   / len(wins))   if wins   else 0
    avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else 0
    profit_factor = abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) \
                    if losses and sum(t.pnl for t in losses) != 0 else float("inf")

    sep = "═" * 52
    print(f"\n{sep}")
    print(f"  📈  ATLAS BACKTEST — RELATÓRIO FINAL")
    print(sep)
    print(f"  Símbolo       : {cfg['symbol']} ({cfg['interval']})")
    print(f"  Capital Ini.  : $ {capital_ini:>10,.2f}")
    print(f"  Capital Final : $ {capital_final:>10,.2f}")
    print(f"  Retorno Total : {pct_return:>+.2f}%")
    print(f"  Max Drawdown  : {max_dd:.2f}%")
    print(sep)
    print(f"  Total Trades  : {n}")
    print(f"  Vencedores    : {len(wins)}  ({win_rate:.1f}%)")
    print(f"  Perdedores    : {len(losses)}")
    print(f"  Avg Win       : $ {avg_win:>8,.2f}")
    print(f"  Avg Loss      : $ {avg_loss:>8,.2f}")
    print(f"  Profit Factor : {profit_factor:.2f}")
    print(f"  Tempo Exec.   : {result['elapsed']:.2f}s")
    print(sep)

    report = {
        "symbol":         cfg["symbol"],
        "interval":       cfg["interval"],
        "capital_ini":    capital_ini,
        "capital_final":  round(capital_final, 2),
        "return_pct":     round(pct_return, 2),
        "max_drawdown":   round(max_dd, 2),
        "total_trades":   n,
        "wins":           len(wins),
        "losses":         len(losses),
        "win_rate":       round(win_rate, 2),
        "avg_win":        round(avg_win, 2),
        "avg_loss":       round(avg_loss, 2),
        "profit_factor":  round(profit_factor, 4),
        "elapsed_sec":    round(result["elapsed"], 2),
        "generated_at":   datetime.now(timezone.utc).isoformat(),
    }
    return report


# ═══════════════════════════════════════════════════════════════
# 6. MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print("\n🚀 Iniciando ATLAS Auto-Backtest\n")

    cfg = CONFIG.copy()

    # ── 1. Download ─────────────────────────────────────────────
    candles = download_candles(cfg["symbol"], cfg["interval"], cfg["candles_req"])

    # Usa apenas os últimos N candles configurados
    if len(candles) > cfg["candles_use"]:
        candles = candles[-cfg["candles_use"]:]
        print(f"📌 Usando últimos {len(candles)} candles para o backtest.\n")

    # ── 2. Pré-calcular indicadores (UMA vez, fora do loop) ─────
    ind = precompute_all(candles, cfg)

    # ── 3. Rodar backtest ────────────────────────────────────────
    result = run_backtest(candles, ind, cfg)

    # ── 4. Relatório ─────────────────────────────────────────────
    report = print_report(result, cfg)

    # ── 5. Salvar resultado ──────────────────────────────────────
    if cfg["save_results"]:
        with open(cfg["results_file"], "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n💾 Resultados salvos em: {cfg['results_file']}")

    print("\n✨ Finalizado.\n")


if __name__ == "__main__":
    main()
