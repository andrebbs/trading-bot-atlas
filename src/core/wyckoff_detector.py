"""
Wyckoff Detector - Detecta fases e padrões Wyckoff
Identifica: Accumulation, Distribution, Spring, Upthrust, SOW, SOC
Autor: Sistema ATLAS - Fase 2
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


class WyckoffDetector:
    """
    Detector de padrões Wyckoff para análise de volume e acumulação/distribuição
    """
    
    def __init__(self, lookback_period: int = 50):
        """
        Args:
            lookback_period: Número de candles para análise
        """
        self.lookback_period = lookback_period
    
    def detect_phase(self, df: pd.DataFrame) -> Dict:
        """
        Detecta a fase Wyckoff atual
        
        Returns:
            {
                'phase': 'accumulation' | 'distribution' | 'markup' | 'markdown' | 'neutral',
                'confidence': 0.0-1.0,
                'sub_phase': string ou None,
                'volume_confirmation': bool
            }
        """
        if len(df) < self.lookback_period:
            return {'phase': 'neutral', 'confidence': 0.0, 'sub_phase': None, 'volume_confirmation': False}
        
        recent_df = df.tail(self.lookback_period).copy()
        
        # Análise de volume
        avg_volume = recent_df['volume'].mean()
        recent_volume = recent_df['volume'].tail(10).mean()
        volume_increase = recent_volume > avg_volume * 1.2
        
        # Análise de range (lateralização)
        highs = recent_df['high'].tail(20)
        lows = recent_df['low'].tail(20)
        price_range = highs.max() - lows.min()
        avg_candle_range = (recent_df['high'] - recent_df['low']).mean()
        is_ranging = price_range < avg_candle_range * 5  # Range comprimido
        
        # Análise de tendência
        close_start = recent_df['close'].iloc[0]
        close_end = recent_df['close'].iloc[-1]
        trend_pct = ((close_end - close_start) / close_start) * 100
        
        # Detecção de acumulação
        if is_ranging and volume_increase and abs(trend_pct) < 3:
            # Preço lateral + volume alto = possível acumulação
            phase = 'accumulation'
            confidence = 0.7
            sub_phase = 'Phase C' if self._detect_spring(recent_df) else 'Phase B'
        
        # Detecção de distribuição
        elif is_ranging and volume_increase and close_end > close_start:
            # Preço lateral no topo + volume = possível distribuição
            phase = 'distribution'
            confidence = 0.6
            sub_phase = 'Phase C' if self._detect_upthrust(recent_df) else 'Phase B'
        
        # Markup (tendência de alta forte)
        elif trend_pct > 5 and not is_ranging:
            phase = 'markup'
            confidence = 0.8 if volume_increase else 0.5
            sub_phase = 'Phase E'
        
        # Markdown (tendência de baixa forte)
        elif trend_pct < -5 and not is_ranging:
            phase = 'markdown'
            confidence = 0.8 if volume_increase else 0.5
            sub_phase = 'Phase E'
        
        else:
            phase = 'neutral'
            confidence = 0.3
            sub_phase = None
        
        return {
            'phase': phase,
            'confidence': confidence,
            'sub_phase': sub_phase,
            'volume_confirmation': volume_increase
        }
    
    def _detect_spring(self, df: pd.DataFrame) -> bool:
        """
        Spring: Rompimento falso para baixo seguido de reversão forte
        """
        if len(df) < 15:
            return False
        
        recent = df.tail(15)
        
        # Procurar mínima local seguida de recuperação
        lows = recent['low'].values
        closes = recent['close'].values
        volumes = recent['volume'].values
        
        # Última mínima quebrou suporte mas fechou acima
        support = np.percentile(lows[:-5], 25)
        
        for i in range(-5, 0):
            if lows[i] < support and closes[i] > support:
                # Volume acima da média no spring?
                if volumes[i] > volumes.mean() * 1.1:
                    return True
        
        return False
    
    def _detect_upthrust(self, df: pd.DataFrame) -> bool:
        """
        Upthrust: Rompimento falso para cima seguido de rejeição
        """
        if len(df) < 15:
            return False
        
        recent = df.tail(15)
        
        # Procurar máxima local seguida de rejeição
        highs = recent['high'].values
        closes = recent['close'].values
        volumes = recent['volume'].values
        
        # Última máxima quebrou resistência mas fechou abaixo
        resistance = np.percentile(highs[:-5], 75)
        
        for i in range(-5, 0):
            if highs[i] > resistance and closes[i] < resistance:
                # Volume acima da média no upthrust?
                if volumes[i] > volumes.mean() * 1.1:
                    return True
        
        return False
    
    def detect_sign_of_weakness(self, df: pd.DataFrame) -> Dict:
        """
        SOW (Sign of Weakness): Vela de baixa com volume alto após alta
        
        Returns:
            {'detected': bool, 'strength': 0.0-1.0}
        """
        if len(df) < 20:
            return {'detected': False, 'strength': 0.0}
        
        recent = df.tail(20)
        last_candle = recent.iloc[-1]
        prev_candles = recent.iloc[-10:-1]
        
        # Vela de baixa forte
        candle_body = last_candle['close'] - last_candle['open']
        candle_range = last_candle['high'] - last_candle['low']
        is_bearish = candle_body < 0
        body_ratio = abs(candle_body) / candle_range if candle_range > 0 else 0
        
        # Volume acima da média
        avg_volume = prev_candles['volume'].mean()
        volume_spike = last_candle['volume'] > avg_volume * 1.3
        
        # Contexto: estava em alta?
        trend_pct = ((prev_candles['close'].iloc[-1] - prev_candles['close'].iloc[0]) / prev_candles['close'].iloc[0]) * 100
        was_uptrend = trend_pct > 2
        
        if is_bearish and body_ratio > 0.6 and volume_spike and was_uptrend:
            strength = min(1.0, body_ratio + (0.3 if volume_spike else 0))
            return {'detected': True, 'strength': strength}
        
        return {'detected': False, 'strength': 0.0}
    
    def detect_sign_of_strength(self, df: pd.DataFrame) -> Dict:
        """
        SOS (Sign of Strength): Vela de alta com volume alto após baixa
        
        Returns:
            {'detected': bool, 'strength': 0.0-1.0}
        """
        if len(df) < 20:
            return {'detected': False, 'strength': 0.0}
        
        recent = df.tail(20)
        last_candle = recent.iloc[-1]
        prev_candles = recent.iloc[-10:-1]
        
        # Vela de alta forte
        candle_body = last_candle['close'] - last_candle['open']
        candle_range = last_candle['high'] - last_candle['low']
        is_bullish = candle_body > 0
        body_ratio = abs(candle_body) / candle_range if candle_range > 0 else 0
        
        # Volume acima da média
        avg_volume = prev_candles['volume'].mean()
        volume_spike = last_candle['volume'] > avg_volume * 1.3
        
        # Contexto: estava em baixa?
        trend_pct = ((prev_candles['close'].iloc[-1] - prev_candles['close'].iloc[0]) / prev_candles['close'].iloc[0]) * 100
        was_downtrend = trend_pct < -2
        
        if is_bullish and body_ratio > 0.6 and volume_spike and was_downtrend:
            strength = min(1.0, body_ratio + (0.3 if volume_spike else 0))
            return {'detected': True, 'strength': strength}
        
        return {'detected': False, 'strength': 0.0}
    
    def get_wyckoff_score(self, df: pd.DataFrame, direction: str) -> float:
        """
        Calcula score Wyckoff para direção (BUY/SELL)
        
        Args:
            df: DataFrame com OHLCV
            direction: 'BUY' ou 'SELL'
        
        Returns:
            Score 0.0-1.0
        """
        phase_data = self.detect_phase(df)
        sos = self.detect_sign_of_strength(df)
        sow = self.detect_sign_of_weakness(df)
        
        score = 0.0
        
        if direction == 'BUY':
            # Favorável para compra
            if phase_data['phase'] == 'accumulation':
                score += 0.4 * phase_data['confidence']
            elif phase_data['phase'] == 'markup':
                score += 0.3 * phase_data['confidence']
            
            # Spring detectado
            if phase_data['sub_phase'] == 'Phase C' and phase_data['phase'] == 'accumulation':
                score += 0.3
            
            # Sign of Strength
            if sos['detected']:
                score += 0.3 * sos['strength']
        
        elif direction == 'SELL':
            # Favorável para venda
            if phase_data['phase'] == 'distribution':
                score += 0.4 * phase_data['confidence']
            elif phase_data['phase'] == 'markdown':
                score += 0.3 * phase_data['confidence']
            
            # Upthrust detectado
            if phase_data['sub_phase'] == 'Phase C' and phase_data['phase'] == 'distribution':
                score += 0.3
            
            # Sign of Weakness
            if sow['detected']:
                score += 0.3 * sow['strength']
        
        return min(1.0, score)
    
    def get_analysis(self, df: pd.DataFrame) -> Dict:
        """
        Análise completa Wyckoff
        
        Returns:
            Dicionário com todas as informações
        """
        phase_data = self.detect_phase(df)
        sos = self.detect_sign_of_strength(df)
        sow = self.detect_sign_of_weakness(df)
        
        return {
            'phase': phase_data['phase'],
            'phase_confidence': phase_data['confidence'],
            'sub_phase': phase_data['sub_phase'],
            'volume_confirmation': phase_data['volume_confirmation'],
            'sign_of_strength': sos,
            'sign_of_weakness': sow,
            'score_buy': self.get_wyckoff_score(df, 'BUY'),
            'score_sell': self.get_wyckoff_score(df, 'SELL')
        }


if __name__ == '__main__':
    # Teste com dados sintéticos
    print("═" * 60)
    print("WYCKOFF DETECTOR TEST")
    print("═" * 60)
    
    # Simular acumulação (lateral com volume)
    np.random.seed(42)
    dates = pd.date_range(start='2026-01-01', periods=100, freq='1h')
    
    # Preço lateral em torno de 100
    close = 100 + np.random.randn(100) * 2
    high = close + np.abs(np.random.randn(100))
    low = close - np.abs(np.random.randn(100))
    open_price = close + np.random.randn(100) * 0.5
    volume = np.random.randn(100) * 1000 + 5000
    volume[-10:] *= 1.5  # Volume aumentando
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    detector = WyckoffDetector(lookback_period=50)
    analysis = detector.get_analysis(df)
    
    print(f"Fase: {analysis['phase']}")
    print(f"Confiança: {analysis['phase_confidence']:.2f}")
    print(f"Sub-fase: {analysis['sub_phase']}")
    print(f"Volume Confirmação: {analysis['volume_confirmation']}")
    print(f"Sign of Strength: {analysis['sign_of_strength']['detected']} (strength: {analysis['sign_of_strength']['strength']:.2f})")
    print(f"Sign of Weakness: {analysis['sign_of_weakness']['detected']} (strength: {analysis['sign_of_weakness']['strength']:.2f})")
    print(f"Score BUY: {analysis['score_buy']:.2f}")
    print(f"Score SELL: {analysis['score_sell']:.2f}")
    print("═" * 60)
