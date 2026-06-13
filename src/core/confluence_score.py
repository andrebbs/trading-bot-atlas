"""
Confluence Score System - Sistema Master ATLAS
Combina TODOS os detectores para gerar score final de confluência

ATLAS = Advanced Technical Liquidity Analysis System
Autor: Sistema ATLAS - Fase 5 (MASTER)
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import logging
import sys
import os

# Add project root to path for testing
if __name__ == '__main__':
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.core.smc_detector import SMCDetector
from src.core.wyckoff_detector import WyckoffDetector
from src.core.price_action_detector import PriceActionDetector
from src.core.elliott_wave_detector import ElliottWaveDetector

logger = logging.getLogger(__name__)


class ConfluenceScoreSystem:
    """
    Sistema Master que combina todas as técnicas de análise:
    - Indicadores Tradicionais (RSI, MACD, BB, EMA, Volume)
    - Smart Money Concepts (SMC)
    - Wyckoff (Volume Profile)
    - Price Action (Padrões de Candle)
    - Elliott Wave (Impulso/Correção)
    
    Retorna score de confluência 0-100 e lista de fatores que concordam
    """
    
    # PESOS DE CADA TÉCNICA (total = 1.0)
    WEIGHTS = {
        'traditional': 0.15,  # Indicadores reduzidos (eram ruins sozinhos)
        'smc': 0.30,          # SMC alto peso (estrutura de mercado)
        'wyckoff': 0.25,      # Wyckoff médio-alto (volume e fase)
        'price_action': 0.20, # Price Action médio (padrões confiáveis)
        'elliott': 0.10       # Elliott baixo (mais subjetivo)
    }

    # Ajustes para evitar score artificialmente deprimido quando poucas técnicas
    # estão ativas no candle atual (cenário comum em 1m/5m).
    ACTIVE_TECHNIQUE_MIN_SCORE = float(os.getenv('ATLAS_ACTIVE_TECHNIQUE_MIN_SCORE', '0.20'))
    NORMALIZATION_BIAS = float(os.getenv('ATLAS_NORMALIZATION_BIAS', '0.45'))
    AGREEMENT_THRESHOLD = float(os.getenv('ATLAS_AGREEMENT_THRESHOLD', '0.30'))

    STRONG_MIN_SCORE = float(os.getenv('ATLAS_STRONG_MIN_SCORE', '0.68'))
    STRONG_MIN_CONFLUENCE = int(os.getenv('ATLAS_STRONG_MIN_CONFLUENCE', '4'))
    MIN_SCORE = float(os.getenv('ATLAS_MIN_SCORE', '0.50'))
    MIN_CONFLUENCE = int(os.getenv('ATLAS_MIN_CONFLUENCE', '3'))

    
    def __init__(self):
        """Inicializa todos os detectores"""
        self.smc = SMCDetector(lookback_period=50)
        self.wyckoff = WyckoffDetector(lookback_period=50)
        self.price_action = PriceActionDetector(lookback_period=30)
        self.elliott = ElliottWaveDetector(lookback_period=100)
    
    def calculate_traditional_score(self, df: pd.DataFrame, direction: str, signal_data: Optional[Dict] = None) -> float:
        """
        Score baseado em indicadores tradicionais (RSI, MACD, etc)
        Usa dados já calculados pelo TradingAnalyzer quando disponíveis e
        aplica fallback direcional por EMA/RSI/ADX/Stoch para evitar neutro fixo.
        
        Args:
            df: DataFrame com indicadores calculados
            direction: 'BUY' ou 'SELL'
            signal_data: Dicionário opcional de signal_data do analyzer
        
        Returns:
            Score 0.0-1.0
        """
        # 1) Base vinda do analyzer (quando presente)
        base_score = 0.5
        if signal_data:
            try:
                base_score = float(signal_data.get('score', 0.5))
            except (TypeError, ValueError):
                base_score = 0.5

        # 2) Fallback direcional usando indicadores já no dataframe
        try:
            def _safe_float(value, default: float) -> float:
                try:
                    v = float(value)
                except (TypeError, ValueError):
                    return default
                if np.isnan(v) or np.isinf(v):
                    return default
                return v

            last = df.iloc[-1]
            close = _safe_float(last.get('close', 0.0), 0.0)
            ema9 = _safe_float(last.get('ema_9', last.get('ema9', 0.0)), 0.0)
            ema20 = _safe_float(last.get('ema_20', last.get('ema20', 0.0)), 0.0)
            ema50 = _safe_float(last.get('ema_50', last.get('ema50', 0.0)), 0.0)
            rsi = _safe_float(last.get('rsi', 50.0), 50.0)
            adx = _safe_float(last.get('adx', 0.0), 0.0)
            stoch_k = _safe_float(last.get('stoch_k', 50.0), 50.0)
            stoch_d = _safe_float(last.get('stoch_d', 50.0), 50.0)

            trend = 0.0
            if close > 0 and ema9 > 0 and ema20 > 0:
                if direction == 'BUY':
                    if close > ema9 > ema20:
                        trend += 0.45
                    elif close > ema20:
                        trend += 0.25
                    elif close > ema50 > 0:
                        trend += 0.10
                else:
                    if close < ema9 < ema20:
                        trend += 0.45
                    elif close < ema20:
                        trend += 0.25
                    elif close < ema50 > 0:
                        trend += 0.10

            momentum = 0.0
            if direction == 'BUY':
                if 52 <= rsi <= 70:
                    momentum += 0.20
                elif 45 <= rsi < 52:
                    momentum += 0.10
                if stoch_k > stoch_d and stoch_k < 85:
                    momentum += 0.15
            else:
                if 30 <= rsi <= 48:
                    momentum += 0.20
                elif 48 < rsi <= 55:
                    momentum += 0.10
                if stoch_k < stoch_d and stoch_k > 15:
                    momentum += 0.15

            strength = 0.0
            if adx >= 25:
                strength += 0.20
            elif adx >= 18:
                strength += 0.10
            elif adx >= 12:
                strength += 0.05

            directional_score = min(1.0, max(0.0, trend + momentum + strength))

            # 3) Blend: privilegia leitura direcional sem ignorar analyzer
            # Se analyzer vier neutro (0.5), a leitura direcional domina.
            if abs(base_score - 0.5) < 0.03:
                return directional_score
            return min(1.0, max(0.0, (0.35 * base_score) + (0.65 * directional_score)))
        except Exception:
            return min(1.0, max(0.0, base_score))
    
    def get_confluence_score(
        self,
        df: pd.DataFrame,
        direction: str,
        signal_data: Optional[Dict] = None
    ) -> Dict:
        """
        Calcula score de confluência combinando TODAS as técnicas
        
        Args:
            df: DataFrame com OHLCV + indicadores
            direction: 'BUY' ou 'SELL'
            signal_data: Opcional - dados do TradingAnalyzer
        
        Returns:
            {
                'final_score': 0.0-1.0,
                'final_score_pct': 0-100,
                'direction': 'BUY' | 'SELL',
                'scores': {
                    'traditional': float,
                    'smc': float,
                    'wyckoff': float,
                    'price_action': float,
                    'elliott': float
                },
                'confluence_count': int (quantos concordam > 0.4),
                'factors_agree': [list of strings],
                'factors_disagree': [list of strings],
                'recommendation': 'STRONG_BUY' | 'BUY' | 'NEUTRAL' | 'SELL' | 'STRONG_SELL'
            }
        """
        # Calcular scores individuais
        scores = {}
        
        # 1. Tradicional (indicadores)
        if signal_data:
            scores['traditional'] = self.calculate_traditional_score(df, direction, signal_data)
        else:
            scores['traditional'] = self.calculate_traditional_score(df, direction, None)
        
        # 2. SMC
        smc_score = self.smc.get_smc_score(df, direction)
        scores['smc'] = smc_score
        
        # 3. Wyckoff
        wyckoff_score = self.wyckoff.get_wyckoff_score(df, direction)
        scores['wyckoff'] = wyckoff_score
        
        # 4. Price Action
        pa_score = self.price_action.get_price_action_score(df, direction)
        scores['price_action'] = pa_score
        
        # 5. Elliott Wave
        elliott_score = self.elliott.get_elliott_score(df, direction)
        scores['elliott'] = elliott_score
        
        # Score bruto ponderado (0-1)
        raw_score = 0.0
        for technique, weight in self.WEIGHTS.items():
            raw_score += scores[technique] * weight

        raw_score = min(1.0, max(0.0, raw_score))

        # Score normalizado por técnicas efetivamente ativas para reduzir
        # falso "sempre neutro" quando detectores de padrão não disparam.
        active_weight = sum(
            weight
            for technique, weight in self.WEIGHTS.items()
            if scores.get(technique, 0.0) >= self.ACTIVE_TECHNIQUE_MIN_SCORE
        )
        # ----------------------------
        # NORMALIZAÇÃO
        # ----------------------------
        normalized_score = raw_score / active_weight if active_weight > 0 else raw_score
        normalized_score = min(1.0, max(0.0, normalized_score))

        # ----------------------------
        # PENALIZAÇÃO POR COBERTURA
        # ----------------------------
        coverage_ratio = active_weight  # total = 1.0

        coverage_penalty = 0.55 + (0.45 * coverage_ratio)

        # ----------------------------
        # BLEND MAIS CONSERVADOR
        # ----------------------------
        blended_score = (
            (0.5 * raw_score) +
            (0.5 * normalized_score)
        )

        final_score = blended_score * coverage_penalty
        final_score = min(1.0, max(0.0, final_score))

        final_score_pct = int(round(final_score * 100))
        raw_score_pct = int(round(raw_score * 100))
        
        # Contar confluências (score >= limiar = concorda)
        agreement_threshold = self.AGREEMENT_THRESHOLD
        factors_agree = []
        factors_disagree = []
        
        for technique, score in scores.items():
            if score >= agreement_threshold:
                factors_agree.append(technique)
            else:
                factors_disagree.append(technique)
        
        confluence_count = len(factors_agree)
        
        # Recomendação baseada em score final e confluência
        recommendation = self._get_recommendation(
            final_score,
            confluence_count,
            direction
        )
        
        return {
            'final_score': final_score,
            'final_score_pct': final_score_pct,
            'raw_score': raw_score,
            'raw_score_pct': raw_score_pct,
            'normalized_score': normalized_score,
            'direction': direction,
            'scores': scores,
            'confluence_count': confluence_count,
            'factors_agree': factors_agree,
            'factors_disagree': factors_disagree,
            'recommendation': recommendation,
            'weights': self.WEIGHTS
        }
    
    def _get_recommendation(self, score: float, confluence_count: int, direction: str) -> str:
        """
        Gera recomendação textual baseada em score e confluência
        
        Args:
            score: Score final 0.0-1.0
            confluence_count: Quantos fatores concordam
            direction: BUY ou SELL
        
        Returns:
            String de recomendação
        """
        # Critérios padrão calibrados para curto prazo, configuráveis via env.
        if score >= self.STRONG_MIN_SCORE and confluence_count >= self.STRONG_MIN_CONFLUENCE:
            return f'STRONG_{direction}'

        if score >= self.MIN_SCORE and confluence_count >= self.MIN_CONFLUENCE:
            return direction

        # Nível fraco para leitura direcional com baixa convicção.
        if score >= 0.40 and confluence_count >= 2:
            return f'WEAK_{direction}'

        return 'NEUTRAL'
    
    def should_enter_trade(
        self,
        df: pd.DataFrame,
        direction: str,
        signal_data: Optional[Dict] = None,
        min_score: float = 0.58,
        min_confluence: int = 3
    ) -> Tuple[bool, Dict]:
        """
        Decisão final: deve entrar no trade?
        
        Args:
            df: DataFrame OHLCV + indicadores
            direction: 'BUY' ou 'SELL'
            signal_data: Dados do TradingAnalyzer (opcional)
            min_score: Score mínimo para entrada (padrão 0.55 = 55%)
            min_confluence: Mínimo de fatores concordantes (padrão 3)
        
        Returns:
            (should_enter: bool, analysis: Dict)
        """
        analysis = self.get_confluence_score(df, direction, signal_data)
        
        # 1) Bloquear sinais fracos
        recommendation = analysis.get('recommendation', 'NEUTRAL')
        if recommendation.startswith('WEAK'):
            analysis['block_reason'] = 'Sinal fraco - baixa qualidade'
            return False, analysis

        if recommendation == 'NEUTRAL':
            analysis['block_reason'] = 'Sem confluência'
            return False, analysis

        # 2) Filtro SMC estrutural — BOS/CHoCH + Sweep
        smc_analysis = self.smc.get_analysis(df)
        if smc_analysis.get('structure') == 'ranging':
            analysis['block_reason'] = 'Mercado lateral (SMC)'
            return False, analysis

        bos = smc_analysis.get('bos', {}) or {}
        choch = smc_analysis.get('choch', {}) or {}
        sweep = smc_analysis.get('liquidity_sweep', {}) or {}

        if direction == 'BUY':
            has_structure_break = bool(bos.get('bullish_bos') or choch.get('bullish_choch'))
            has_directional_sweep = bool(sweep.get('swept_low'))
        else:
            has_structure_break = bool(bos.get('bearish_bos') or choch.get('bearish_choch'))
            has_directional_sweep = bool(sweep.get('swept_high'))

        # BOS/CHoCH vira gatilho obrigatório de estrutura. Sweep é forte, mas não obrigatório.
        if not has_structure_break:
            analysis['block_reason'] = f'Sem BOS/CHoCH válido para {direction}'
            analysis['smc_gate'] = {
                'has_structure_break': False,
                'has_directional_sweep': has_directional_sweep,
                'bos': bos,
                'choch': choch,
                'sweep': sweep,
            }
            return False, analysis

        analysis['smc_gate'] = {
            'has_structure_break': True,
            'has_directional_sweep': has_directional_sweep,
            'bos': bos,
            'choch': choch,
            'sweep': sweep,
        }

        # 3) Filtro de volatilidade
        try:
            atr = float(df['atr'].iloc[-1])
            price = float(df['close'].iloc[-1])
            volatility = (atr / price) if price > 0 else 0.0

            if volatility < 0.003:
                analysis['block_reason'] = 'Baixa volatilidade'
                return False, analysis
        except Exception:
            pass

        # 4) Verificar score
        if analysis['final_score'] < min_score:
            analysis['block_reason'] = f'Score baixo ({analysis["final_score"]:.2f})'
            return False, analysis

        # 5) Verificar confluência
        if analysis['confluence_count'] < min_confluence:
            analysis['block_reason'] = f'Pouca confluência ({analysis["confluence_count"]})'
            return False, analysis

        analysis['block_reason'] = None
        return True, analysis
    
    def get_full_analysis(self, df: pd.DataFrame, signal_data: Optional[Dict] = None) -> Dict:
        """
        Análise completa para ambas as direções (BUY e SELL)
        
        Returns:
            {
                'buy_analysis': Dict,
                'sell_analysis': Dict,
                'best_direction': 'BUY' | 'SELL' | 'NEUTRAL',
                'best_score': float,
                'smc_structure': string,
                'wyckoff_phase': string,
                'elliott_momentum': string
            }
        """
        buy_analysis = self.get_confluence_score(df, 'BUY', signal_data)
        sell_analysis = self.get_confluence_score(df, 'SELL', signal_data)
        
        # Informações de contexto
        smc_analysis = self.smc.get_analysis(df)
        wyckoff_analysis = self.wyckoff.get_analysis(df)
        elliott_analysis = self.elliott.get_analysis(df)
        
        # Determinar melhor direção
        if buy_analysis['final_score'] > sell_analysis['final_score']:
            best_direction = 'BUY'
            best_score = buy_analysis['final_score']
        elif sell_analysis['final_score'] > buy_analysis['final_score']:
            best_direction = 'SELL'
            best_score = sell_analysis['final_score']
        else:
            best_direction = 'NEUTRAL'
            best_score = 0.5
        
        # Se score muito baixo, forçar NEUTRAL
        if best_score < 0.5:
            best_direction = 'NEUTRAL'
        
        return {
            'buy_analysis': buy_analysis,
            'sell_analysis': sell_analysis,
            'best_direction': best_direction,
            'best_score': best_score,
            'smc_structure': smc_analysis['structure'],
            'wyckoff_phase': wyckoff_analysis['phase'],
            'elliott_momentum': elliott_analysis['wave_momentum'],
            'context': {
                'smc': smc_analysis,
                'wyckoff': wyckoff_analysis,
                'price_action': self.price_action.get_analysis(df),
                'elliott': elliott_analysis
            }
        }


if __name__ == '__main__':
    # Teste com dados sintéticos
    print("═" * 80)
    print("CONFLUENCE SCORE SYSTEM TEST - SISTEMA ATLAS COMPLETO")
    print("═" * 80)
    
    # Criar dados de teste (tendência de alta forte)
    np.random.seed(42)
    dates = pd.date_range(start='2026-01-01', periods=200, freq='5m')
    
    # Simular alta forte com volume
    base = 100
    close = base + np.arange(200) * 0.1 + np.random.randn(200) * 0.3
    high = close + np.abs(np.random.randn(200) * 0.4)
    low = close - np.abs(np.random.randn(200) * 0.3)
    open_price = close + np.random.randn(200) * 0.2
    volume = 1000 + np.random.randn(200) * 200
    volume[-20:] *= 1.5  # Volume aumentando no final
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })
    
    # Sistema de confluência
    confluence = ConfluenceScoreSystem()
    
    # Análise completa
    full_analysis = confluence.get_full_analysis(df)
    
    print(f"\n🔍 ANÁLISE COMPLETA - SISTEMA ATLAS")
    print("─" * 80)
    print(f"Melhor Direção: {full_analysis['best_direction']}")
    print(f"Score Final: {full_analysis['best_score']:.2%}")
    print(f"\nContexto de Mercado:")
    print(f"  • SMC Structure: {full_analysis['smc_structure']}")
    print(f"  • Wyckoff Phase: {full_analysis['wyckoff_phase']}")
    print(f"  • Elliott Momentum: {full_analysis['elliott_momentum']}")
    
    print(f"\n📊 ANÁLISE BUY:")
    buy = full_analysis['buy_analysis']
    print(f"  Score Final: {buy['final_score_pct']}%")
    print(f"  Confluência: {buy['confluence_count']}/5 fatores")
    print(f"  Concordam: {', '.join(buy['factors_agree'])}")
    print(f"  Discordam: {', '.join(buy['factors_disagree']) if buy['factors_disagree'] else 'nenhum'}")
    print(f"  Recomendação: {buy['recommendation']}")
    print(f"\n  Scores Individuais:")
    for tech, score in buy['scores'].items():
        print(f"    - {tech}: {score:.2%}")
    
    print(f"\n📊 ANÁLISE SELL:")
    sell = full_analysis['sell_analysis']
    print(f"  Score Final: {sell['final_score_pct']}%")
    print(f"  Confluência: {sell['confluence_count']}/5 fatores")
    print(f"  Concordam: {', '.join(sell['factors_agree'])}")
    print(f"  Discordam: {', '.join(sell['factors_disagree']) if sell['factors_disagree'] else 'nenhum'}")
    print(f"  Recomendação: {sell['recommendation']}")
    
    # Testar decisão de entrada
    print(f"\n✅ DECISÃO DE ENTRADA:")
    should_buy, buy_dec = confluence.should_enter_trade(df, 'BUY')
    should_sell, sell_dec = confluence.should_enter_trade(df, 'SELL')
    
    print(f"  BUY:  {'✅ ENTRAR' if should_buy else '❌ NÃO ENTRAR'}")
    if not should_buy and 'block_reason' in buy_dec:
        print(f"        Razão: {buy_dec['block_reason']}")
    
    print(f"  SELL: {'✅ ENTRAR' if should_sell else '❌ NÃO ENTRAR'}")
    if not should_sell and 'block_reason' in sell_dec:
        print(f"        Razão: {sell_dec['block_reason']}")
    
    print("═" * 80)
