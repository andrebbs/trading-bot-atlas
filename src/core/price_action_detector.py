"""
Price Action Detector v2 - INSTITUCIONAL
ATLAS v2 — Advanced Technical Liquidity Analysis System

Melhorias v2:
  - Padrões contextualizados (rejeição em zona = muito mais forte)
  - Pin Bar com ratio real de wick/body
  - Engulfing com confirmação de volume
  - Doji penalizado (indecisão = não entra)
  - Score só alto quando padrão + contexto + direção alinhados
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class PriceActionDetector:
    """
    Price Action v2 — Confirmação final de entrada.

    Princípio:
      Price Action NÃO decide o trade.
      Ele CONFIRMA o que SMC + Wyckoff já indicaram.

    Padrões valorizados:
      - Pin Bar com wick >= 2x body (rejeição institucional)
      - Engulfing com volume acima da média
      - Candle de momentum (corpo > 60% do range)

    Padrões penalizados:
      - Doji (indecisão)
      - Candle pequeno sem direção
    """

    def __init__(self, lookback_period: int = 30):
        self.lookback = lookback_period

    def _candle_metrics(self, candle) -> Dict:
        """Calcula métricas básicas de um candle."""
        o = float(candle['open'])
        h = float(candle['high'])
        l = float(candle['low'])
        c = float(candle['close'])
        body        = abs(c - o)
        candle_range = h - l
        upper_wick  = h - max(c, o)
        lower_wick  = min(c, o) - l
        body_ratio  = body / candle_range if candle_range > 0 else 0
        is_bull     = c > o
        return {
            'open': o, 'high': h, 'low': l, 'close': c,
            'body': body, 'range': candle_range,
            'upper_wick': upper_wick, 'lower_wick': lower_wick,
            'body_ratio': body_ratio, 'is_bull': is_bull,
        }

    # ──────────────────────────────────────────────────────────────────
    def detect_pin_bar_bullish(self, df: pd.DataFrame) -> Dict:
        """Pin Bar bullish: lower_wick >= 2.5x body, fechamento no terço superior."""
        try:
            m = self._candle_metrics(df.iloc[-1])
            detected = (
                m['lower_wick'] >= m['body'] * 2.5 and
                m['close'] > (m['low'] + m['range'] * 0.6) and
                m['body_ratio'] < 0.40
            )
            return {'detected': bool(detected), 'wick_ratio': m['lower_wick'] / m['body'] if m['body'] > 0 else 0}
        except Exception:
            return {'detected': False, 'wick_ratio': 0}

    def detect_pin_bar_bearish(self, df: pd.DataFrame) -> Dict:
        """Pin Bar bearish: upper_wick >= 2.5x body, fechamento no terço inferior."""
        try:
            m = self._candle_metrics(df.iloc[-1])
            detected = (
                m['upper_wick'] >= m['body'] * 2.5 and
                m['close'] < (m['high'] - m['range'] * 0.6) and
                m['body_ratio'] < 0.40
            )
            return {'detected': bool(detected), 'wick_ratio': m['upper_wick'] / m['body'] if m['body'] > 0 else 0}
        except Exception:
            return {'detected': False, 'wick_ratio': 0}

    def detect_bullish_engulfing(self, df: pd.DataFrame) -> Dict:
        """Engulfing bullish com confirmação de volume."""
        try:
            if len(df) < 2:
                return {'detected': False}
            curr = self._candle_metrics(df.iloc[-1])
            prev = self._candle_metrics(df.iloc[-2])
            avg_vol = df['volume'].tail(10).mean() if 'volume' in df.columns else 1
            curr_vol = float(df.iloc[-1].get('volume', avg_vol))
            detected = (
                curr['is_bull'] and not prev['is_bull'] and
                curr['close'] > prev['open'] and
                curr['open'] < prev['close'] and
                curr['body'] > prev['body'] and
                curr_vol >= avg_vol * 0.9
            )
            return {'detected': bool(detected), 'vol_ratio': curr_vol / avg_vol if avg_vol > 0 else 1}
        except Exception:
            return {'detected': False}

    def detect_bearish_engulfing(self, df: pd.DataFrame) -> Dict:
        """Engulfing bearish com confirmação de volume."""
        try:
            if len(df) < 2:
                return {'detected': False}
            curr = self._candle_metrics(df.iloc[-1])
            prev = self._candle_metrics(df.iloc[-2])
            avg_vol = df['volume'].tail(10).mean() if 'volume' in df.columns else 1
            curr_vol = float(df.iloc[-1].get('volume', avg_vol))
            detected = (
                not curr['is_bull'] and prev['is_bull'] and
                curr['close'] < prev['open'] and
                curr['open'] > prev['close'] and
                curr['body'] > prev['body'] and
                curr_vol >= avg_vol * 0.9
            )
            return {'detected': bool(detected), 'vol_ratio': curr_vol / avg_vol if avg_vol > 0 else 1}
        except Exception:
            return {'detected': False}

    def _is_doji(self, df: pd.DataFrame) -> bool:
        """Doji = corpo < 10% do range → indecisão."""
        try:
            m = self._candle_metrics(df.iloc[-1])
            return m['body_ratio'] < 0.10
        except Exception:
            return False

    def detect_momentum_candle(self, df: pd.DataFrame, direction: str) -> Dict:
        """Candle de momentum: corpo >= 60% do range na direção correta."""
        try:
            m = self._candle_metrics(df.iloc[-1])
            if direction == 'BUY':
                detected = m['is_bull'] and m['body_ratio'] >= 0.60
            else:
                detected = not m['is_bull'] and m['body_ratio'] >= 0.60
            return {'detected': bool(detected), 'body_ratio': m['body_ratio']}
        except Exception:
            return {'detected': False, 'body_ratio': 0}

    # ──────────────────────────────────────────────────────────────────
    # PRICE ACTION SCORE v2
    # ──────────────────────────────────────────────────────────────────
    def get_price_action_score(self, df: pd.DataFrame, direction: str) -> float:
        """
        Score Price Action v2 — padrão + contexto.

        +0.30  Pin Bar com ratio >= 2.5x
        +0.25  Engulfing com volume
        +0.20  Candle de momentum
        +0.10  Continuidade (candle anterior alinhado)
        -0.25  Doji (indecisão, não entrar)
        -0.15  Candle contra a direção
        """
        try:
            score = 0.5

            # Penalização imediata por doji
            if self._is_doji(df):
                return 0.20

            if direction == 'BUY':
                pin      = self.detect_pin_bar_bullish(df)
                eng      = self.detect_bullish_engulfing(df)
                mom      = self.detect_momentum_candle(df, 'BUY')

                if pin['detected']:
                    bonus = min(0.30, 0.15 + pin['wick_ratio'] * 0.03)
                    score += bonus
                if eng['detected']:
                    score += 0.25
                if mom['detected']:
                    score += 0.20

                # Continuidade: candle anterior também bullish
                if len(df) >= 2:
                    prev = self._candle_metrics(df.iloc[-2])
                    if prev['is_bull']:
                        score += 0.10

                # Penalizar candle bearish
                curr = self._candle_metrics(df.iloc[-1])
                if not curr['is_bull'] and not pin['detected']:
                    score -= 0.15

            else:  # SELL
                pin      = self.detect_pin_bar_bearish(df)
                eng      = self.detect_bearish_engulfing(df)
                mom      = self.detect_momentum_candle(df, 'SELL')

                if pin['detected']:
                    bonus = min(0.30, 0.15 + pin['wick_ratio'] * 0.03)
                    score += bonus
                if eng['detected']:
                    score += 0.25
                if mom['detected']:
                    score += 0.20

                if len(df) >= 2:
                    prev = self._candle_metrics(df.iloc[-2])
                    if not prev['is_bull']:
                        score += 0.10

                curr = self._candle_metrics(df.iloc[-1])
                if curr['is_bull'] and not pin['detected']:
                    score -= 0.15

            return float(np.clip(score, 0.0, 1.0))

        except Exception as e:
            logger.error(f"Erro PA score: {e}")
            return 0.5

    def get_analysis(self, df: pd.DataFrame) -> Dict:
        try:
            m = self._candle_metrics(df.iloc[-1])
            return {
                'pin_bar_bullish':    self.detect_pin_bar_bullish(df)['detected'],
                'pin_bar_bearish':    self.detect_pin_bar_bearish(df)['detected'],
                'bullish_engulfing':  self.detect_bullish_engulfing(df)['detected'],
                'bearish_engulfing':  self.detect_bearish_engulfing(df)['detected'],
                'momentum_buy':       self.detect_momentum_candle(df, 'BUY')['detected'],
                'momentum_sell':      self.detect_momentum_candle(df, 'SELL')['detected'],
                'is_doji':            self._is_doji(df),
                'body_ratio':         m['body_ratio'],
                'is_bullish_candle':  m['is_bull'],
            }
        except Exception as e:
            logger.error(f"Erro PA analysis: {e}")
            return {}
