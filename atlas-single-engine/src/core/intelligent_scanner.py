"""ATLAS Intelligent Scanner."""
from __future__ import annotations
import math
from typing import Any, Dict, Iterable, List, Optional


class ScannerSignal:
    __slots__ = ("symbol","side","score","confidence","reasons",
                 "timeframe","entry","stop_loss","take_profit")

    def __init__(self, symbol, side, score, confidence, reasons,
                 timeframe="5m", entry=None, stop_loss=None, take_profit=None):
        self.symbol     = symbol
        self.side       = side
        self.score      = score
        self.confidence = confidence
        self.reasons    = reasons
        self.timeframe  = timeframe
        self.entry      = entry
        self.stop_loss  = stop_loss
        self.take_profit = take_profit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol, "side": self.side,
            "score": self.score,   "confidence": self.confidence,
            "reasons": self.reasons, "timeframe": self.timeframe,
            "entry": self.entry,   "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
        }


def _num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        v = float(x)
        return default if (math.isnan(v) or math.isinf(v)) else v
    except Exception:
        return default


def get_asset_profile(symbol: str) -> Dict[str, Any]:
    s = (symbol or "").upper().replace("/", "")
    if s in {"BTCUSDT", "ETHUSDT"}:
        return {"tier": 1, "liquidity": "high", "min_score": 0.58}
    if s in {"SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT",
             "DOGEUSDT","AVAXUSDT","LINKUSDT","TONUSDT"}:
        return {"tier": 2, "liquidity": "medium_high", "min_score": 0.62}
    return {"tier": 3, "liquidity": "selective", "min_score": 0.68}


def analyze_market_snapshot(
    symbol: str, data: Dict[str, Any], timeframe: str = "5m"
) -> ScannerSignal:
    price     = _num(data.get("price") or data.get("close"))
    rsi       = _num(data.get("rsi"), 50)
    macd      = _num(data.get("macd_hist") or data.get("macd"), 0)
    ema_fast  = _num(data.get("ema_fast") or data.get("ema9"), price)
    ema_slow  = _num(data.get("ema_slow") or data.get("ema21"), price)
    atr_pct   = _num(data.get("atr_pct"), 0.5)
    vol_ratio = _num(data.get("volume_ratio"), 1.0)
    profile   = get_asset_profile(symbol)

    score = 0.0
    reasons: List[str] = []

    if ema_fast > ema_slow:
        score += 0.18; reasons.append("EMA rapida acima da lenta")
    elif ema_fast < ema_slow:
        score -= 0.18; reasons.append("EMA rapida abaixo da lenta")

    if 52 <= rsi <= 68:
        score += 0.15; reasons.append("RSI comprador saudavel")
    elif 32 <= rsi <= 48:
        score -= 0.15; reasons.append("RSI vendedor saudavel")
    elif rsi > 75:
        score -= 0.08; reasons.append("RSI sobrecomprado")
    elif rsi < 25:
        score += 0.08; reasons.append("RSI sobrevendido")

    if macd > 0:
        score += 0.12; reasons.append("MACD positivo")
    elif macd < 0:
        score -= 0.12; reasons.append("MACD negativo")

    if 0.25 <= atr_pct <= 3.5:
        score += 0.10; reasons.append("Volatilidade operavel")
    else:
        score -= 0.12; reasons.append("Volatilidade fora do ideal")

    if vol_ratio >= 1.2:
        score += 0.12; reasons.append("Volume acima da media")
    elif vol_ratio < 0.75:
        score -= 0.08; reasons.append("Volume fraco")

    conf = data.get("confluence_score")
    if conf is not None:
        c = max(0.0, min(1.0, _num(conf)))
        score += (c - 0.5) * 0.60
        reasons.append(f"Confluencia ATLAS {c:.2f}")

    side      = "BUY" if score >= 0 else "SELL"
    abs_score = max(0.0, min(1.0, 0.5 + abs(score)))
    min_sc    = profile["min_score"]
    if abs_score >= max(0.78, min_sc + 0.12):
        confidence = "STRONG"
    elif abs_score >= min_sc:
        confidence = "VALID"
    else:
        confidence = "WAIT"

    sl = tp = None
    if price > 0:
        risk = max(atr_pct / 100 * price, price * 0.006)
        if side == "BUY":
            sl, tp = price - risk, price + risk * 1.8
        else:
            sl, tp = price + risk, price - risk * 1.8

    return ScannerSignal(
        symbol=symbol, side=side,
        score=round(abs_score, 3), confidence=confidence,
        reasons=reasons[:8], timeframe=timeframe,
        entry=price or None, stop_loss=sl, take_profit=tp,
    )


def rank_opportunities(
    items: Iterable[Dict[str, Any]],
    timeframe: str = "5m",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    out = []
    for item in items:
        sym = item.get("symbol") or item.get("pair") or item.get("ticker")
        if not sym:
            continue
        sig = analyze_market_snapshot(sym, item, item.get("timeframe", timeframe))
        if sig.confidence != "WAIT":
            out.append(sig.to_dict())
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:limit]
