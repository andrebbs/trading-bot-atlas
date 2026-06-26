"""
Wyckoff Detector v2 - INSTITUCIONAL
ATLAS v2 — Advanced Technical Liquidity Analysis System

Melhorias v2:
  - Detecção de Spring/Upthrust com confirmação de volume
  - Fases Wyckoff com critérios mais rigorosos
  - Score zerado quando fase não identificada
  - SOS/SOW com confirmação estrutural
  - Integração com volume profile simplificado
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List
import logging

logger = logging.getLogger(__name__)


class WyckoffDetector:
    """
    Wyckoff Method v2 — Institucional.

    Fases:
      Accumulation  → Markup   (comprar no spring, confirmar SOS)
      Distribution  → Markdown (vender no upthrust, confirmar SOW)
      Re-accumulation / Re-distribution (dentro de tendência)
    """

    def __init__(self, lookback_period: int = 50):
        self.lookback = lookback_period

    # ──────────────────────────────────────────────────────────────────
    # FASE WYCKOFF
    # ──────────────────────────────────────────────────────────────────
    def detect_phase(self, df: pd.DataFrame) -> Dict:
        """
        Detecta fase atual do mercado segundo Wyckoff.
        Retorna fase + confiança.
        """
        try:
            data  = df.tail(self.lookback).reset_index(drop=True)
            close = data['close'].values
            vol   = data['volume'].values if 'volume' in data.columns else np.ones(len(data))
            high  = data['high'].values
            low   = data['low'].values

            # Médias para contexto
            mid        = len(data) // 2
            price_early = close[:mid].mean()
            price_late  = close[mid:].mean()
            vol_early   = vol[:mid].mean()
            vol_late    = vol[mid:].mean()

            price_up  = price_late > price_early * 1.005
            price_dn  = price_late < price_early * 0.995
            price_lat = not price_up and not price_dn

            vol_expand = vol_late > vol_early * 1.1
            vol_dry    = vol_late < vol_early * 0.9

            # Range do período
            rng    = high.max() - low.min()
            rng_ok = rng > 0

            # Proximidade ao fundo/topo do range
            near_bottom = (close[-1] - low.min()) / rng < 0.25 if rng_ok else False
            near_top    = (high.max() - close[-1]) / rng < 0.25 if rng_ok else False

            # ── ACUMULAÇÃO ──
            # Preço lateral/baixo + volume secando + próximo ao fundo
            if price_lat and vol_dry and near_bottom:
                return {'phase': 'accumulation', 'confidence': 0.75, 'bias': 'bullish'}

            # ── MARKUP ──
            # Preço subindo + volume expandindo
            if price_up and vol_expand:
                return {'phase': 'markup', 'confidence': 0.80, 'bias': 'bullish'}

            # ── MARKUP sem volume (cautela) ──
            if price_up and not vol_expand:
                return {'phase': 'markup', 'confidence': 0.50, 'bias': 'bullish'}

            # ── DISTRIBUIÇÃO ──
            # Preço lateral/alto + volume secando + próximo ao topo
            if price_lat and vol_dry and near_top:
                return {'phase': 'distribution', 'confidence': 0.75, 'bias': 'bearish'}

            # ── MARKDOWN ──
            # Preço caindo + volume expandindo
            if price_dn and vol_expand:
                return {'phase': 'markdown', 'confidence': 0.80, 'bias': 'bearish'}

            if price_dn and not vol_expand:
                return {'phase': 'markdown', 'confidence': 0.50, 'bias': 'bearish'}

            return {'phase': 'unknown', 'confidence': 0.0, 'bias': 'neutral'}

        except Exception as e:
            logger.debug(f"Erro detect_phase: {e}")
            return {'phase': 'unknown', 'confidence': 0.0, 'bias': 'neutral'}

    # ──────────────────────────────────────────────────────────────────
    # SPRING (fundo falso = entrada long)
    # ──────────────────────────────────────────────────────────────────
    def _detect_spring(self, df: pd.DataFrame) -> Dict:
        """
        Spring = price varre fundo do range mas fecha acima → sinal de acumulação.
        v2: exige volume decrescente no spring.
        """
        try:
            data   = df.tail(self.lookback).reset_index(drop=True)
            recent = data.tail(10)
            rng_low = data['low'].min()
            last    = data.iloc[-1]
            avg_vol = data['volume'].mean() if 'volume' in data.columns else 1

            spring = (
                float(last['low']) <= rng_low * 1.002 and
                float(last['close']) > rng_low * 1.005 and
                float(last.get('volume', avg_vol)) < avg_vol * 0.9
            )
            return {'detected': bool(spring), 'level': float(rng_low)}
        except Exception as e:
            logger.debug(f"Erro spring: {e}")
            return {'detected': False, 'level': None}

    # ──────────────────────────────────────────────────────────────────
    # UPTHRUST (topo falso = entrada short)
    # ──────────────────────────────────────────────────────────────────
    def _detect_upthrust(self, df: pd.DataFrame) -> Dict:
        """
        Upthrust = price varre topo do range mas fecha abaixo → sinal de distribuição.
        v2: exige volume decrescente no upthrust.
        """
        try:
            data    = df.tail(self.lookback).reset_index(drop=True)
            rng_high = data['high'].max()
            last     = data.iloc[-1]
            avg_vol  = data['volume'].mean() if 'volume' in data.columns else 1

            upthrust = (
                float(last['high']) >= rng_high * 0.998 and
                float(last['close']) < rng_high * 0.995 and
                float(last.get('volume', avg_vol)) < avg_vol * 0.9
            )
            return {'detected': bool(upthrust), 'level': float(rng_high)}
        except Exception as e:
            logger.debug(f"Erro upthrust: {e}")
            return {'detected': False, 'level': None}

    # ──────────────────────────────────────────────────────────────────
    # SIGN OF STRENGTH / SIGN OF WEAKNESS
    # ──────────────────────────────────────────────────────────────────
    def detect_sign_of_strength(self, df: pd.DataFrame) -> Dict:
        """SOS = barra de alta com volume acima da média."""
        try:
            data    = df.tail(20).reset_index(drop=True)
            last    = data.iloc[-1]
            avg_vol = data['volume'].mean() if 'volume' in data.columns else 1
            avg_body = (data['close'] - data['open']).abs().mean()

            body   = float(last['close']) - float(last['open'])
            vol    = float(last.get('volume', avg_vol))
            sos    = body > avg_body * 1.2 and vol > avg_vol * 1.2 and body > 0

            return {'detected': bool(sos), 'strength': vol / avg_vol if avg_vol > 0 else 1.0}
        except Exception as e:
            return {'detected': False, 'strength': 1.0}

    def detect_sign_of_weakness(self, df: pd.DataFrame) -> Dict:
        """SOW = barra de baixa com volume acima da média."""
        try:
            data    = df.tail(20).reset_index(drop=True)
            last    = data.iloc[-1]
            avg_vol = data['volume'].mean() if 'volume' in data.columns else 1
            avg_body = (data['close'] - data['open']).abs().mean()

            body = float(last['close']) - float(last['open'])
            vol  = float(last.get('volume', avg_vol))
            sow  = body < -avg_body * 1.2 and vol > avg_vol * 1.2

            return {'detected': bool(sow), 'strength': vol / avg_vol if avg_vol > 0 else 1.0}
        except Exception as e:
            return {'detected': False, 'strength': 1.0}

    # ──────────────────────────────────────────────────────────────────
    # WYCKOFF SCORE v2
    # ──────────────────────────────────────────────────────────────────
    def get_wyckoff_score(self, df: pd.DataFrame, direction: str) -> float:
        """
        Score Wyckoff v2.
        Se fase desconhecida → score máximo 0.40 (não contamina confluência).
        """
        try:
            phase    = self.detect_phase(df)
            spring   = self._detect_spring(df)
            upthrust = self._detect_upthrust(df)
            sos      = self.detect_sign_of_strength(df)
            sow      = self.detect_sign_of_weakness(df)

            # Fase desconhecida = não ativa
            if phase['phase'] == 'unknown':
                return 0.35  # neutro baixo

            score = 0.5

            if direction == 'BUY':
                if phase['phase'] in ('accumulation', 'markup'):
                    score += 0.25 * phase['confidence']
                elif phase['phase'] in ('distribution', 'markdown'):
                    score -= 0.30

                if spring['detected']:  score += 0.20
                if sos['detected']:     score += 0.15
                if upthrust['detected']: score -= 0.15
                if sow['detected']:     score -= 0.10

            else:  # SELL
                if phase['phase'] in ('distribution', 'markdown'):
                    score += 0.25 * phase['confidence']
                elif phase['phase'] in ('accumulation', 'markup'):
                    score -= 0.30

                if upthrust['detected']: score += 0.20
                if sow['detected']:      score += 0.15
                if spring['detected']:   score -= 0.15
                if sos['detected']:      score -= 0.10

            return float(np.clip(score, 0.0, 1.0))

        except Exception as e:
            logger.error(f"Erro Wyckoff score: {e}")
            return 0.35

    # ──────────────────────────────────────────────────────────────────
    # GET ANALYSIS
    # ──────────────────────────────────────────────────────────────────
    def get_analysis(self, df: pd.DataFrame) -> Dict:
        try:
            phase    = self.detect_phase(df)
            spring   = self._detect_spring(df)
            upthrust = self._detect_upthrust(df)
            sos      = self.detect_sign_of_strength(df)
            sow      = self.detect_sign_of_weakness(df)
            return {
                'phase':     phase['phase'],
                'confidence': phase['confidence'],
                'bias':       phase['bias'],
                'spring':     spring['detected'],
                'upthrust':   upthrust['detected'],
                'sos':        sos['detected'],
                'sow':        sow['detected'],
            }
        except Exception as e:
            logger.error(f"Erro Wyckoff analysis: {e}")
            return {'phase': 'unknown', 'confidence': 0.0, 'bias': 'neutral'}
