"""
Price Action Detector - Padrões clássicos de candlestick e price action
Identifica: Engulfing, Pin Bar, Inside Bar, Rejection, Breakout
Autor: Sistema ATLAS - Fase 3
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class PriceActionDetector:
    """
    Detector de padrões de Price Action para identificar setups de alta probabilidade
    """
    
    def __init__(self, lookback_period: int = 30):
        """
        Args:
            lookback_period: Número de candles para análise de contexto
        """
        self.lookback_period = lookback_period
    
    def detect_bullish_engulfing(self, df: pd.DataFrame) -> Dict:
        """
        Engulfing de alta: vela verde engole vela vermelha anterior
        
        Returns:
            {'detected': bool, 'strength': 0.0-1.0, 'location': 'support' | 'mid' | None}
        """
        if len(df) < 3:
            return {'detected': False, 'strength': 0.0, 'location': None}
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Prev: vela vermelha, Curr: vela verde
        prev_bearish = prev['close'] < prev['open']
        curr_bullish = curr['close'] > curr['open']
        
        if not (prev_bearish and curr_bullish):
            return {'detected': False, 'strength': 0.0, 'location': None}
        
        # Engulfing: curr open < prev close E curr close > prev open
        engulfs = curr['open'] < prev['close'] and curr['close'] > prev['open']
        
        if not engulfs:
            return {'detected': False, 'strength': 0.0, 'location': None}
        
        # Força: tamanho relativo da vela atual
        prev_body = abs(prev['close'] - prev['open'])
        curr_body = curr['close'] - curr['open']
        strength = min(1.0, curr_body / (prev_body + 0.0001))
        
        # Localização: próximo de suporte?
        location = self._get_support_resistance_location(df, curr['close'])
        
        return {'detected': True, 'strength': strength, 'location': location}
    
    def detect_bearish_engulfing(self, df: pd.DataFrame) -> Dict:
        """
        Engulfing de baixa: vela vermelha engole vela verde anterior
        """
        if len(df) < 3:
            return {'detected': False, 'strength': 0.0, 'location': None}
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Prev: vela verde, Curr: vela vermelha
        prev_bullish = prev['close'] > prev['open']
        curr_bearish = curr['close'] < curr['open']
        
        if not (prev_bullish and curr_bearish):
            return {'detected': False, 'strength': 0.0, 'location': None}
        
        # Engulfing: curr open > prev close E curr close < prev open
        engulfs = curr['open'] > prev['close'] and curr['close'] < prev['open']
        
        if not engulfs:
            return {'detected': False, 'strength': 0.0, 'location': None}
        
        # Força
        prev_body = abs(prev['close'] - prev['open'])
        curr_body = abs(curr['close'] - curr['open'])
        strength = min(1.0, curr_body / (prev_body + 0.0001))
        
        # Localização: próximo de resistência?
        location = self._get_support_resistance_location(df, curr['close'])
        
        return {'detected': True, 'strength': strength, 'location': location}
    
    def detect_pin_bar_bullish(self, df: pd.DataFrame) -> Dict:
        """
        Pin bar de alta: pavio inferior longo, corpo pequeno no topo
        
        Returns:
            {'detected': bool, 'strength': 0.0-1.0}
        """
        if len(df) < 2:
            return {'detected': False, 'strength': 0.0}
        
        candle = df.iloc[-1]
        
        candle_range = candle['high'] - candle['low']
        if candle_range == 0:
            return {'detected': False, 'strength': 0.0}
        
        body = abs(candle['close'] - candle['open'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        
        # Pin bar: pavio inferior > 60% do range, corpo pequeno
        is_pin_bar = (
            lower_wick > candle_range * 0.6 and
            body < candle_range * 0.3 and
            upper_wick < candle_range * 0.2
        )
        
        if not is_pin_bar:
            return {'detected': False, 'strength': 0.0}
        
        # Força: quanto maior o pavio, mais forte
        strength = min(1.0, lower_wick / candle_range)
        
        return {'detected': True, 'strength': strength}
    
    def detect_pin_bar_bearish(self, df: pd.DataFrame) -> Dict:
        """
        Pin bar de baixa: pavio superior longo, corpo pequeno embaixo
        """
        if len(df) < 2:
            return {'detected': False, 'strength': 0.0}
        
        candle = df.iloc[-1]
        
        candle_range = candle['high'] - candle['low']
        if candle_range == 0:
            return {'detected': False, 'strength': 0.0}
        
        body = abs(candle['close'] - candle['open'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        
        # Pin bar: pavio superior > 60% do range, corpo pequeno
        is_pin_bar = (
            upper_wick > candle_range * 0.6 and
            body < candle_range * 0.3 and
            lower_wick < candle_range * 0.2
        )
        
        if not is_pin_bar:
            return {'detected': False, 'strength': 0.0}
        
        strength = min(1.0, upper_wick / candle_range)
        
        return {'detected': True, 'strength': strength}
    
    def detect_rejection_at_level(self, df: pd.DataFrame, level_type: str = 'support') -> Dict:
        """
        Rejeição em nível de suporte/resistência
        
        Args:
            level_type: 'support' ou 'resistance'
        
        Returns:
            {'detected': bool, 'strength': 0.0-1.0, 'bounces': int}
        """
        if len(df) < 20:
            return {'detected': False, 'strength': 0.0, 'bounces': 0}
        
        recent = df.tail(20)
        current_price = recent['close'].iloc[-1]
        
        # Identificar níveis de suporte/resistência
        if level_type == 'support':
            # Suporte = mínimas anteriores
            potential_levels = recent['low'].nsmallest(5).values
        else:
            # Resistência = máximas anteriores
            potential_levels = recent['high'].nlargest(5).values
        
        # Verificar se preço atual está próximo de algum nível
        tolerance = (recent['high'].max() - recent['low'].min()) * 0.02  # 2% do range
        
        bounces = 0
        closest_level = None
        
        for level in potential_levels:
            if abs(current_price - level) <= tolerance:
                closest_level = level
                # Contar quantas vezes respeitou este nível
                for i in range(len(recent) - 5):
                    if abs(recent['low'].iloc[i] - level) <= tolerance:
                        bounces += 1
                break
        
        if closest_level is None:
            return {'detected': False, 'strength': 0.0, 'bounces': 0}
        
        # Força baseada em número de toques
        strength = min(1.0, bounces / 3.0)
        
        return {'detected': True, 'strength': strength, 'bounces': bounces}
    
    def _get_support_resistance_location(self, df: pd.DataFrame, price: float) -> str:
        """
        Determina se preço está próximo de suporte, resistência ou meio
        """
        if len(df) < 20:
            return 'mid'
        
        recent = df.tail(20)
        high_level = recent['high'].max()
        low_level = recent['low'].min()
        range_size = high_level - low_level
        
        # Dividir range em 3 partes
        lower_third = low_level + range_size * 0.33
        upper_third = low_level + range_size * 0.67
        
        if price <= lower_third:
            return 'support'
        elif price >= upper_third:
            return 'resistance'
        else:
            return 'mid'
    
    def get_price_action_score(self, df: pd.DataFrame, direction: str) -> float:
        """
        Calcula score de Price Action para direção
        
        Args:
            df: DataFrame OHLCV
            direction: 'BUY' ou 'SELL'
        
        Returns:
            Score 0.0-1.0
        """
        score = 0.0
        
        if direction == 'BUY':
            # Padrões de alta
            bull_engulf = self.detect_bullish_engulfing(df)
            pin_bar_bull = self.detect_pin_bar_bullish(df)
            support_rej = self.detect_rejection_at_level(df, 'support')
            
            if bull_engulf['detected']:
                score += 0.4 * bull_engulf['strength']
                if bull_engulf['location'] == 'support':
                    score += 0.2  # Bônus se em suporte
            
            if pin_bar_bull['detected']:
                score += 0.3 * pin_bar_bull['strength']
            
            if support_rej['detected']:
                score += 0.3 * support_rej['strength']
        
        elif direction == 'SELL':
            # Padrões de baixa
            bear_engulf = self.detect_bearish_engulfing(df)
            pin_bar_bear = self.detect_pin_bar_bearish(df)
            resistance_rej = self.detect_rejection_at_level(df, 'resistance')
            
            if bear_engulf['detected']:
                score += 0.4 * bear_engulf['strength']
                if bear_engulf['location'] == 'resistance':
                    score += 0.2  # Bônus se em resistência
            
            if pin_bar_bear['detected']:
                score += 0.3 * pin_bar_bear['strength']
            
            if resistance_rej['detected']:
                score += 0.3 * resistance_rej['strength']
        
        return min(1.0, score)
    
    def get_analysis(self, df: pd.DataFrame) -> Dict:
        """
        Análise completa de Price Action
        
        Returns:
            Dicionário com todos os padrões detectados
        """
        return {
            'bullish_engulfing': self.detect_bullish_engulfing(df),
            'bearish_engulfing': self.detect_bearish_engulfing(df),
            'pin_bar_bullish': self.detect_pin_bar_bullish(df),
            'pin_bar_bearish': self.detect_pin_bar_bearish(df),
            'support_rejection': self.detect_rejection_at_level(df, 'support'),
            'resistance_rejection': self.detect_rejection_at_level(df, 'resistance'),
            'score_buy': self.get_price_action_score(df, 'BUY'),
            'score_sell': self.get_price_action_score(df, 'SELL')
        }


if __name__ == '__main__':
    # Teste com dados sintéticos
    print("═" * 60)
    print("PRICE ACTION DETECTOR TEST")
    print("═" * 60)
    
    # Simular bullish engulfing
    np.random.seed(42)
    dates = pd.date_range(start='2026-01-01', periods=50, freq='5m')
    
    close = 100 + np.random.randn(50).cumsum() * 0.5
    high = close + np.abs(np.random.randn(50) * 0.3)
    low = close - np.abs(np.random.randn(50) * 0.3)
    open_price = close + np.random.randn(50) * 0.2
    volume = np.random.randn(50) * 100 + 1000
    
    # Forçar bullish engulfing nas 2 últimas velas
    open_price[-2] = 100.5
    close[-2] = 100.0  # Vela vermelha
    open_price[-1] = 99.8
    close[-1] = 101.0  # Vela verde que engole
    high[-1] = 101.2
    low[-1] = 99.7
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    detector = PriceActionDetector(lookback_period=30)
    analysis = detector.get_analysis(df)
    
    print(f"Bullish Engulfing: {analysis['bullish_engulfing']}")
    print(f"Bearish Engulfing: {analysis['bearish_engulfing']}")
    print(f"Pin Bar Bull: {analysis['pin_bar_bullish']}")
    print(f"Pin Bar Bear: {analysis['pin_bar_bearish']}")
    print(f"Support Rejection: {analysis['support_rejection']}")
    print(f"Resistance Rejection: {analysis['resistance_rejection']}")
    print(f"\nScore BUY: {analysis['score_buy']:.2f}")
    print(f"Score SELL: {analysis['score_sell']:.2f}")
    print("═" * 60)
