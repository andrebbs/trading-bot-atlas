"""
Smart Money Concepts (SMC) Detector
------------------------------------
Detecta estrutura de mercado baseada em conceitos institucionais:
- Order Blocks (OB) — zonas onde smart money entrou
- Break of Structure (BOS) — continuação de tendência
- Change of Character (CHoCH) — reversão de tendência
- Fair Value Gaps (FVG) — ineficiências de preço
- Liquidity Zones — áreas de acumulação de stops

Referências:
- The Inner Circle Trader (ICT)
- Smart Money Concepts by LuxAlgo
"""

import pandas as pd
import numpy as np
from typing import Tuple, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class SMCDetector:
    """
    Detector de Smart Money Concepts para identificar estrutura de mercado.
    """
    
    def __init__(self, lookback_period: int = 50):
        """
        Args:
            lookback_period: Número de candles para análise de estrutura
        """
        self.lookback_period = lookback_period
    
    def detect_swing_points(self, df: pd.DataFrame, window: int = 5) -> Tuple[List[int], List[int]]:
        """
        Detecta swing highs e swing lows.
        
        Swing High: pico local (high maior que N candles antes e depois)
        Swing Low: vale local (low menor que N candles antes e depois)
        
        Args:
            df: DataFrame com OHLCV
            window: Janela para confirmação de swing (default: 5)
        
        Returns:
            (swing_highs_indices, swing_lows_indices)
        """
        swing_highs = []
        swing_lows = []
        
        for i in range(window, len(df) - window):
            # Swing High
            high_window = df['high'].iloc[i-window:i+window+1]
            if df['high'].iloc[i] == high_window.max():
                swing_highs.append(i)
            
            # Swing Low
            low_window = df['low'].iloc[i-window:i+window+1]
            if df['low'].iloc[i] == low_window.min():
                swing_lows.append(i)
        
        return swing_highs, swing_lows
    
    def detect_bos(self, df: pd.DataFrame) -> Dict[str, any]:
        """
        Break of Structure (BOS) — quebra de estrutura anterior.
        
        BOS Bullish: preço quebra último swing high
        BOS Bearish: preço quebra último swing low
        
        Indica continuação de tendência.
        
        Returns:
            {
                'type': 'bullish' | 'bearish' | None,
                'level': float,  # nível quebrado
                'strength': float  # 0-1 (força do rompimento)
            }
        """
        swing_highs, swing_lows = self.detect_swing_points(df)
        
        if len(df) < 10:
            return {'type': None, 'level': None, 'strength': 0.0}
        
        current_close = df['close'].iloc[-1]
        current_high = df['high'].iloc[-1]
        current_low = df['low'].iloc[-1]
        
        # BOS Bullish: quebrou último swing high
        if swing_highs:
            last_swing_high_idx = swing_highs[-1]
            last_swing_high = df['high'].iloc[last_swing_high_idx]
            
            if current_high > last_swing_high:
                strength = min((current_high - last_swing_high) / last_swing_high * 100, 1.0)
                return {
                    'type': 'bullish',
                    'level': last_swing_high,
                    'strength': strength
                }
        
        # BOS Bearish: quebrou último swing low
        if swing_lows:
            last_swing_low_idx = swing_lows[-1]
            last_swing_low = df['low'].iloc[last_swing_low_idx]
            
            if current_low < last_swing_low:
                strength = min((last_swing_low - current_low) / last_swing_low * 100, 1.0)
                return {
                    'type': 'bearish',
                    'level': last_swing_low,
                    'strength': strength
                }
        
        return {'type': None, 'level': None, 'strength': 0.0}
    
    def detect_choch(self, df: pd.DataFrame) -> Dict[str, any]:
        """
        Change of Character (CHoCH) — mudança de caráter do mercado.
        
        CHoCH Bullish: após downtrend, preço quebra swing high anterior
        CHoCH Bearish: após uptrend, preço quebra swing low anterior
        
        Indica reversão de tendência.
        
        Returns:
            {
                'type': 'bullish' | 'bearish' | None,
                'level': float,
                'strength': float
            }
        """
        swing_highs, swing_lows = self.detect_swing_points(df, window=3)
        
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return {'type': None, 'level': None, 'strength': 0.0}
        
        # Identificar tendência recente
        recent_highs = [df['high'].iloc[i] for i in swing_highs[-3:]]
        recent_lows = [df['low'].iloc[i] for i in swing_lows[-3:]]
        
        # Downtrend → CHoCH bullish
        if len(recent_lows) >= 2 and recent_lows[-1] < recent_lows[-2]:
            # Estava em downtrend, agora quebrou swing high
            if len(recent_highs) >= 1:
                last_swing_high = recent_highs[-1]
                current_high = df['high'].iloc[-1]
                
                if current_high > last_swing_high:
                    strength = min((current_high - last_swing_high) / last_swing_high * 100, 1.0)
                    return {
                        'type': 'bullish',
                        'level': last_swing_high,
                        'strength': strength
                    }
        
        # Uptrend → CHoCH bearish
        if len(recent_highs) >= 2 and recent_highs[-1] > recent_highs[-2]:
            # Estava em uptrend, agora quebrou swing low
            if len(recent_lows) >= 1:
                last_swing_low = recent_lows[-1]
                current_low = df['low'].iloc[-1]
                
                if current_low < last_swing_low:
                    strength = min((last_swing_low - current_low) / last_swing_low * 100, 1.0)
                    return {
                        'type': 'bearish',
                        'level': last_swing_low,
                        'strength': strength
                    }
        
        return {'type': None, 'level': None, 'strength': 0.0}
    
    def detect_order_blocks(self, df: pd.DataFrame) -> Dict[str, List]:
        """
        Order Blocks (OB) — zonas onde smart money entrou.
        
        Bullish OB: última vela antes de movimento forte de alta
        Bearish OB: última vela antes de movimento forte de baixa
        
        Returns:
            {
                'bullish_ob': [(index, low, high), ...],
                'bearish_ob': [(index, low, high), ...]
            }
        """
        bullish_obs = []
        bearish_obs = []
        
        for i in range(5, len(df) - 1):
            # Movimento forte de alta (3+ candles verdes consecutivos)
            if all(df['close'].iloc[i+j] > df['open'].iloc[i+j] for j in range(1, min(4, len(df)-i))):
                # Order Block = última vela antes do movimento
                ob_low = df['low'].iloc[i]
                ob_high = df['high'].iloc[i]
                bullish_obs.append((i, ob_low, ob_high))
            
            # Movimento forte de baixa (3+ candles vermelhos consecutivos)
            if all(df['close'].iloc[i+j] < df['open'].iloc[i+j] for j in range(1, min(4, len(df)-i))):
                ob_low = df['low'].iloc[i]
                ob_high = df['high'].iloc[i]
                bearish_obs.append((i, ob_low, ob_high))
        
        return {
            'bullish_ob': bullish_obs[-5:],  # últimos 5
            'bearish_ob': bearish_obs[-5:]
        }
    
    def detect_fair_value_gaps(self, df: pd.DataFrame) -> Dict[str, List]:
        """
        Fair Value Gaps (FVG) — gaps de 3 candles (ineficiências).
        
        Bullish FVG: gap entre candle[i-2].high e candle[i].low
        Bearish FVG: gap entre candle[i-2].low e candle[i].high
        
        Returns:
            {
                'bullish_fvg': [(index, gap_low, gap_high), ...],
                'bearish_fvg': [(index, gap_low, gap_high), ...]
            }
        """
        bullish_fvgs = []
        bearish_fvgs = []
        
        for i in range(2, len(df)):
            # Bullish FVG
            gap_low = df['high'].iloc[i-2]
            gap_high = df['low'].iloc[i]
            
            if gap_high > gap_low:  # existe gap
                bullish_fvgs.append((i, gap_low, gap_high))
            
            # Bearish FVG
            gap_high = df['low'].iloc[i-2]
            gap_low = df['high'].iloc[i]
            
            if gap_low < gap_high:  # existe gap
                bearish_fvgs.append((i, gap_low, gap_high))
        
        return {
            'bullish_fvg': bullish_fvgs[-5:],
            'bearish_fvg': bearish_fvgs[-5:]
        }
    
    def get_market_structure(self, df: pd.DataFrame) -> str:
        """
        Determina estrutura atual do mercado.
        
        Returns:
            'bullish' — BOS bullish ativo ou tendência de alta
            'bearish' — BOS bearish ativo ou tendência de baixa
            'ranging' — sem estrutura clara (lateralização)
            'transition' — CHoCH detectado (mudança de tendência)
        """
        bos = self.detect_bos(df)
        choch = self.detect_choch(df)
        
        # Prioridade: CHoCH > BOS > Análise de swing points
        if choch['type'] is not None:
            return 'transition'
        
        if bos['type'] == 'bullish' and bos['strength'] > 0.3:
            return 'bullish'
        
        if bos['type'] == 'bearish' and bos['strength'] > 0.3:
            return 'bearish'
        
        # Análise de swing points (tendência)
        swing_highs, swing_lows = self.detect_swing_points(df, window=5)
        
        if len(swing_highs) >= 3 and len(swing_lows) >= 3:
            recent_highs = [df['high'].iloc[i] for i in swing_highs[-3:]]
            recent_lows = [df['low'].iloc[i] for i in swing_lows[-3:]]
            
            # Higher highs + higher lows = uptrend
            if all(recent_highs[i] > recent_highs[i-1] for i in range(1, len(recent_highs))):
                if all(recent_lows[i] > recent_lows[i-1] for i in range(1, len(recent_lows))):
                    return 'bullish'
            
            # Lower highs + lower lows = downtrend
            if all(recent_highs[i] < recent_highs[i-1] for i in range(1, len(recent_highs))):
                if all(recent_lows[i] < recent_lows[i-1] for i in range(1, len(recent_lows))):
                    return 'bearish'
        
        return 'ranging'
    
    def get_smc_score(self, df: pd.DataFrame, direction: str) -> float:
        """
        Calcula score SMC (0-1) baseado em alinhamento estrutural.
        
        Args:
            df: DataFrame OHLCV
            direction: 'BUY' ou 'SELL'
        
        Returns:
            Score 0.0-1.0
        """
        structure = self.get_market_structure(df)
        bos = self.detect_bos(df)
        choch = self.detect_choch(df)
        order_blocks = self.detect_order_blocks(df)
        fvgs = self.detect_fair_value_gaps(df)
        
        score = 0.0
        
        if direction == 'BUY':
            # Estrutura bullish
            if structure == 'bullish':
                score += 0.4
            elif structure == 'transition' and choch['type'] == 'bullish':
                score += 0.5  # reversão bullish
            
            # BOS bullish
            if bos['type'] == 'bullish':
                score += 0.3 * bos['strength']
            
            # Order Blocks bullish próximos
            if order_blocks['bullish_ob']:
                score += 0.2
            
            # FVG bullish não preenchido
            if fvgs['bullish_fvg']:
                score += 0.1
        
        elif direction == 'SELL':
            # Estrutura bearish
            if structure == 'bearish':
                score += 0.4
            elif structure == 'transition' and choch['type'] == 'bearish':
                score += 0.5  # reversão bearish
            
            # BOS bearish
            if bos['type'] == 'bearish':
                score += 0.3 * bos['strength']
            
            # Order Blocks bearish próximos
            if order_blocks['bearish_ob']:
                score += 0.2
            
            # FVG bearish não preenchido
            if fvgs['bearish_fvg']:
                score += 0.1
        
        return min(score, 1.0)
    
    def get_analysis(self, df: pd.DataFrame) -> Dict[str, any]:
        """
        Retorna análise SMC completa.
        
        Returns:
            {
                'structure': str,
                'bos': dict,
                'choch': dict,
                'order_blocks': dict,
                'fvgs': dict,
                'score_buy': float,
                'score_sell': float
            }
        """
        return {
            'structure': self.get_market_structure(df),
            'bos': self.detect_bos(df),
            'choch': self.detect_choch(df),
            'order_blocks': self.detect_order_blocks(df),
            'fvgs': self.detect_fair_value_gaps(df),
            'score_buy': self.get_smc_score(df, 'BUY'),
            'score_sell': self.get_smc_score(df, 'SELL')
        }


