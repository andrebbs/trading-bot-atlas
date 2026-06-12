"""
Elliott Wave Detector v2 - INSTITUCIONAL
ATLAS v2 — Advanced Technical Liquidity Analysis System

Melhorias v2:
  - wave_valid só True quando estrutura completa identificada
  - Score neutro-baixo quando contagem inválida
  - Impulse wave com validação de proporção das ondas
  - Momentum como confirmador secundário
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ElliottWaveDetector:
    """
    Elliott Wave v2 — Confirmador de momentum.

    Uso correto:
      Elliott NÃO decide o trade.
      Ele confirma se o momentum está em fase de impulso ou correção.

    wave_valid = True apenas quando estrutura claramente identificada.
    """

    def __init__(self, lookback_period: int = 100):
        self.lookback = lookback_period

    def _find_swing_points(self, df: pd.DataFrame, window: int = 5) -> Tuple[List, List]:
        data  = df.tail(self.lookback).reset_index(drop=True)
        highs, lows = [], []
        for i in range(window, len(data) - window):
            if data['high'].iloc[i] == data['high'].iloc[i-window:i+window+1].max():
                highs.append((i, float(data['high'].iloc[i])))
            if data['low'].iloc[i] == data['low'].iloc[i-window:i+window+1].min():
                lows.append((i, float(data['low'].iloc[i])))
        return highs, lows

    def detect_impulse_wave(self, df: pd.DataFrame) -> Dict:
        """
        Onda de impulso (5 ondas):
        W1 alta → W2 correção → W3 alta (maior) → W4 correção → W5 alta.
        Retorna wave_valid=True apenas se estrutura clara.
        """
        try:
            highs, lows = self._find_swing_points(df)
            if len(highs) < 3 or len(lows) < 2:
                return {'detected': False, 'wave_valid': False, 'direction': 'unknown'}

            # Pegar últimos swings
            sh = sorted(highs[-4:], key=lambda x: x[0])
            sl = sorted(lows[-3:],  key=lambda x: x[0])

            if len(sh) < 3 or len(sl) < 2:
                return {'detected': False, 'wave_valid': False, 'direction': 'unknown'}

            # Validar sequência de alta: cada topo > anterior
            tops_ascending = all(sh[i][1] < sh[i+1][1] for i in range(len(sh)-1))
            # Fundos ascendentes
            bots_ascending = all(sl[i][1] < sl[i+1][1] for i in range(len(sl)-1))

            # Regra: W3 nunca pode ser a menor (comparar diferenças)
            if tops_ascending and bots_ascending and len(sh) >= 3:
                w1 = sh[1][1] - sl[0][1]
                w3 = sh[2][1] - sl[1][1]
                if w3 > w1:  # W3 > W1 (regra básica Elliott)
                    return {'detected': True, 'wave_valid': True, 'direction': 'bullish',
                            'current_wave': 3, 'confidence': 0.70}

            # Impulso de baixa
            tops_desc = all(sh[i][1] > sh[i+1][1] for i in range(len(sh)-1))
            bots_desc = all(sl[i][1] > sl[i+1][1] for i in range(len(sl)-1))
            if tops_desc and bots_desc and len(sl) >= 3:
                w1 = sl[0][1] - sh[1][1]
                w3 = sl[1][1] - sh[2][1]
                if w3 > w1:
                    return {'detected': True, 'wave_valid': True, 'direction': 'bearish',
                            'current_wave': 3, 'confidence': 0.70}

            return {'detected': False, 'wave_valid': False, 'direction': 'unknown'}
        except Exception as e:
            logger.debug(f"Erro impulse: {e}")
            return {'detected': False, 'wave_valid': False, 'direction': 'unknown'}

    def detect_corrective_wave(self, df: pd.DataFrame) -> Dict:
        """
        Onda corretiva (ABC):
        Detecta quando mercado está em correção (melhor aguardar).
        """
        try:
            highs, lows = self._find_swing_points(df)
            if len(highs) < 2 or len(lows) < 2:
                return {'detected': False, 'wave_valid': False}

            sh = sorted(highs[-3:], key=lambda x: x[0])
            sl = sorted(lows[-3:],  key=lambda x: x[0])

            if len(sh) < 2 or len(sl) < 2:
                return {'detected': False, 'wave_valid': False}

            # ABC bullish: queda, subida, queda (pullback normal)
            tops_desc = sh[-1][1] < sh[-2][1]
            bots_asc  = sl[-1][1] > sl[-2][1] if len(sl) >= 2 else False

            if tops_desc and bots_asc:
                return {'detected': True, 'wave_valid': True, 'type': 'ABC_bullish_correction'}

            tops_asc = sh[-1][1] > sh[-2][1]
            bots_desc = sl[-1][1] < sl[-2][1] if len(sl) >= 2 else False

            if tops_asc and bots_desc:
                return {'detected': True, 'wave_valid': True, 'type': 'ABC_bearish_correction'}

            return {'detected': False, 'wave_valid': False}
        except Exception as e:
            return {'detected': False, 'wave_valid': False}

    def get_wave_momentum(self, df: pd.DataFrame) -> str:
        """Retorna momentum atual: impulse_up | impulse_down | corrective | unknown."""
        try:
            impulse = self.detect_impulse_wave(df)
            if impulse['wave_valid']:
                return f"impulse_{impulse['direction']}"
            corrective = self.detect_corrective_wave(df)
            if corrective['wave_valid']:
                return 'corrective'
            return 'unknown'
        except Exception:
            return 'unknown'

    # ──────────────────────────────────────────────────────────────────
    # ELLIOTT SCORE v2
    # ──────────────────────────────────────────────────────────────────
    def get_elliott_score(self, df: pd.DataFrame, direction: str) -> float:
        """
        Score Elliott v2.
        Se contagem inválida → máximo 0.40 (não contamina confluência).
        """
        try:
            impulse    = self.detect_impulse_wave(df)
            corrective = self.detect_corrective_wave(df)
            momentum   = self.get_wave_momentum(df)

            # Sem contagem válida → neutro baixo
            if not impulse['wave_valid'] and not corrective['wave_valid']:
                return 0.35

            score = 0.5

            if direction == 'BUY':
                if impulse['wave_valid'] and impulse['direction'] == 'bullish':
                    score += 0.30 * impulse.get('confidence', 0.7)
                elif impulse['wave_valid'] and impulse['direction'] == 'bearish':
                    score -= 0.25
                if corrective['wave_valid'] and 'bullish' in corrective.get('type', ''):
                    score += 0.15  # fim de correção = entrada
                if momentum == 'corrective':
                    score -= 0.10  # aguardar fim da correção

            else:  # SELL
                if impulse['wave_valid'] and impulse['direction'] == 'bearish':
                    score += 0.30 * impulse.get('confidence', 0.7)
                elif impulse['wave_valid'] and impulse['direction'] == 'bullish':
                    score -= 0.25
                if corrective['wave_valid'] and 'bearish' in corrective.get('type', ''):
                    score += 0.15
                if momentum == 'corrective':
                    score -= 0.10

            return float(np.clip(score, 0.0, 1.0))

        except Exception as e:
            logger.error(f"Erro Elliott score: {e}")
            return 0.35

    def get_analysis(self, df: pd.DataFrame) -> Dict:
        try:
            impulse    = self.detect_impulse_wave(df)
            corrective = self.detect_corrective_wave(df)
            momentum   = self.get_wave_momentum(df)
            return {
                'impulse_detected':    impulse['detected'],
                'wave_valid':           impulse['wave_valid'] or corrective['wave_valid'],
                'impulse_direction':   impulse.get('direction', 'unknown'),
                'corrective_detected': corrective['detected'],
                'wave_momentum':        momentum,
                'current_wave':         impulse.get('current_wave', None),
            }
        except Exception as e:
            logger.error(f"Erro Elliott analysis: {e}")
            return {'wave_valid': False, 'wave_momentum': 'unknown'}
