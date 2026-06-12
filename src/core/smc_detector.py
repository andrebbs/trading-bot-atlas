"""
SMC Detector v2 - Smart Money Concepts INSTITUCIONAL
ATLAS v2 — Advanced Technical Liquidity Analysis System

Melhorias v2:
  - Liquidity Sweep real (equal highs/lows capturados)
  - BOS / CHoCH como condição de gatilho (não apenas informativo)
  - Order Blocks com confirmação de volume
  - FVG (Fair Value Gap) com verificação de mitigação
  - Premium / Discount zones (50% do range)
  - Score só sobe com confluência estrutural real
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class SMCDetector:
    """
    Smart Money Concepts — nível institucional.

    Fluxo correto de entrada SMC:
        1. Identifica zona de liquidez (equal highs/lows)
        2. Confirma sweep (price varre a liquidez)
        3. Confirma CHoCH ou BOS após sweep
        4. Entrada no retorno ao OB ou FVG
        5. Alvo: próxima zona de liquidez oposta
    """

    def __init__(self, lookback_period: int = 50):
        self.lookback = lookback_period

    # ──────────────────────────────────────────────────────────────────
    # SWING POINTS
    # ──────────────────────────────────────────────────────────────────
    def detect_swing_points(self, df: pd.DataFrame, window: int = 5) -> Tuple[List[int], List[int]]:
        """Detecta swing highs e swing lows."""
        highs, lows = [], []
        data = df.tail(self.lookback).reset_index(drop=True)
        for i in range(window, len(data) - window):
            if data['high'].iloc[i] == data['high'].iloc[i-window:i+window+1].max():
                highs.append(i)
            if data['low'].iloc[i] == data['low'].iloc[i-window:i+window+1].min():
                lows.append(i)
        return highs, lows

    # ──────────────────────────────────────────────────────────────────
    # LIQUIDITY ZONES (equal highs / equal lows)
    # ──────────────────────────────────────────────────────────────────
    def detect_liquidity_zones(self, df: pd.DataFrame, tolerance: float = 0.002) -> Dict:
        """
        Detecta zonas de liquidez:
        - Equal Highs: topos quase iguais = stop de vendedores acumulado
        - Equal Lows : fundos quase iguais = stop de compradores acumulado
        """
        data = df.tail(self.lookback).reset_index(drop=True)
        swing_highs_idx, swing_lows_idx = self.detect_swing_points(df)

        equal_highs = []
        equal_lows  = []

        # Equal Highs
        sh_prices = [data['high'].iloc[i] for i in swing_highs_idx if i < len(data)]
        for i in range(len(sh_prices)):
            for j in range(i+1, len(sh_prices)):
                diff = abs(sh_prices[i] - sh_prices[j]) / sh_prices[i] if sh_prices[i] > 0 else 1
                if diff <= tolerance:
                    level = (sh_prices[i] + sh_prices[j]) / 2
                    if level not in equal_highs:
                        equal_highs.append(level)

        # Equal Lows
        sl_prices = [data['low'].iloc[i] for i in swing_lows_idx if i < len(data)]
        for i in range(len(sl_prices)):
            for j in range(i+1, len(sl_prices)):
                diff = abs(sl_prices[i] - sl_prices[j]) / sl_prices[i] if sl_prices[i] > 0 else 1
                if diff <= tolerance:
                    level = (sl_prices[i] + sl_prices[j]) / 2
                    if level not in equal_lows:
                        equal_lows.append(level)

        return {'equal_highs': equal_highs, 'equal_lows': equal_lows}

    # ──────────────────────────────────────────────────────────────────
    # LIQUIDITY SWEEP
    # ──────────────────────────────────────────────────────────────────
    def detect_liquidity_sweep(self, df: pd.DataFrame) -> Dict:
        """
        Detecta se o preço acabou de varrer uma zona de liquidez.
        Sweep = price ultrapassou equal high/low e voltou.
        """
        if len(df) < 10:
            return {'swept_high': False, 'swept_low': False, 'sweep_level': None}

        liq = self.detect_liquidity_zones(df)
        last   = df.iloc[-1]
        prev   = df.iloc[-2]
        close  = float(last['close'])
        high   = float(last['high'])
        low    = float(last['low'])
        p_high = float(prev['high'])
        p_low  = float(prev['low'])

        swept_high = False
        swept_low  = False
        sweep_level = None

        # Sweep de High: wick acima do equal high mas fecha abaixo
        for level in liq['equal_highs']:
            if high > level and close < level:
                swept_high  = True
                sweep_level = level
                break

        # Sweep de Low: wick abaixo do equal low mas fecha acima
        for level in liq['equal_lows']:
            if low < level and close > level:
                swept_low   = True
                sweep_level = level
                break

        return {
            'swept_high': swept_high,
            'swept_low':  swept_low,
            'sweep_level': sweep_level,
            'equal_highs': liq['equal_highs'],
            'equal_lows':  liq['equal_lows'],
        }

    # ──────────────────────────────────────────────────────────────────
    # BOS — Break of Structure
    # ──────────────────────────────────────────────────────────────────
    def detect_bos(self, df: pd.DataFrame) -> Dict:
        """
        BOS = rompimento de topo/fundo estrutural na MESMA direção da tendência.
        Confirma continuação.
        """
        try:
            data = df.tail(self.lookback).reset_index(drop=True)
            swing_highs, swing_lows = self.detect_swing_points(df)

            if not swing_highs or not swing_lows:
                return {'bullish_bos': False, 'bearish_bos': False, 'bos_level': None}

            last_close = float(data['close'].iloc[-1])

            # Último swing high válido
            last_sh = data['high'].iloc[swing_highs[-1]] if swing_highs else None
            # Último swing low válido
            last_sl = data['low'].iloc[swing_lows[-1]] if swing_lows else None

            bullish_bos = bool(last_sh is not None and last_close > float(last_sh))
            bearish_bos = bool(last_sl is not None and last_close < float(last_sl))

            bos_level = float(last_sh) if bullish_bos else (float(last_sl) if bearish_bos else None)

            return {
                'bullish_bos': bullish_bos,
                'bearish_bos': bearish_bos,
                'bos_level':   bos_level,
                'last_swing_high': float(last_sh) if last_sh is not None else None,
                'last_swing_low':  float(last_sl) if last_sl is not None else None,
            }
        except Exception as e:
            logger.debug(f"Erro BOS: {e}")
            return {'bullish_bos': False, 'bearish_bos': False, 'bos_level': None}

    # ──────────────────────────────────────────────────────────────────
    # CHoCH — Change of Character
    # ──────────────────────────────────────────────────────────────────
    def detect_choch(self, df: pd.DataFrame) -> Dict:
        """
        CHoCH = rompimento CONTRA a tendência atual.
        Sinal de reversão institucional — mais forte que BOS.
        """
        try:
            data = df.tail(self.lookback).reset_index(drop=True)
            swing_highs, swing_lows = self.detect_swing_points(df)

            if len(swing_highs) < 2 or len(swing_lows) < 2:
                return {'bullish_choch': False, 'bearish_choch': False}

            last_close = float(data['close'].iloc[-1])

            # Topos decrescentes (tendência de baixa) → CHoCH bullish se romper último topo
            sh_prices  = [float(data['high'].iloc[i]) for i in swing_highs[-3:]]
            sl_prices  = [float(data['low'].iloc[i])  for i in swing_lows[-3:]]

            bearish_trend = all(sh_prices[i] > sh_prices[i+1] for i in range(len(sh_prices)-1))
            bullish_trend = all(sl_prices[i] < sl_prices[i+1] for i in range(len(sl_prices)-1))

            bullish_choch = bearish_trend and last_close > sh_prices[-1]
            bearish_choch = bullish_trend and last_close < sl_prices[-1]

            return {
                'bullish_choch': bool(bullish_choch),
                'bearish_choch': bool(bearish_choch),
                'choch_level': sh_prices[-1] if bullish_choch else (sl_prices[-1] if bearish_choch else None),
            }
        except Exception as e:
            logger.debug(f"Erro CHoCH: {e}")
            return {'bullish_choch': False, 'bearish_choch': False}

    # ──────────────────────────────────────────────────────────────────
    # ORDER BLOCKS
    # ──────────────────────────────────────────────────────────────────
    def detect_order_blocks(self, df: pd.DataFrame) -> Dict:
        """
        Order Block = último candle oposto antes de um movimento forte.
        v2: confirmação por volume relativo.
        """
        try:
            data = df.tail(self.lookback).reset_index(drop=True)
            bullish_obs = []
            bearish_obs = []
            avg_vol = data['volume'].mean() if 'volume' in data.columns else 1

            for i in range(2, len(data) - 1):
                candle     = data.iloc[i]
                next_c     = data.iloc[i+1]
                body       = abs(float(candle['close']) - float(candle['open']))
                next_body  = abs(float(next_c['close']) - float(next_c['open']))
                vol        = float(candle.get('volume', avg_vol))
                vol_ok     = vol >= avg_vol * 0.8  # volume razoável

                # Bullish OB: candle de baixa seguido de forte alta
                if (float(candle['close']) < float(candle['open'])
                        and float(next_c['close']) > float(next_c['open'])
                        and next_body > body * 1.5
                        and vol_ok):
                    bullish_obs.append({
                        'high': float(candle['high']),
                        'low':  float(candle['low']),
                        'idx':  i,
                        'mitigated': False,
                    })

                # Bearish OB: candle de alta seguido de forte baixa
                if (float(candle['close']) > float(candle['open'])
                        and float(next_c['close']) < float(next_c['open'])
                        and next_body > body * 1.5
                        and vol_ok):
                    bearish_obs.append({
                        'high': float(candle['high']),
                        'low':  float(candle['low']),
                        'idx':  i,
                        'mitigated': False,
                    })

            # Marcar OBs já mitigados (preço voltou a eles)
            last_close = float(data['close'].iloc[-1])
            for ob in bullish_obs:
                if last_close < ob['low']:
                    ob['mitigated'] = True
            for ob in bearish_obs:
                if last_close > ob['high']:
                    ob['mitigated'] = True

            active_bull = [ob for ob in bullish_obs if not ob['mitigated']]
            active_bear = [ob for ob in bearish_obs if not ob['mitigated']]

            return {
                'bullish': active_bull,
                'bearish': active_bear,
                'bullish_count': len(active_bull),
                'bearish_count': len(active_bear),
            }
        except Exception as e:
            logger.debug(f"Erro OB: {e}")
            return {'bullish': [], 'bearish': [], 'bullish_count': 0, 'bearish_count': 0}

    # ──────────────────────────────────────────────────────────────────
    # FAIR VALUE GAPS
    # ──────────────────────────────────────────────────────────────────
    def detect_fair_value_gaps(self, df: pd.DataFrame) -> Dict:
        """
        FVG = gap de 3 candles (candle anterior high < candle posterior low).
        v2: marca FVGs já mitigados.
        """
        try:
            data = df.tail(self.lookback).reset_index(drop=True)
            bullish_fvgs = []
            bearish_fvgs = []
            last_close   = float(data['close'].iloc[-1])

            for i in range(1, len(data) - 1):
                prev = data.iloc[i-1]
                curr = data.iloc[i]
                nxt  = data.iloc[i+1]

                # Bullish FVG: gap entre high[i-1] e low[i+1]
                if float(prev['high']) < float(nxt['low']):
                    gap = {
                        'top':       float(nxt['low']),
                        'bottom':    float(prev['high']),
                        'mid':       (float(nxt['low']) + float(prev['high'])) / 2,
                        'idx':       i,
                        'mitigated': last_close < float(prev['high']),
                    }
                    bullish_fvgs.append(gap)

                # Bearish FVG: gap entre low[i-1] e high[i+1]
                if float(prev['low']) > float(nxt['high']):
                    gap = {
                        'top':       float(prev['low']),
                        'bottom':    float(nxt['high']),
                        'mid':       (float(prev['low']) + float(nxt['high'])) / 2,
                        'idx':       i,
                        'mitigated': last_close > float(prev['low']),
                    }
                    bearish_fvgs.append(gap)

            active_bull = [g for g in bullish_fvgs if not g['mitigated']]
            active_bear = [g for g in bearish_fvgs if not g['mitigated']]

            return {
                'bullish': active_bull,
                'bearish': active_bear,
                'bullish_count': len(active_bull),
                'bearish_count': len(active_bear),
            }
        except Exception as e:
            logger.debug(f"Erro FVG: {e}")
            return {'bullish': [], 'bearish': [], 'bullish_count': 0, 'bearish_count': 0}

    # ──────────────────────────────────────────────────────────────────
    # PREMIUM / DISCOUNT ZONES
    # ──────────────────────────────────────────────────────────────────
    def get_premium_discount(self, df: pd.DataFrame) -> Dict:
        """
        Premium = acima de 50% do range → vender
        Discount = abaixo de 50% do range → comprar
        """
        try:
            data  = df.tail(self.lookback)
            high  = float(data['high'].max())
            low   = float(data['low'].min())
            close = float(df.iloc[-1]['close'])
            mid   = (high + low) / 2
            ratio = (close - low) / (high - low) if (high - low) > 0 else 0.5

            if ratio > 0.618:
                zone = 'premium'
            elif ratio < 0.382:
                zone = 'discount'
            else:
                zone = 'equilibrium'

            return {
                'zone':    zone,
                'ratio':   ratio,
                'range_high': high,
                'range_low':  low,
                'midpoint':   mid,
            }
        except Exception as e:
            logger.debug(f"Erro Premium/Discount: {e}")
            return {'zone': 'equilibrium', 'ratio': 0.5}

    # ──────────────────────────────────────────────────────────────────
    # ESTRUTURA DE MERCADO
    # ──────────────────────────────────────────────────────────────────
    def get_market_structure(self, df: pd.DataFrame) -> str:
        """
        Retorna: 'bullish' | 'bearish' | 'ranging'
        Baseado em sequência de HH/HL ou LH/LL.
        """
        try:
            swing_highs, swing_lows = self.detect_swing_points(df)
            data = df.tail(self.lookback).reset_index(drop=True)

            if len(swing_highs) < 2 or len(swing_lows) < 2:
                return 'ranging'

            sh = [float(data['high'].iloc[i]) for i in swing_highs[-3:] if i < len(data)]
            sl = [float(data['low'].iloc[i])  for i in swing_lows[-3:]  if i < len(data)]

            if len(sh) < 2 or len(sl) < 2:
                return 'ranging'

            hh = sh[-1] > sh[-2]
            hl = sl[-1] > sl[-2]
            lh = sh[-1] < sh[-2]
            ll = sl[-1] < sl[-2]

            if hh and hl:   return 'bullish'
            if lh and ll:   return 'bearish'
            return 'ranging'
        except Exception as e:
            logger.debug(f"Erro estrutura: {e}")
            return 'ranging'

    # ──────────────────────────────────────────────────────────────────
    # SMC SCORE — INSTITUCIONAL v2
    # ──────────────────────────────────────────────────────────────────
    def get_smc_score(self, df: pd.DataFrame, direction: str) -> float:
        """
        Score SMC v2 — exige confluência estrutural real.

        Pontuação:
          +0.30  Estrutura alinhada (bullish/bearish)
          +0.20  Sweep de liquidez confirmado
          +0.20  BOS ou CHoCH na direção correta
          +0.15  OB ativo próximo
          +0.10  FVG ativo próximo
          +0.05  Zona premium/discount correta
          -0.30  Estrutura contrária (penalização forte)
          -0.15  Ranging (sem estrutura)
        """
        try:
            score = 0.0

            structure = self.get_market_structure(df)
            sweep     = self.detect_liquidity_sweep(df)
            bos       = self.detect_bos(df)
            choch     = self.detect_choch(df)
            obs       = self.detect_order_blocks(df)
            fvgs      = self.detect_fair_value_gaps(df)
            pd_zone   = self.get_premium_discount(df)

            last_close = float(df.iloc[-1]['close'])

            if direction == 'BUY':
                # Estrutura
                if structure == 'bullish':    score += 0.30
                elif structure == 'bearish':  score -= 0.30
                elif structure == 'ranging':  score -= 0.15

                # Sweep de low (caçou stops de compradores → institucional entra long)
                if sweep['swept_low']:        score += 0.20

                # BOS ou CHoCH bullish
                if choch['bullish_choch']:    score += 0.20
                elif bos['bullish_bos']:       score += 0.12

                # OB bullish próximo (preço acima do OB)
                for ob in obs['bullish'][-3:]:
                    if ob['low'] <= last_close <= ob['high'] * 1.005:
                        score += 0.15
                        break

                # FVG bullish não mitigado próximo
                for fvg in fvgs['bullish'][-3:]:
                    if fvg['bottom'] <= last_close <= fvg['top'] * 1.005:
                        score += 0.10
                        break

                # Zona discount = boa para compra
                if pd_zone['zone'] == 'discount':  score += 0.05
                elif pd_zone['zone'] == 'premium':  score -= 0.05

            else:  # SELL
                if structure == 'bearish':    score += 0.30
                elif structure == 'bullish':  score -= 0.30
                elif structure == 'ranging':  score -= 0.15

                if sweep['swept_high']:       score += 0.20

                if choch['bearish_choch']:    score += 0.20
                elif bos['bearish_bos']:       score += 0.12

                for ob in obs['bearish'][-3:]:
                    if ob['low'] * 0.995 <= last_close <= ob['high']:
                        score += 0.15
                        break

                for fvg in fvgs['bearish'][-3:]:
                    if fvg['bottom'] * 0.995 <= last_close <= fvg['top']:
                        score += 0.10
                        break

                if pd_zone['zone'] == 'premium':   score += 0.05
                elif pd_zone['zone'] == 'discount': score -= 0.05

            return float(np.clip(score, 0.0, 1.0))

        except Exception as e:
            logger.error(f"Erro SMC score: {e}")
            return 0.5

    # ──────────────────────────────────────────────────────────────────
    # GET ANALYSIS (compatibilidade com ConfluenceScore)
    # ──────────────────────────────────────────────────────────────────
    def get_analysis(self, df: pd.DataFrame) -> Dict:
        """Retorna análise completa SMC para uso externo."""
        try:
            structure = self.get_market_structure(df)
            sweep     = self.detect_liquidity_sweep(df)
            bos       = self.detect_bos(df)
            choch     = self.detect_choch(df)
            obs       = self.detect_order_blocks(df)
            fvgs      = self.detect_fair_value_gaps(df)
            pd_zone   = self.get_premium_discount(df)

            return {
                'structure':         structure,
                'liquidity_sweep':   sweep,
                'bos':               bos,
                'choch':             choch,
                'order_blocks':      obs,
                'fvgs':              fvgs,
                'premium_discount':  pd_zone,
                'has_setup': (
                    (sweep['swept_high'] or sweep['swept_low']) and
                    (bos['bullish_bos'] or bos['bearish_bos'] or
                     choch['bullish_choch'] or choch['bearish_choch'])
                ),
            }
        except Exception as e:
            logger.error(f"Erro SMC analysis: {e}")
            return {'structure': 'ranging', 'has_setup': False}
