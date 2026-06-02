"""
Elliott Wave Detector - Versão simplificada para trading de curto prazo
Identifica: Impulse waves (5 ondas) e Corrective waves (3 ondas) de forma pragmática
Autor: Sistema ATLAS - Fase 4
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ElliottWaveDetector:
    """
    Detector simplificado de ondas Elliott focado em impulso vs correção
    Não tenta identificar ondas exatas, mas detecta PADRÃO de movimento
    """
    
    def __init__(self, lookback_period: int = 100):
        """
        Args:
            lookback_period: Número de candles para análise de ondas
        """
        self.lookback_period = lookback_period
    
    def _find_swing_points(self, df: pd.DataFrame, window: int = 5) -> Tuple[List, List]:
        """
        Encontra swing highs e swing lows
        
        Returns:
            (swing_highs, swing_lows) - listas de índices
        """
        highs = []
        lows = []
        
        for i in range(window, len(df) - window):
            # Swing high: maior que vizinhos
            if df['high'].iloc[i] == df['high'].iloc[i-window:i+window+1].max():
                highs.append(i)
            
            # Swing low: menor que vizinhos
            if df['low'].iloc[i] == df['low'].iloc[i-window:i+window+1].min():
                lows.append(i)
        
        return highs, lows
    
    def detect_impulse_wave(self, df: pd.DataFrame) -> Dict:
        """
        Detecta onda de impulso (5 ondas na mesma direção geral)
        
        Returns:
            {
                'detected': bool,
                'direction': 'bullish' | 'bearish' | None,
                'wave_count': int,
                'strength': 0.0-1.0
            }
        """
        if len(df) < 50:
            return {'detected': False, 'direction': None, 'wave_count': 0, 'strength': 0.0}
        
        recent = df.tail(self.lookback_period).copy().reset_index(drop=True)
        
        # Encontrar swings
        swing_highs, swing_lows = self._find_swing_points(recent, window=3)
        
        # Analisar se há padrão impulsivo
        # Impulso de alta: 3+ swing highs crescentes
        # Impulso de baixa: 3+ swing lows decrescentes
        
        # Checar impulso de alta
        if len(swing_highs) >= 3:
            last_3_highs = swing_highs[-3:]
            high_values = [recent['high'].iloc[i] for i in last_3_highs]
            
            # Highs crescentes = impulso de alta
            if high_values[0] < high_values[1] < high_values[2]:
                # Força: velocidade da subida
                price_change = (high_values[-1] - high_values[0]) / high_values[0]
                strength = min(1.0, abs(price_change) * 10)
                
                return {
                    'detected': True,
                    'direction': 'bullish',
                    'wave_count': len(swing_highs),
                    'strength': strength
                }
        
        # Checar impulso de baixa
        if len(swing_lows) >= 3:
            last_3_lows = swing_lows[-3:]
            low_values = [recent['low'].iloc[i] for i in last_3_lows]
            
            # Lows decrescentes = impulso de baixa
            if low_values[0] > low_values[1] > low_values[2]:
                price_change = (low_values[-1] - low_values[0]) / low_values[0]
                strength = min(1.0, abs(price_change) * 10)
                
                return {
                    'detected': True,
                    'direction': 'bearish',
                    'wave_count': len(swing_lows),
                    'strength': strength
                }
        
        return {'detected': False, 'direction': None, 'wave_count': 0, 'strength': 0.0}
    
    def detect_corrective_wave(self, df: pd.DataFrame) -> Dict:
        """
        Detecta onda corretiva (ABC - movimento contra tendência anterior)
        
        Returns:
            {
                'detected': bool,
                'correction_depth': float (0.0-1.0),
                'direction': 'up' | 'down' | None,
                'likely_finished': bool
            }
        """
        if len(df) < 30:
            return {'detected': False, 'correction_depth': 0.0, 'direction': None, 'likely_finished': False}
        
        recent = df.tail(50).copy().reset_index(drop=True)
        
        # Identificar tendência anterior
        first_third = recent.iloc[:16]
        last_third = recent.iloc[-16:]
        
        trend_start = first_third['close'].mean()
        trend_end = last_third['close'].mean()
        
        # Se lateral, sem correção clara
        if abs(trend_end - trend_start) / trend_start < 0.02:
            return {'detected': False, 'correction_depth': 0.0, 'direction': None, 'likely_finished': False}
        
        # Detectar pico (para correção de baixa) ou fundo (para correção de alta)
        peak_price = recent['high'].max()
        peak_idx = recent['high'].idxmax()
        trough_price = recent['low'].min()
        trough_idx = recent['low'].idxmin()
        
        current_price = recent['close'].iloc[-1]
        
        # Correção de baixa (após alta)
        if peak_idx < len(recent) - 5:  # Pico não é agora
            correction = (peak_price - current_price) / peak_price
            if 0.2 < correction < 0.7:  # Correção típica 20-70%
                # Fibonacci: 38.2%, 50%, 61.8%
                fib_levels = [0.382, 0.5, 0.618]
                at_fib = any(abs(correction - fib) < 0.05 for fib in fib_levels)
                
                return {
                    'detected': True,
                    'correction_depth': correction,
                    'direction': 'down',
                    'likely_finished': at_fib
                }
        
        # Correção de alta (após baixa)
        if trough_idx < len(recent) - 5:  # Fundo não é agora
            correction = (current_price - trough_price) / trough_price
            if 0.2 < correction < 0.7:
                fib_levels = [0.382, 0.5, 0.618]
                at_fib = any(abs(correction - fib) < 0.05 for fib in fib_levels)
                
                return {
                    'detected': True,
                    'correction_depth': correction,
                    'direction': 'up',
                    'likely_finished': at_fib
                }
        
        return {'detected': False, 'correction_depth': 0.0, 'direction': None, 'likely_finished': False}
    
    def get_wave_momentum(self, df: pd.DataFrame) -> str:
        """
        Determina momento da onda: impulse vs correction
        
        Returns:
            'impulsive_up' | 'impulsive_down' | 'corrective' | 'neutral'
        """
        impulse = self.detect_impulse_wave(df)
        correction = self.detect_corrective_wave(df)
        
        # Priorizar impulso (mais forte)
        if impulse['detected']:
            if impulse['direction'] == 'bullish':
                return 'impulsive_up'
            else:
                return 'impulsive_down'
        
        # Depois correção
        if correction['detected']:
            return 'corrective'
        
        return 'neutral'
    
    def get_elliott_score(self, df: pd.DataFrame, direction: str) -> float:
        """
        Calcula score Elliott para direção
        
        Args:
            df: DataFrame OHLCV
            direction: 'BUY' ou 'SELL'
        
        Returns:
            Score 0.0-1.0
        """
        impulse = self.detect_impulse_wave(df)
        correction = self.detect_corrective_wave(df)
        momentum = self.get_wave_momentum(df)
        
        score = 0.0
        
        if direction == 'BUY':
            # Impulso de alta em andamento
            if momentum == 'impulsive_up':
                score += 0.5 * impulse['strength']
            
            # Correção de alta terminando (potencial reversão para cima)
            if correction['detected'] and correction['direction'] == 'up' and correction['likely_finished']:
                score += 0.4
            
            # Evitar comprar em impulso de baixa
            if momentum == 'impulsive_down':
                score = 0.0
        
        elif direction == 'SELL':
            # Impulso de baixa em andamento
            if momentum == 'impulsive_down':
                score += 0.5 * impulse['strength']
            
            # Correção de baixa terminando (potencial reversão para baixo)
            if correction['detected'] and correction['direction'] == 'down' and correction['likely_finished']:
                score += 0.4
            
            # Evitar vender em impulso de alta
            if momentum == 'impulsive_up':
                score = 0.0
        
        return min(1.0, score)
    
    def get_analysis(self, df: pd.DataFrame) -> Dict:
        """
        Análise completa Elliott Wave
        
        Returns:
            Dicionário com informações de ondas
        """
        impulse = self.detect_impulse_wave(df)
        correction = self.detect_corrective_wave(df)
        momentum = self.get_wave_momentum(df)
        
        return {
            'impulse_wave': impulse,
            'corrective_wave': correction,
            'wave_momentum': momentum,
            'score_buy': self.get_elliott_score(df, 'BUY'),
            'score_sell': self.get_elliott_score(df, 'SELL')
        }


if __name__ == '__main__':
    # Teste com dados sintéticos
    print("═" * 60)
    print("ELLIOTT WAVE DETECTOR TEST")
    print("═" * 60)
    
    # Simular onda de impulso de alta (5 ondas)
    np.random.seed(42)
    dates = pd.date_range(start='2026-01-01', periods=150, freq='15m')
    
    # Criar movimento de 5 ondas
    base = 100
    wave_pattern = []
    
    for i in range(150):
        # Onda 1: alta
        if i < 30:
            wave_pattern.append(base + i * 0.3)
        # Onda 2: correção
        elif i < 50:
            wave_pattern.append(wave_pattern[29] - (i - 30) * 0.15)
        # Onda 3: alta forte (maior)
        elif i < 90:
            wave_pattern.append(wave_pattern[49] + (i - 50) * 0.4)
        # Onda 4: correção menor
        elif i < 110:
            wave_pattern.append(wave_pattern[89] - (i - 90) * 0.1)
        # Onda 5: alta final
        else:
            wave_pattern.append(wave_pattern[109] + (i - 110) * 0.25)
    
    close = np.array(wave_pattern) + np.random.randn(150) * 0.5
    high = close + np.abs(np.random.randn(150) * 0.3)
    low = close - np.abs(np.random.randn(150) * 0.3)
    open_price = close + np.random.randn(150) * 0.2
    volume = np.random.randn(150) * 100 + 1000
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    detector = ElliottWaveDetector(lookback_period=100)
    analysis = detector.get_analysis(df)
    
    print(f"Impulse Wave: {analysis['impulse_wave']}")
    print(f"Corrective Wave: {analysis['corrective_wave']}")
    print(f"Wave Momentum: {analysis['wave_momentum']}")
    print(f"\nScore BUY: {analysis['score_buy']:.2f}")
    print(f"Score SELL: {analysis['score_sell']:.2f}")
    print("═" * 60)