# ─────────────────────────────────────────────────────────────────────────────
# Testes
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # Teste básico com dados sintéticos
    import pandas as pd
    
    # Criar uptrend sintético
    dates = pd.date_range('2024-01-01', periods=100, freq='5min')
    df = pd.DataFrame({
        'timestamp': dates,
        'open': np.linspace(100, 150, 100) + np.random.randn(100) * 2,
        'high': np.linspace(102, 152, 100) + np.random.randn(100) * 2,
        'low': np.linspace(98, 148, 100) + np.random.randn(100) * 2,
        'close': np.linspace(101, 151, 100) + np.random.randn(100) * 2,
        'volume': np.random.randint(1000, 5000, 100)
    })
    
    detector = SMCDetector()
    analysis = detector.get_analysis(df)
    
    print('═' * 60)
    print('SMC ANALYSIS')
    print('═' * 60)
    print(f"Structure: {analysis['structure']}")
    print(f"BOS: {analysis['bos']['type']} (strength: {analysis['bos']['strength']:.2f})")
    print(f"CHoCH: {analysis['choch']['type']}")
    print(f"Bullish OBs: {len(analysis['order_blocks']['bullish_ob'])}")
    print(f"Bearish OBs: {len(analysis['order_blocks']['bearish_ob'])}")
    print(f"Score BUY: {analysis['score_buy']:.2f}")
    print(f"Score SELL: {analysis['score_sell']:.2f}")
    print('═' * 60)
