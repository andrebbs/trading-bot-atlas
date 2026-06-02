"""
Exemplo de Integração SMC no Trading Analyzer
----------------------------------------------
Demonstra como combinar SMC com indicadores técnicos tradicionais
para melhorar a taxa de acerto.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core import ExchangeConnector, TechnicalIndicators
from src.core.smc_detector import SMCDetector
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedTradingAnalyzer:
    """
    Analyzer melhorado com SMC (Smart Money Concepts).
    
    Lógica:
    1. Calcula score tradicional (indicadores técnicos)
    2. Calcula score SMC (estrutura de mercado)
    3. Combina ambos com pesos
    4. Adiciona filtro de estrutura obrigatória
    """
    
    def __init__(self, exchange_connector: ExchangeConnector):
        self.exchange = exchange_connector
        self.smc_detector = SMCDetector(lookback_period=50)
        
        # Pesos para score final
        self.weight_traditional = 0.5  # 50% indicadores
        self.weight_smc = 0.5          # 50% SMC
        
        # Thresholds
        self.buy_threshold = 0.65
        self.sell_threshold = 0.35
        self.min_smc_score = 0.40  # SMC mínimo para entrar
    
    def _calculate_traditional_score(self, df):
        """Calcula score tradicional baseado em RSI e MACD."""
        if len(df) < 30:
            return 0.5, 'NEUTRAL'
        
        # RSI score
        rsi = df['rsi'].iloc[-1]
        if rsi < 30:
            rsi_score = 1.0  # oversold = compra
        elif rsi > 70:
            rsi_score = 0.0  # overbought = venda
        else:
            rsi_score = 0.5  # neutro
        
        # MACD score
        macd = df['macd'].iloc[-1]
        macd_signal = df['macd_signal'].iloc[-1]
        if macd > macd_signal:
            macd_score = 1.0  # bullish
        else:
            macd_score = 0.0  # bearish
        
        # Score combinado
        score = (rsi_score * 0.4 + macd_score * 0.6)
        
        # Direção
        if score > 0.65:
            direction = 'BUY'
        elif score < 0.35:
            direction = 'SELL'
        else:
            direction = 'NEUTRAL'
        
        return score, direction
    
    def analyze_with_smc(self, symbol: str, timeframe: str = '5m', limit: int = 100):
        """
        Análise completa: indicadores + SMC.
        
        Returns:
            {
                'symbol': str,
                'direction': 'BUY' | 'SELL' | 'NEUTRAL',
                'traditional_score': float,
                'smc_score': float,
                'final_score': float,
                'smc_structure': str,
                'confidence': float,
                'reason': str,
                'smc_details': dict
            }
        """
        # 1. Obter dados
        df = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        # 2. Calcular indicadores
        from config.config import INDICATORS_CONFIG
        indicators = TechnicalIndicators(df)
        indicators.calculate_all_indicators(INDICATORS_CONFIG)
        df = indicators.df
        
        # 3. Análise tradicional
        trad_score, trad_direction = self._calculate_traditional_score(df)
        
        # 3. Análise SMC
        smc_analysis = self.smc_detector.get_analysis(df)
        smc_structure = smc_analysis['structure']
        
        # 4. Determinar direção preliminar
        if trad_direction == 'BUY':
            direction = 'BUY'
            smc_score = smc_analysis['score_buy']
        elif trad_direction == 'SELL':
            direction = 'SELL'
            smc_score = smc_analysis['score_sell']
        else:
            direction = 'NEUTRAL'
            smc_score = 0.0
        
        # 5. Calcular score final ponderado
        final_score = (
            self.weight_traditional * trad_score +
            self.weight_smc * smc_score
        )
        
        # 6. Aplicar filtros de estrutura SMC
        reason = []
        filtered_direction = direction
        
        # FILTRO 1: Estrutura deve alinhar com direção
        if direction == 'BUY' and smc_structure not in ['bullish', 'transition']:
            filtered_direction = 'NEUTRAL'
            reason.append(f"Estrutura {smc_structure} não suporta BUY")
        
        if direction == 'SELL' and smc_structure not in ['bearish', 'transition']:
            filtered_direction = 'NEUTRAL'
            reason.append(f"Estrutura {smc_structure} não suporta SELL")
        
        # FILTRO 2: SMC score mínimo
        if smc_score < self.min_smc_score:
            filtered_direction = 'NEUTRAL'
            reason.append(f"SMC score baixo ({smc_score:.2f} < {self.min_smc_score})")
        
        # FILTRO 3: Evitar ranging market
        if smc_structure == 'ranging':
            filtered_direction = 'NEUTRAL'
            reason.append("Mercado lateralizado (ranging)")
        
        # FILTRO 4: Final score deve passar threshold
        if filtered_direction == 'BUY' and final_score < self.buy_threshold:
            filtered_direction = 'NEUTRAL'
            reason.append(f"Score final abaixo do threshold BUY ({final_score:.2f} < {self.buy_threshold})")
        
        if filtered_direction == 'SELL' and final_score > self.sell_threshold:
            filtered_direction = 'NEUTRAL'
            reason.append(f"Score final acima do threshold SELL ({final_score:.2f} > {self.sell_threshold})")
        
        # 7. Calcular confiança
        confidence = final_score if filtered_direction != 'NEUTRAL' else 0.0
        
        # Boost de confiança se estrutura + indicadores alinham perfeitamente
        if (direction == 'BUY' and smc_structure == 'bullish' and smc_score > 0.7 and trad_score > 0.7):
            confidence = min(confidence * 1.2, 1.0)  # boost 20%
            reason.append("CONFLUÊNCIA PERFEITA: Bullish structure + High scores")
        
        if (direction == 'SELL' and smc_structure == 'bearish' and smc_score > 0.7 and trad_score > 0.7):
            confidence = min(confidence * 1.2, 1.0)
            reason.append("CONFLUÊNCIA PERFEITA: Bearish structure + High scores")
        
        # 8. Retornar análise completa
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'direction': filtered_direction,
            'traditional_score': trad_score,
            'smc_score': smc_score,
            'final_score': final_score,
            'smc_structure': smc_structure,
            'confidence': confidence,
            'reason': ' | '.join(reason) if reason else 'Todos os filtros passaram',
            'smc_details': {
                'bos': smc_analysis['bos'],
                'choch': smc_analysis['choch'],
                'order_blocks_bullish': len(smc_analysis['order_blocks']['bullish_ob']),
                'order_blocks_bearish': len(smc_analysis['order_blocks']['bearish_ob']),
                'fvg_bullish': len(smc_analysis['fvgs']['bullish_fvg']),
                'fvg_bearish': len(smc_analysis['fvgs']['bearish_fvg'])
            },
            'price': df['close'].iloc[-1] if len(df) > 0 else 0.0,
            'rsi': df['rsi'].iloc[-1] if len(df) > 0 else 50.0
        }
    
    def should_enter_trade(self, analysis: dict) -> bool:
        """
        Decisão final: entrar ou não no trade.
        
        Returns:
            True se deve entrar, False caso contrário
        """
        return (
            analysis['direction'] in ['BUY', 'SELL'] and
            analysis['confidence'] >= 0.60 and
            analysis['smc_score'] >= self.min_smc_score
        )


# ─────────────────────────────────────────────────────────────────────────────
# Teste
# ─────────────────────────────────────────────────────────────────────────────

def test_enhanced_analyzer():
    """Testa analyzer melhorado com dados reais."""
    print('═' * 80)
    print('TESTE: Enhanced Trading Analyzer com SMC')
    print('═' * 80)
    print()
    
    # Conectar exchange
    exchange = ExchangeConnector(testnet=True)
    analyzer = EnhancedTradingAnalyzer(exchange)
    
    # Testar com BTC
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    for symbol in symbols:
        try:
            print(f'\n🔍 Analisando {symbol}...')
            analysis = analyzer.analyze_with_smc(symbol, timeframe='5m', limit=100)
            
            print(f'\n┌─ {symbol} ─────────────────────────────────────────────')
            print(f'│ Direção: {analysis["direction"]}')
            print(f'│ Score Tradicional: {analysis["traditional_score"]:.2f}')
            print(f'│ Score SMC: {analysis["smc_score"]:.2f}')
            print(f'│ Score Final: {analysis["final_score"]:.2f}')
            print(f'│ Estrutura SMC: {analysis["smc_structure"]}')
            print(f'│ Confiança: {analysis["confidence"]:.2%}')
            print(f'│ Preço: ${analysis["price"]:.2f}')
            print(f'│ RSI: {analysis["rsi"]:.1f}')
            print(f'│')
            print(f'│ SMC Details:')
            print(f'│   BOS: {analysis["smc_details"]["bos"]["type"]}')
            print(f'│   CHoCH: {analysis["smc_details"]["choch"]["type"]}')
            print(f'│   Order Blocks (Bull/Bear): {analysis["smc_details"]["order_blocks_bullish"]}/{analysis["smc_details"]["order_blocks_bearish"]}')
            print(f'│   FVG (Bull/Bear): {analysis["smc_details"]["fvg_bullish"]}/{analysis["smc_details"]["fvg_bearish"]}')
            print(f'│')
            print(f'│ Razão: {analysis["reason"]}')
            print(f'│')
            
            should_enter = analyzer.should_enter_trade(analysis)
            decision = '✅ EXECUTAR TRADE' if should_enter else '❌ NÃO ENTRAR'
            print(f'│ Decisão Final: {decision}')
            print(f'└──────────────────────────────────────────────────────────')
        
        except Exception as e:
            print(f'❌ Erro ao analisar {symbol}: {e}')
    
    print()
    print('═' * 80)


if __name__ == '__main__':
    test_enhanced_analyzer()
