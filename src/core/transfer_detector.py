"""
Transfer Detector — Liquidity Transfer / Displacement Reversal
ATLAS v6 — Advanced Technical Liquidity Analysis System

Conceito (transferencia):
  Captura de liquidez + rejeicao = trava na ponta do pavio.

Regras:
  Bullish Transfer (compra com compra):
    - 1a vela do lote/candle atual tem pavio inferior relevante (>= ~45% do range)
    - Pavio superior pequeno (<= ~30%)
    - Sweep a minima local (low < min dos ultimos N)
    - Fechamento recuperado (close_position >= 0.55)
    - (Opcional) confirmacao de compra na vela seguinte

  Bearish Transfer (venda com venda):
    - Pavio superior relevante (>= ~45%)
    - Pavio inferior pequeno (<= ~30%)
    - Sweep a maxima local
    - Fechamento pressionado (close_position <= 0.45)
    - (Opcional) confirmacao de venda na vela seguinte

  Split Rate (taxa dividida):
    - Rompimento limpo (pavio pequeno) de um lado numa vela
    - Confirmacao na outra direcao na vela seguinte
    - (alias de "displacement")

Retorna score 0.0-1.0 por direcao e nivel de stop (trava na ponta do pavio).
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class TransferDetector:
    def __init__(self, lookback_period: int = 30, sweep_window: int = 10):
        self.lookback = lookback_period
        self.sweep_window = sweep_window

    def _candle_metrics(self, row) -> Dict:
        o = float(row['open']); h = float(row['high'])
        l = float(row['low']);  c = float(row['close'])
        rng = h - l
        if rng <= 0:
            rng = 1e-9
        body = abs(c - o)
        upper_wick = h - max(c, o)
        lower_wick = min(c, o) - l
        close_pos = (c - l) / rng if rng > 0 else 0.5
        return {
            'open': o, 'high': h, 'low': l, 'close': c, 'range': rng,
            'body': body,
            'upper_wick': upper_wick, 'lower_wick': lower_wick,
            'upper_wick_ratio': upper_wick / rng,
            'lower_wick_ratio': lower_wick / rng,
            'body_ratio': body / rng,
            'close_position': close_pos,
            'is_bull': c > o,
        }

    def detect_bullish_transfer(self, df: pd.DataFrame) -> Dict:
        if df is None or len(df) < self.sweep_window + 2:
            return {'detected': False, 'score': 0.0, 'stop': None, 'reason': 'data-curta'}
        cur = self._candle_metrics(df.iloc[-1])
        prev = self._candle_metrics(df.iloc[-2]) if len(df) >= 2 else None
        recent_lows = df['low'].iloc[-(self.sweep_window + 1):-1]
        recent_highs = df['high'].iloc[-(self.sweep_window + 1):-1]
        local_min = recent_lows.min() if len(recent_lows) else cur['low']
        local_max = recent_highs.max() if len(recent_highs) else cur['high']
        swept_low = cur['low'] < local_min
        lower_wick_ok = cur['lower_wick_ratio'] >= 0.45
        upper_wick_ok = cur['upper_wick_ratio'] <= 0.30
        close_recovered = cur['close_position'] >= 0.55
        confirmation = prev is not None and prev['is_bull']
        detected = swept_low and lower_wick_ok and upper_wick_ok and close_recovered
        if not detected:
            return {'detected': False, 'score': 0.0, 'stop': None, 'reason': 'regras-falham'}
        score = 0.55
        if cur['lower_wick_ratio'] >= 0.60: score += 0.10
        if confirmation: score += 0.10
        if cur['close_position'] >= 0.70: score += 0.08
        if local_max - local_min > 0 and cur['range'] < (local_max - local_min) * 0.6: score += 0.07
        score = min(1.0, score)
        return {
            'detected': True, 'score': float(score), 'stop': cur['low'],
            'swept_low': float(local_min), 'close_position': float(cur['close_position']),
            'lower_wick_ratio': float(cur['lower_wick_ratio']),
            'confirmation': bool(confirmation), 'reason': 'bullish-transfer',
        }

    def detect_bearish_transfer(self, df: pd.DataFrame) -> Dict:
        if df is None or len(df) < self.sweep_window + 2:
            return {'detected': False, 'score': 0.0, 'stop': None, 'reason': 'data-curta'}
        cur = self._candle_metrics(df.iloc[-1])
        prev = self._candle_metrics(df.iloc[-2]) if len(df) >= 2 else None
        recent_lows = df['low'].iloc[-(self.sweep_window + 1):-1]
        recent_highs = df['high'].iloc[-(self.sweep_window + 1):-1]
        local_min = recent_lows.min() if len(recent_lows) else cur['low']
        local_max = recent_highs.max() if len(recent_highs) else cur['high']
        swept_high = cur['high'] > local_max
        upper_wick_ok = cur['upper_wick_ratio'] >= 0.45
        lower_wick_ok = cur['lower_wick_ratio'] <= 0.30
        close_pressed = cur['close_position'] <= 0.45
        confirmation = prev is not None and (not prev['is_bull'])
        detected = swept_high and upper_wick_ok and lower_wick_ok and close_pressed
        if not detected:
            return {'detected': False, 'score': 0.0, 'stop': None, 'reason': 'regras-falham'}
        score = 0.55
        if cur['upper_wick_ratio'] >= 0.60: score += 0.10
        if confirmation: score += 0.10
        if cur['close_position'] <= 0.30: score += 0.08
        if local_max - local_min > 0 and cur['range'] < (local_max - local_min) * 0.6: score += 0.07
        score = min(1.0, score)
        return {
            'detected': True, 'score': float(score), 'stop': cur['high'],
            'swept_high': float(local_max), 'close_position': float(cur['close_position']),
            'upper_wick_ratio': float(cur['upper_wick_ratio']),
            'confirmation': bool(confirmation), 'reason': 'bearish-transfer',
        }

    def detect_split_rate(self, df: pd.DataFrame) -> Dict:
        if df is None or len(df) < 3:
            return {'direction': None, 'score': 0.0}
        prev = self._candle_metrics(df.iloc[-2])
        cur = self._candle_metrics(df.iloc[-1])
        breakout_up = (prev['is_bull']) and (prev['upper_wick_ratio'] <= 0.25)
        confirm_up = cur['is_bull']
        if breakout_up and confirm_up:
            return {'direction': 'BUY', 'score': 0.65}
        breakout_down = (not prev['is_bull']) and (prev['lower_wick_ratio'] <= 0.25)
        confirm_down = (not cur['is_bull'])
        if breakout_down and confirm_down:
            return {'direction': 'SELL', 'score': 0.65}
        return {'direction': None, 'score': 0.0}

    def get_transfer_score(self, df: pd.DataFrame, direction: str) -> Tuple[float, Dict]:
        info = {'transfer': None, 'split': None}
        score = 0.0
        try:
            if direction == 'BUY':
                t = self.detect_bullish_transfer(df)
                if t['detected']:
                    score = max(score, t['score'])
                    info['transfer'] = t
            elif direction == 'SELL':
                t = self.detect_bearish_transfer(df)
                if t['detected']:
                    score = max(score, t['score'])
                    info['transfer'] = t
            split = self.detect_split_rate(df)
            if split.get('direction') == direction:
                score = max(score, split['score'])
                info['split'] = split
        except Exception as e:
            logger.debug(f"TransferDetector error: {e}")
        return float(min(1.0, score)), info
