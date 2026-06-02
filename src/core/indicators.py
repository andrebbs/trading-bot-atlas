"""
Módulo de Indicadores Técnicos
Calcula diversos indicadores para análise técnica
"""
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator, AwesomeOscillatorIndicator
from ta.trend import MACD, EMAIndicator, ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange


class TechnicalIndicators:
    """Classe para calcular indicadores técnicos"""
    
    def __init__(self, df):
        """
        Inicializa com um DataFrame contendo OHLCV
        df deve ter colunas: open, high, low, close, volume
        """
        self.df = df.copy()
        
    def calculate_rsi(self, period=14):
        """Calcula o RSI (Relative Strength Index)"""
        rsi_indicator = RSIIndicator(close=self.df['close'], window=period)
        self.df['rsi'] = rsi_indicator.rsi()
        return self.df['rsi']
    
    def calculate_macd(self, fast=12, slow=26, signal=9):
        """Calcula o MACD"""
        macd_indicator = MACD(
            close=self.df['close'],
            window_fast=fast,
            window_slow=slow,
            window_sign=signal
        )
        self.df['macd'] = macd_indicator.macd()
        self.df['macd_signal'] = macd_indicator.macd_signal()
        self.df['macd_diff'] = macd_indicator.macd_diff()
        return self.df[['macd', 'macd_signal', 'macd_diff']]
    
    def calculate_bollinger_bands(self, period=20, std=2):
        """Calcula as Bandas de Bollinger"""
        bollinger = BollingerBands(
            close=self.df['close'],
            window=period,
            window_dev=std
        )
        self.df['bb_upper'] = bollinger.bollinger_hband()
        self.df['bb_middle'] = bollinger.bollinger_mavg()
        self.df['bb_lower'] = bollinger.bollinger_lband()
        self.df['bb_width'] = bollinger.bollinger_wband()
        return self.df[['bb_upper', 'bb_middle', 'bb_lower', 'bb_width']]
    
    def calculate_ema(self, period=9):
        """Calcula a EMA (Exponential Moving Average)"""
        ema_indicator = EMAIndicator(close=self.df['close'], window=period)
        self.df[f'ema_{period}'] = ema_indicator.ema_indicator()
        return self.df[f'ema_{period}']
    
    def calculate_atr(self, period=14):
        """Calcula o ATR (Average True Range) para volatilidade"""
        atr_indicator = AverageTrueRange(
            high=self.df['high'],
            low=self.df['low'],
            close=self.df['close'],
            window=period
        )
        self.df['atr'] = atr_indicator.average_true_range()
        return self.df['atr']
    
    def calculate_volume_ma(self, period=20):
        """Calcula a média móvel do volume"""
        self.df['volume_ma'] = self.df['volume'].rolling(window=period).mean()
        return self.df['volume_ma']

    def calculate_stochastic(self, k_period=14, d_period=3, smooth_window=3):
        """Calcula estocástico (%K e %D)"""
        stoch = StochasticOscillator(
            high=self.df['high'],
            low=self.df['low'],
            close=self.df['close'],
            window=k_period,
            smooth_window=smooth_window,
        )
        self.df['stoch_k'] = stoch.stoch()
        self.df['stoch_d'] = self.df['stoch_k'].rolling(window=d_period).mean()
        return self.df[['stoch_k', 'stoch_d']]

    def calculate_adx(self, period=14):
        """Calcula ADX e DI+/DI-"""
        adx = ADXIndicator(
            high=self.df['high'],
            low=self.df['low'],
            close=self.df['close'],
            window=period,
        )
        self.df['adx'] = adx.adx()
        self.df['adx_pos'] = adx.adx_pos()
        self.df['adx_neg'] = adx.adx_neg()
        return self.df[['adx', 'adx_pos', 'adx_neg']]

    def calculate_awesome_oscillator(self, fast=5, slow=34):
        """Calcula Awesome Oscillator (AO)."""
        ao = AwesomeOscillatorIndicator(
            high=self.df['high'],
            low=self.df['low'],
            window1=fast,
            window2=slow,
        )
        self.df['awesome_oscillator'] = ao.awesome_oscillator()
        return self.df['awesome_oscillator']

    def calculate_fractals(self):
        """
        Detecta fractais básicos (5 barras).
        Fractal de alta: máxima local com 2 barras de cada lado menores.
        Fractal de baixa: mínima local com 2 barras de cada lado maiores.
        """
        high = self.df['high']
        low = self.df['low']

        self.df['fractal_high'] = (
            (high > high.shift(1))
            & (high > high.shift(2))
            & (high > high.shift(-1))
            & (high > high.shift(-2))
        )
        self.df['fractal_low'] = (
            (low < low.shift(1))
            & (low < low.shift(2))
            & (low < low.shift(-1))
            & (low < low.shift(-2))
        )

        return self.df[['fractal_high', 'fractal_low']]
    
    def calculate_all_indicators(self, config):
        """Calcula todos os indicadores de uma vez"""
        # RSI
        if 'RSI' in config:
            self.calculate_rsi(config['RSI']['period'])
        
        # MACD
        if 'MACD' in config:
            self.calculate_macd(
                config['MACD']['fast'],
                config['MACD']['slow'],
                config['MACD']['signal']
            )
        
        # Bollinger Bands
        if 'BOLLINGER' in config:
            self.calculate_bollinger_bands(
                config['BOLLINGER']['period'],
                config['BOLLINGER']['std']
            )
        
        # EMAs
        if 'EMA_SHORT' in config:
            self.calculate_ema(config['EMA_SHORT']['period'])
        if 'EMA_LONG' in config:
            self.calculate_ema(config['EMA_LONG']['period'])
        
        # ATR
        if 'ATR' in config:
            self.calculate_atr(config['ATR']['period'])
        
        # Volume MA
        if 'VOLUME' in config:
            self.calculate_volume_ma(config['VOLUME']['ma_period'])

        # Stochastic
        if 'STOCHASTIC' in config:
            self.calculate_stochastic(
                config['STOCHASTIC'].get('k_period', 14),
                config['STOCHASTIC'].get('d_period', 3),
                config['STOCHASTIC'].get('smooth', 3),
            )

        # ADX
        if 'ADX' in config:
            self.calculate_adx(config['ADX'].get('period', 14))

        # Awesome Oscillator
        if 'AO' in config:
            self.calculate_awesome_oscillator(
                config['AO'].get('fast', 5),
                config['AO'].get('slow', 34),
            )

        # Fractals
        if config.get('FRACTALS'):
            self.calculate_fractals()
        
        return self.df
    
    def get_dataframe(self):
        """Retorna o DataFrame com todos os indicadores"""
        return self.df
