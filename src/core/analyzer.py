"""
Módulo de Análise e Tomada de Decisão
Analisa indicadores e gera sinais de compra/venda com probabilidades
"""
import pandas as pd
import numpy as np
from config.config import BUY_THRESHOLD, INDICATORS_CONFIG, INDICATOR_WEIGHTS, SELL_THRESHOLD


class TradingAnalyzer:
    """Classe para análise e geração de sinais de trading"""
    
    def __init__(self, df, config=INDICATORS_CONFIG, weights=INDICATOR_WEIGHTS):
        """
        Inicializa o analisador
        df: DataFrame com indicadores já calculados
        """
        self.df = df
        self.config = config
        self.weights = weights
        self.signals = pd.DataFrame(index=df.index)
        
    def analyze_rsi(self):
        """
        Analisa RSI e retorna score (-1 a 1)
        -1 = forte venda, 0 = neutro, 1 = forte compra
        """
        rsi = self.df['rsi']
        oversold = self.config['RSI']['oversold']
        overbought = self.config['RSI']['overbought']
        
        # Trata o miolo do RSI como neutro e usa reversao apenas nas extremidades.
        score = np.where(
            rsi < oversold,
            np.clip((oversold - rsi) / max(oversold, 1), 0, 1),
            np.where(
                rsi > overbought,
                -np.clip((rsi - overbought) / max(100 - overbought, 1), 0, 1),
                0.0
            )
        )
        
        self.signals['rsi_score'] = score
        return score
    
    def analyze_macd(self):
        """
        Analisa MACD e retorna score (-1 a 1)
        """
        macd = self.df['macd']
        macd_signal = self.df['macd_signal']
        macd_diff = self.df['macd_diff']
        
        # Score baseado no cruzamento e divergência
        score = np.where(
            (macd > macd_signal) & (macd_diff > 0),
            np.clip(macd_diff / macd_diff.abs().rolling(20).mean(), -1, 1),
            np.where(
                (macd < macd_signal) & (macd_diff < 0),
                np.clip(macd_diff / macd_diff.abs().rolling(20).mean(), -1, 1),
                0
            )
        )
        
        self.signals['macd_score'] = score
        return score
    
    def analyze_bollinger(self):
        """
        Analisa Bandas de Bollinger e retorna score (-1 a 1)
        """
        close = self.df['close']
        bb_upper = self.df['bb_upper']
        bb_lower = self.df['bb_lower']
        
        # Considera reversao apenas quando o preco realmente estoura as bandas.
        bb_range = bb_upper - bb_lower
        score = np.where(
            close < bb_lower,
            np.clip((bb_lower - close) / bb_range, 0, 1),
            np.where(
                close > bb_upper,
                -np.clip((close - bb_upper) / bb_range, 0, 1),
                0.0,
            )
        )
        
        self.signals['bollinger_score'] = score
        return score
    
    def analyze_ema(self):
        """
        Analisa cruzamento de EMAs e retorna score (-1 a 1)
        """
        ema_short_period = self.config['EMA_SHORT']['period']
        ema_long_period = self.config['EMA_LONG']['period']
        
        ema_short = self.df[f'ema_{ema_short_period}']
        ema_long = self.df[f'ema_{ema_long_period}']
        close = self.df['close']
        
        # Score baseado na relação entre EMAs e preço
        ema_diff = (ema_short - ema_long) / ema_long * 100
        price_vs_ema = (close - ema_short) / ema_short * 100
        
        score = np.clip((ema_diff + price_vs_ema) / 10, -1, 1)
        
        self.signals['ema_score'] = score
        return score
    
    def analyze_volume(self):
        """
        Analisa volume e retorna score (-1 a 1)
        """
        volume = self.df['volume']
        volume_ma = self.df['volume_ma']
        close = self.df['close']
        
        # Volume relativo
        volume_ratio = volume / volume_ma
        
        # Trend de preço
        price_change = close.pct_change()
        
        # Score: volume alto + preço subindo = compra
        score = np.where(
            (volume_ratio > 1.5) & (price_change > 0),
            np.clip(volume_ratio - 1, 0, 1),
            np.where(
                (volume_ratio > 1.5) & (price_change < 0),
                -np.clip(volume_ratio - 1, 0, 1),
                0
            )
        )
        
        self.signals['volume_score'] = score
        return score
    
    def analyze_atr(self):
        """
        Analisa ATR (volatilidade) e retorna score
        Alta volatilidade = score mais conservador
        """
        atr = self.df['atr']
        close = self.df['close']
        
        # ATR relativo ao preço
        atr_percent = (atr / close) * 100
        atr_ma = atr_percent.rolling(20).mean()
        
        # Score: alta volatilidade = cautela (score próximo de 0)
        volatility_ratio = atr_percent / atr_ma
        score = 1 - np.clip((volatility_ratio - 1) * 2, 0, 1)
        
        self.signals['atr_score'] = score
        return score
    
    def calculate_composite_score(self):
        """
        Calcula score composto baseado em todos os indicadores
        Retorna valor entre 0 e 1 (0 = venda, 1 = compra)
        """
        # Calcula todos os scores
        self.analyze_rsi()
        self.analyze_macd()
        self.analyze_bollinger()
        self.analyze_ema()
        self.analyze_volume()
        self.analyze_atr()
        
        # Score-base ponderado (faixa esperada: -1 a 1)
        composite_base = (
            self.signals['rsi_score'] * self.weights['RSI'] +
            self.signals['macd_score'] * self.weights['MACD'] +
            self.signals['bollinger_score'] * self.weights['BOLLINGER'] +
            self.signals['ema_score'] * self.weights['EMA'] +
            self.signals['volume_score'] * self.weights['VOLUME']
        )
        
        # ATR nao deve adicionar vies direcional; apenas reduzir conviccao
        # quando a volatilidade relativa estiver desfavoravel.
        atr_adjustment = np.where(self.signals['atr_score'] < 0.5, self.signals['atr_score'] * 2, 1.0)
        composite = composite_base * atr_adjustment
        
        # Normaliza para 0-1
        self.signals['composite_score'] = (composite + 1) / 2
        
        return self.signals['composite_score']
    
    def generate_signals(self, buy_threshold=None, sell_threshold=None):
        """
        Gera sinais de compra/venda baseado no score composto
        Retorna: 1 = COMPRA, -1 = VENDA, 0 = NEUTRO
        
        Thresholds otimizados para qualidade:
        - COMPRA: score > BUY_THRESHOLD
        - VENDA: score < SELL_THRESHOLD
        """
        if buy_threshold is None:
            buy_threshold = BUY_THRESHOLD
        if sell_threshold is None:
            sell_threshold = SELL_THRESHOLD

        self.calculate_composite_score()
        
        signals = np.where(
            self.signals['composite_score'] > buy_threshold,
            1,  # COMPRA
            np.where(
                self.signals['composite_score'] < sell_threshold,
                -1,  # VENDA
                0  # NEUTRO
            )
        )
        
        self.signals['signal'] = signals
        return signals
    
    def get_current_signal(self):
        """Retorna o sinal mais recente"""
        if 'signal' not in self.signals.columns:
            self.generate_signals()
        
        latest = self.signals.iloc[-1]
        
        return {
            'signal': int(latest['signal']),
            'score': float(latest['composite_score']),
            'rsi_score': float(latest['rsi_score']),
            'macd_score': float(latest['macd_score']),
            'bollinger_score': float(latest['bollinger_score']),
            'ema_score': float(latest['ema_score']),
            'volume_score': float(latest['volume_score']),
            'atr_score': float(latest['atr_score']),
            'probability': self._calculate_probability(latest['composite_score'])
        }
    
    def _calculate_probability(self, score):
        """
        Converte score em probabilidade de sucesso
        Score próximo de 0.5 = baixa confiança
        Score próximo de 0 ou 1 = alta confiança
        """
        distance_from_neutral = abs(score - 0.5)
        probability = 50 + (distance_from_neutral * 100)
        return round(probability, 2)
    
    def get_signals_dataframe(self):
        """Retorna DataFrame com todos os sinais"""
        return self.signals
