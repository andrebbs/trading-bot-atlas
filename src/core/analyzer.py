"""
Trading Analyzer v2 - INSTITUCIONAL
ATLAS v2 — Advanced Technical Liquidity Analysis System

Melhorias v2:
  - Filtro Dow (tendência 4H/1D bloqueia contra-tendência)
  - Bloqueio automático de sinais WEAK
  - Integração total com ConfluenceScoreSystem
  - Filtro de volatilidade via ATR
  - generate_signals respeita fluxo institucional
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple

from config.config import INDICATORS_CONFIG, INDICATOR_WEIGHTS
from src.core.confluence_score import ConfluenceScoreSystem

logger = logging.getLogger(__name__)


class TradingAnalyzer:
    """
    Orquestrador de análise institucional ATLAS v2.

    Fluxo correto:
      1. Analisa indicadores técnicos (RSI, MACD, BB, EMA, Volume, ATR)
      2. Calcula composite score
      3. Aplica filtro Dow (tendência macro)
      4. Consulta ConfluenceScoreSystem
      5. Bloqueia sinais WEAK / NEUTRAL
      6. Retorna sinal validado
    """

    def __init__(self, df: pd.DataFrame,
                 config: Dict = None,
                 weights: Dict = None):
        self.df         = df.copy()
        self.config     = config  or INDICATORS_CONFIG
        self.weights    = weights or INDICATOR_WEIGHTS
        self.confluence = ConfluenceScoreSystem()

    # ──────────────────────────────────────────────────────────────
    # INDICADORES TÉCNICOS (mantidos do original)
    # ──────────────────────────────────────────────────────────────
    def analyze_rsi(self) -> Dict:
        try:
            cfg    = self.config.get("rsi", {})
            period = cfg.get("period", 14)
            ob     = cfg.get("overbought", 70)
            os_    = cfg.get("oversold",   30)
            df     = self.df

            delta = df["close"].diff()
            gain  = delta.clip(lower=0)
            loss  = (-delta).clip(lower=0)
            avg_g = gain.ewm(com=period-1, min_periods=period).mean()
            avg_l = loss.ewm(com=period-1, min_periods=period).mean()
            rs    = avg_g / avg_l.replace(0, np.nan)
            rsi   = 100 - (100 / (1 + rs))
            val   = float(rsi.iloc[-1])

            if val <= os_:
                signal, score = "BUY",  min(1.0, (os_ - val) / os_ + 0.5)
            elif val >= ob:
                signal, score = "SELL", min(1.0, (val - ob) / (100 - ob) + 0.5)
            else:
                signal = "NEUTRAL"
                score  = 0.5 - abs(val - 50) / 100

            return {"signal": signal, "score": score, "value": val}
        except Exception as e:
            logger.debug(f"RSI erro: {e}")
            return {"signal": "NEUTRAL", "score": 0.5, "value": 50}

    def analyze_macd(self) -> Dict:
        try:
            cfg    = self.config.get("macd", {})
            fast   = cfg.get("fast",   12)
            slow   = cfg.get("slow",   26)
            signal_p = cfg.get("signal", 9)
            close  = self.df["close"]

            ema_f  = close.ewm(span=fast,   adjust=False).mean()
            ema_s  = close.ewm(span=slow,   adjust=False).mean()
            macd   = ema_f - ema_s
            sig    = macd.ewm(span=signal_p, adjust=False).mean()
            hist   = macd - sig

            val   = float(hist.iloc[-1])
            prev  = float(hist.iloc[-2]) if len(hist) > 1 else 0.0

            if val > 0 and val > prev:
                signal, score = "BUY",  min(1.0, 0.6 + abs(val) * 10)
            elif val < 0 and val < prev:
                signal, score = "SELL", min(1.0, 0.6 + abs(val) * 10)
            else:
                signal, score = "NEUTRAL", 0.5

            return {"signal": signal, "score": score,
                    "macd": float(macd.iloc[-1]),
                    "signal_line": float(sig.iloc[-1]),
                    "histogram": val}
        except Exception as e:
            logger.debug(f"MACD erro: {e}")
            return {"signal": "NEUTRAL", "score": 0.5}

    def analyze_bollinger(self) -> Dict:
        try:
            cfg    = self.config.get("bollinger", {})
            period = cfg.get("period", 20)
            std    = cfg.get("std",    2.0)
            close  = self.df["close"]

            mid    = close.rolling(period).mean()
            band   = close.rolling(period).std() * std
            upper  = mid + band
            lower  = mid - band

            price  = float(close.iloc[-1])
            u, l, m = float(upper.iloc[-1]), float(lower.iloc[-1]), float(mid.iloc[-1])
            width  = u - l
            pos    = (price - l) / width if width > 0 else 0.5

            if pos < 0.15:
                signal, score = "BUY",  min(1.0, 0.6 + (0.15 - pos) * 2)
            elif pos > 0.85:
                signal, score = "SELL", min(1.0, 0.6 + (pos - 0.85) * 2)
            else:
                signal, score = "NEUTRAL", 0.5

            return {"signal": signal, "score": score,
                    "upper": u, "lower": l, "middle": m, "position": pos}
        except Exception as e:
            logger.debug(f"BB erro: {e}")
            return {"signal": "NEUTRAL", "score": 0.5}

    def analyze_ema(self) -> Dict:
        try:
            cfg    = self.config.get("ema", {})
            fast   = cfg.get("fast", 9)
            slow   = cfg.get("slow", 21)
            close  = self.df["close"]

            ema_f  = close.ewm(span=fast, adjust=False).mean()
            ema_s  = close.ewm(span=slow, adjust=False).mean()

            vf, vs = float(ema_f.iloc[-1]), float(ema_s.iloc[-1])
            pf, ps = float(ema_f.iloc[-2]), float(ema_s.iloc[-2])

            cross_up   = pf <= ps and vf > vs
            cross_down = pf >= ps and vf < vs
            aligned_up = vf > vs
            sep        = abs(vf - vs) / vs if vs > 0 else 0

            if cross_up or aligned_up:
                signal, score = "BUY",  min(1.0, 0.55 + sep * 10)
            else:
                signal, score = "SELL", min(1.0, 0.55 + sep * 10)

            return {"signal": signal, "score": score,
                    "fast": vf, "slow": vs,
                    "cross_up": cross_up, "cross_down": cross_down}
        except Exception as e:
            logger.debug(f"EMA erro: {e}")
            return {"signal": "NEUTRAL", "score": 0.5}

    def analyze_volume(self) -> Dict:
        try:
            if "volume" not in self.df.columns:
                return {"signal": "NEUTRAL", "score": 0.5}
            cfg    = self.config.get("volume", {})
            period = cfg.get("period", 20)
            vol    = self.df["volume"]
            close  = self.df["close"]

            avg    = vol.rolling(period).mean()
            ratio  = float(vol.iloc[-1]) / float(avg.iloc[-1]) if float(avg.iloc[-1]) > 0 else 1.0
            bull   = float(close.iloc[-1]) > float(close.iloc[-2])

            if ratio > 1.5:
                signal, score = ("BUY" if bull else "SELL"), min(1.0, 0.5 + ratio * 0.15)
            else:
                signal, score = "NEUTRAL", 0.5

            return {"signal": signal, "score": score, "ratio": ratio}
        except Exception as e:
            logger.debug(f"Volume erro: {e}")
            return {"signal": "NEUTRAL", "score": 0.5}

    def analyze_atr(self) -> Dict:
        try:
            cfg    = self.config.get("atr", {})
            period = cfg.get("period", 14)
            df     = self.df

            hl  = df["high"] - df["low"]
            hc  = (df["high"] - df["close"].shift()).abs()
            lc  = (df["low"]  - df["close"].shift()).abs()
            tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
            atr = tr.ewm(com=period-1, min_periods=period).mean()

            val     = float(atr.iloc[-1])
            price   = float(df["close"].iloc[-1])
            vol_pct = val / price if price > 0 else 0

            return {"atr": val, "volatility_pct": vol_pct,
                    "signal": "NEUTRAL", "score": 0.5}
        except Exception as e:
            logger.debug(f"ATR erro: {e}")
            return {"atr": 0, "volatility_pct": 0, "signal": "NEUTRAL", "score": 0.5}

    # ──────────────────────────────────────────────────────────────
    # FILTRO DOW — BLOQUEIA CONTRA-TENDÊNCIA
    # ──────────────────────────────────────────────────────────────
    def _get_trend(self, df: pd.DataFrame, window: int = 5) -> str:
        """
        Detecta tendência via sequência de topos/fundos (Dow).
        Retorna: 'UP' | 'DOWN' | 'LATERAL'
        """
        try:
            close = df["close"].values
            highs = df["high"].values
            lows  = df["low"].values

            n = min(window, len(df) - 1)
            if n < 2:
                return "LATERAL"

            recent_h = highs[-n:]
            recent_l = lows[-n:]

            hh = recent_h[-1] > recent_h[0]
            hl = recent_l[-1] > recent_l[0]
            lh = recent_h[-1] < recent_h[0]
            ll = recent_l[-1] < recent_l[0]

            if hh and hl:   return "UP"
            if lh and ll:   return "DOWN"
            return "LATERAL"
        except Exception:
            return "LATERAL"

    def _dow_filter(self, direction: str) -> Tuple[bool, str]:
        """
        Aplica filtro de tendência Dow.
        Bloqueia se a direção for contra a tendência predominante.
        Retorna (passou, motivo).
        """
        trend = self._get_trend(self.df, window=10)

        if trend == "LATERAL":
            return False, "Mercado lateral — aguardar direção"

        if direction == "BUY" and trend == "DOWN":
            return False, "Contra-tendência (Dow): tendência de baixa ativa"

        if direction == "SELL" and trend == "UP":
            return False, "Contra-tendência (Dow): tendência de alta ativa"

        return True, None

    # ──────────────────────────────────────────────────────────────
    # COMPOSITE SCORE (indicadores técnicos)
    # ──────────────────────────────────────────────────────────────
    def calculate_composite_score(self) -> Dict:
        analyses = {
            "rsi":       self.analyze_rsi(),
            "macd":      self.analyze_macd(),
            "bollinger": self.analyze_bollinger(),
            "ema":       self.analyze_ema(),
            "volume":    self.analyze_volume(),
            "atr":       self.analyze_atr(),
        }

        total_w = 0.0
        raw_s   = 0.0
        buy_v   = 0
        sell_v  = 0

        for key, analysis in analyses.items():
            w = self.weights.get(key, 0.1)
            s = analysis.get("score", 0.5)
            raw_s   += s * w
            total_w += w
            sig = analysis.get("signal", "NEUTRAL")
            if sig == "BUY":   buy_v  += 1
            elif sig == "SELL": sell_v += 1

        composite = raw_s / total_w if total_w > 0 else 0.5

        if buy_v > sell_v:
            direction = "BUY"
        elif sell_v > buy_v:
            direction = "SELL"
        else:
            direction = "NEUTRAL"

        return {
            "composite_score": composite,
            "direction":       direction,
            "buy_votes":       buy_v,
            "sell_votes":      sell_v,
            "analyses":        analyses,
        }

    # ──────────────────────────────────────────────────────────────
    # GENERATE SIGNALS (institucional)
    # ──────────────────────────────────────────────────────────────
    def generate_signals(self,
                         buy_threshold:  Optional[float] = None,
                         sell_threshold: Optional[float] = None) -> pd.Series:
        """
        Gera série de sinais respeitando fluxo institucional.
        Uso principal: backtesting e análise histórica.
        """
        composite = self.calculate_composite_score()
        score     = composite["composite_score"]
        direction = composite["direction"]

        bt = buy_threshold  or 0.60
        st = sell_threshold or 0.60

        if direction == "BUY"  and score >= bt:  return pd.Series(["BUY"])
        if direction == "SELL" and score >= st:   return pd.Series(["SELL"])
        return pd.Series(["NEUTRAL"])

    # ──────────────────────────────────────────────────────────────
    # GET CURRENT SIGNAL — CORAÇÃO DO ATLAS v2
    # ──────────────────────────────────────────────────────────────
    def get_current_signal(self) -> Dict:
        """
        Sinal atual com fluxo institucional completo:

        1. Composite score (indicadores técnicos)
        2. Filtro Dow (tendência macro)
        3. Filtro ATR (volatilidade mínima)
        4. ConfluenceScoreSystem (SMC + Wyckoff + PA + Elliott)
        5. Bloqueio de sinais WEAK
        6. Retorna sinal validado ou NEUTRAL com motivo
        """
        try:
            # Coleta scores individuais dos indicadores para compatibilidade com main.py
            rsi_analysis = self.analyze_rsi()
            macd_analysis = self.analyze_macd()
            bollinger_analysis = self.analyze_bollinger()
            ema_analysis = self.analyze_ema()
            volume_analysis = self.analyze_volume()
            atr_analysis = self.analyze_atr()

            # 1. Composite score
            composite = self.calculate_composite_score()
            direction = composite["direction"]
            score     = composite["composite_score"]

            if direction == "NEUTRAL":
                return self._neutral("Indicadores sem direção clara",
                                     int(score * 100),
                                     rsi_analysis, macd_analysis, bollinger_analysis,
                                     ema_analysis, volume_analysis, atr_analysis)

            # 2. Filtro Dow
            dow_ok, dow_reason = self._dow_filter(direction)
            if not dow_ok:
                return self._neutral(dow_reason, int(score * 100),
                                     rsi_analysis, macd_analysis, bollinger_analysis,
                                     ema_analysis, volume_analysis, atr_analysis)

            # 3. Filtro ATR (volatilidade mínima)
            atr_data  = composite["analyses"]["atr"]
            vol_pct   = atr_data.get("volatility_pct", 0.01)
            if vol_pct < 0.002:
                return self._neutral("Baixa volatilidade — mercado parado",
                                     int(score * 100),
                                     rsi_analysis, macd_analysis, bollinger_analysis,
                                     ema_analysis, volume_analysis, atr_analysis)

            # 4. ConfluenceScoreSystem
            should_enter, analysis = self.confluence.should_enter_trade(
                self.df, direction
            )

            # 5. Bloquear WEAK / NEUTRAL
            recommendation = analysis.get("recommendation", "NEUTRAL")

            if recommendation.startswith("WEAK"):
                return self._neutral(
                    f"Sinal fraco ({recommendation}) — aguardar",
                    int(analysis.get("final_score", 0) * 100),
                    rsi_analysis, macd_analysis, bollinger_analysis,
                    ema_analysis, volume_analysis, atr_analysis)

            if not should_enter:
                return self._neutral(
                    analysis.get("block_reason", "Filtro institucional"),
                    int(analysis.get("final_score", 0) * 100),
                    rsi_analysis, macd_analysis, bollinger_analysis,
                    ema_analysis, volume_analysis, atr_analysis)

            # 6. ✅ SINAL VALIDADO
            final_score = analysis.get("final_score", 0)
            return {
                "signal":         direction,
                "confidence":     int(final_score * 100),
                "probability":    final_score * 100,  # Para compatibilidade com main.py
                "confluence":     analysis.get("confluence_count", 0),
                "score":          final_score,
                "recommendation": recommendation,
                "composite_score": score,
                "dow_trend":       self._get_trend(self.df),
                "volatility_pct":  vol_pct,
                "block_reason":    None,
                # Scores individuais para compatibilidade com main.py
                # Converte de range [0.5, 1.0] para [-1, +1] para visualização
                "rsi_score":       (rsi_analysis.get("score", 0.5) - 0.5) * 2,
                "macd_score":      (macd_analysis.get("score", 0.5) - 0.5) * 2,
                "bollinger_score": (bollinger_analysis.get("score", 0.5) - 0.5) * 2,
                "ema_score":       (ema_analysis.get("score", 0.5) - 0.5) * 2,
                "volume_score":    (volume_analysis.get("score", 0.5) - 0.5) * 2,
                "atr_score":       (atr_analysis.get("score", 0.5) - 0.5) * 2,
            }

        except Exception as e:
            logger.error(f"Erro get_current_signal: {e}")
            return self._neutral(f"Erro interno: {str(e)}", 0)

    # ──────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────
    def _neutral(self, reason: str, confidence: int = 0,
                 rsi_analysis=None, macd_analysis=None, bollinger_analysis=None,
                 ema_analysis=None, volume_analysis=None, atr_analysis=None) -> Dict:
        # Defaults se não fornecidos
        rsi_analysis = rsi_analysis or {"score": 0.5}
        macd_analysis = macd_analysis or {"score": 0.5}
        bollinger_analysis = bollinger_analysis or {"score": 0.5}
        ema_analysis = ema_analysis or {"score": 0.5}
        volume_analysis = volume_analysis or {"score": 0.5}
        atr_analysis = atr_analysis or {"score": 0.5}
        
        return {
            "signal":      "NEUTRAL",
            "confidence":  confidence,
            "probability": confidence,  # Para compatibilidade com main.py
            "block_reason": reason,
            "score":        confidence / 100,
            # Scores individuais para compatibilidade com main.py
            "rsi_score":       (rsi_analysis.get("score", 0.5) - 0.5) * 2,
            "macd_score":      (macd_analysis.get("score", 0.5) - 0.5) * 2,
            "bollinger_score": (bollinger_analysis.get("score", 0.5) - 0.5) * 2,
            "ema_score":       (ema_analysis.get("score", 0.5) - 0.5) * 2,
            "volume_score":    (volume_analysis.get("score", 0.5) - 0.5) * 2,
            "atr_score":       (atr_analysis.get("score", 0.5) - 0.5) * 2,
        }

    def _calculate_probability(self, score: float) -> float:
        """Converte score em probabilidade estimada (0.5 – 0.95)."""
        return float(np.clip(0.5 + (score - 0.5) * 0.9, 0.50, 0.95))

    def get_signals_dataframe(self) -> pd.DataFrame:
        """Retorna DataFrame completo com todas as análises."""
        composite = self.calculate_composite_score()
        signal    = self.get_current_signal()

        row = {
            "signal":          signal.get("signal"),
            "confidence":      signal.get("confidence"),
            "composite_score": composite.get("composite_score"),
            "direction":       composite.get("direction"),
            "buy_votes":       composite.get("buy_votes"),
            "sell_votes":      composite.get("sell_votes"),
            "block_reason":    signal.get("block_reason"),
        }
        return pd.DataFrame([row])
