"""Engine for OTC operations (broker-specific synthetic feed)."""
"""Engine for OTC operations (broker-specific synthetic feed).

This module centralises all OTC-specific logic so that ForexEngine,
CryptoBinaryEngine and OTCEngine form three fully independent projects
within the same codebase.
"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .base import BaseEngine, EngineContext, EngineSignal

# ─── Proxy map: OTC symbol names → Binance tradeable counterparts ─────────────
OTC_PROXY_MAP: dict = {
    'EUR/USD OTC': 'EUR/USDT',
    'EURUSD OTC': 'EUR/USDT',
    'EUR/USD': 'EUR/USDT',
    'EURUSD': 'EUR/USDT',
    'EUR/GBP OTC': 'EUR/USDT',
    'EURGBP OTC': 'EUR/USDT',
    'EUR/GBP': 'EUR/USDT',
    'EURGBP': 'EUR/USDT',
    'EUR/CHF OTC': 'EUR/USDT',
    'EURCHF OTC': 'EUR/USDT',
    'EUR/CHF': 'EUR/USDT',
    'EURCHF': 'EUR/USDT',
    'EUR/HUF OTC': 'EUR/USDT',
    'EURHUF OTC': 'EUR/USDT',
    'EUR/HUF': 'EUR/USDT',
    'EURHUF': 'EUR/USDT',
    'EUR/RUB OTC': 'EUR/USDT',
    'EURRUB OTC': 'EUR/USDT',
    'EUR/RUB': 'EUR/USDT',
    'EURRUB': 'EUR/USDT',
    'EUR/NZD OTC': 'EUR/USDT',
    'EURNZD OTC': 'EUR/USDT',
    'EUR/NZD': 'EUR/USDT',
    'EURNZD': 'EUR/USDT',
    'EUR/TRY OTC': 'EUR/USDT',
    'EURTRY OTC': 'EUR/USDT',
    'EUR/TRY': 'EUR/USDT',
    'EURTRY': 'EUR/USDT',
    'EUR/JPY OTC': 'EUR/USDT',
    'EURJPY OTC': 'EUR/USDT',
    'EUR/JPY': 'EUR/USDT',
    'EURJPY': 'EUR/USDT',
    'GBP/USD OTC': 'GBP/USDT',
    'GBPUSD OTC': 'GBP/USDT',
    'GBP/USD': 'GBP/USDT',
    'GBPUSD': 'GBP/USDT',
    'GBP/JPY OTC': 'GBP/USDT',
    'GBPJPY OTC': 'GBP/USDT',
    'GBP/JPY': 'GBP/USDT',
    'GBPJPY': 'GBP/USDT',
    'AUD/USD OTC': 'AUD/USDT',
    'AUDUSD OTC': 'AUD/USDT',
    'AUD/USD': 'AUD/USDT',
    'AUDUSD': 'AUD/USDT',
    'AUD/JPY OTC': 'AUD/USDT',
    'AUDJPY OTC': 'AUD/USDT',
    'AUD/JPY': 'AUD/USDT',
    'AUDJPY': 'AUD/USDT',
    'AUD/CAD OTC': 'AUD/USDT',
    'AUDCAD OTC': 'AUD/USDT',
    'AUD/CAD': 'AUD/USDT',
    'AUDCAD': 'AUD/USDT',
    'AUD/NZD OTC': 'AUD/USDT',
    'AUDNZD OTC': 'AUD/USDT',
    'AUD/NZD': 'AUD/USDT',
    'AUDNZD': 'AUD/USDT',
    'AUD/CHF OTC': 'AUD/USDT',
    'AUDCHF OTC': 'AUD/USDT',
    'AUD/CHF': 'AUD/USDT',
    'AUDCHF': 'AUD/USDT',
    'NZD/USD OTC': 'FDUSD/USDT',
    'USD/JPY OTC': 'USDC/USDT',
    'USDJPY OTC': 'USDC/USDT',
    'USD/JPY': 'USDC/USDT',
    'USDJPY': 'USDC/USDT',
    'USD/CAD OTC': 'BNB/USDT',
    'CAD/JPY OTC': None,
    'CADJPY OTC': None,
    'CAD/JPY': None,
    'CADJPY': None,
    'XAU/USD': 'PAXG/USDT',
    'XAUUSD': 'PAXG/USDT',
    'HK50 OTC': None,
    'HK50': None,
}

# ─── Strategy catalogue ───────────────────────────────────────────────────────
VALID_STRATEGIES = frozenset({
    'ema_adx_ao_trend_filter',
    'macd_profitunity',
    'fidelity_envelopes_sma',
    'auto',
})

STRATEGY_DISPLAY = {
    'ema_adx_ao_trend_filter': 'EMA21 + ADX + AO (tendência)',
    'fidelity_envelopes_sma': 'Envelopes + SMA (lateral)',
    'macd_profitunity': 'MACD + AO + Fractais',
}

STRATEGY_EXPIRY_HINT = {
    'ema_adx_ao_trend_filter': '1-2 candles',
    'fidelity_envelopes_sma': '10m-15m',
    'macd_profitunity': 'up to 5 candles',
}

# ─── Live-mode defaults ───────────────────────────────────────────────────────
DEFAULT_STRATEGY = 'ema_adx_ao_trend_filter'
# Mais permissivo que o backtest (25) — pares sintéticos OTC têm ADX naturalmente baixo
MIN_ADX = 12.0
DEFAULT_SESSION = 'all'
TOP_5_SYMBOLS = [
    'AUD/CAD OTC',
    'AUD/USD OTC',
    'AUD/NZD OTC',
    'AUD/CHF OTC',
    'EUR/USD OTC',
]

TOP_10_SYMBOLS = [
    'AUD/CAD OTC',
    'AUD/USD OTC',
    'AUD/NZD OTC',
    'AUD/CHF OTC',
    'EUR/USD OTC',
    'EUR/GBP OTC',
    'EUR/CHF OTC',
    'EUR/HUF OTC',
    'EUR/RUB OTC',
    'EUR/NZD OTC',
]

DEFAULT_MONITORED_SYMBOLS = list(TOP_10_SYMBOLS)

# Indicadores unificados para análise OTC ao vivo (cobre as 3 estratégias)
INDICATOR_CONFIG = {
    'EMA_LONG': {'period': 21},            # ema_adx_ao_trend_filter
    'EMA_SHORT': {'period': 6},            # fidelity_envelopes_sma
    'ADX': {'period': 14},                 # todos (detecta regime)
    'AO': {'fast': 5, 'slow': 34},         # ema_adx_ao + macd_profitunity
    'BOLLINGER': {'period': 14, 'std': 2}, # fidelity_envelopes_sma
    'MACD': {'fast': 34, 'slow': 89, 'signal': 9},  # macd_profitunity
    'FRACTALS': True,                      # macd_profitunity
}

# Janela de pré-alerta por timeframe: (max_s, min_s) antes do fechamento do candle
PRE_ALERT_WINDOW = {
    '1m':  (55, 8),
    '5m':  (60, 10),
    '15m': (60, 10),
    '1h':  (60, 10),
    '4h':  (60, 10),
    '1d':  (60, 10),
}


class OTCEngine(BaseEngine):
    """Engine for OTC (PocketOption) live signal operations.

    Mirrors the design pattern of ForexEngine and CryptoBinaryEngine,
    providing a self-contained module for the OTC 'project'.
    """

    market_type = "otc"

    def evaluate(self, context: EngineContext) -> EngineSignal:
        signal = context.metadata.get("signal", {})
        direction = signal.get("type", "neutral")

        expiry_seconds = int(context.metadata.get("expiry_seconds", 120))
        payout = float(context.metadata.get("payout", 0.0))

        return EngineSignal(
            market_type=self.market_type,
            symbol=context.symbol,
            timeframe=context.timeframe,
            direction=direction,
            probability=float(signal.get("probability", 0.0)),
            score=float(signal.get("score", 0.0)),
            edge=float(signal.get("edge", 0.0)),
            consensus=int(signal.get("consensus", 0)),
            reference_price=signal.get("reference_price"),
            expires_at=datetime.utcnow() + timedelta(seconds=expiry_seconds),
            reason="otc engine decision",
            extra={"payout": payout},
        )

    @staticmethod
    def resolve_proxy(symbol: str):
        """Return the Binance proxy symbol for an OTC pair, or None."""
        return OTC_PROXY_MAP.get(symbol.strip().upper())

    @staticmethod
    def live_signal_series(
        df: pd.DataFrame,
        strategy_id: str,
        min_adx: float = MIN_ADX,
    ) -> pd.Series:
        """Generate live OTC signal series from a closed-candle DataFrame.

        ema_adx_ao_trend_filter: single-bar AO check (more responsive than the
        2-bar confirmation used in back-tests).
        Other strategies delegate to main._otc_signal_series unchanged.
        """
        from main import _otc_signal_series  # lazy import – avoids circular dep

        if strategy_id == 'ema_adx_ao_trend_filter':
            required = ('ema_21', 'adx', 'awesome_oscillator')
            if not all(c in df.columns for c in required):
                return pd.Series(0, index=df.index)
            long_cond = (
                (df['close'] > df['ema_21'])
                & (df['adx'] > min_adx)
                & (df['awesome_oscillator'] > 0)
            )
            short_cond = (
                (df['close'] < df['ema_21'])
                & (df['adx'] > min_adx)
                & (df['awesome_oscillator'] < 0)
            )
            return pd.Series(
                np.where(long_cond, 1, np.where(short_cond, -1, 0)),
                index=df.index,
            )

        return _otc_signal_series(df, strategy_id)

    @classmethod
    def regime_auto_signal(
        cls,
        df: pd.DataFrame,
        min_adx: float = MIN_ADX,
    ) -> tuple:
        """Auto-select OTC strategy based on current market regime.

        ADX >= min_adx → trending market → ema_adx_ao_trend_filter
        ADX <  min_adx → ranging market → fidelity_envelopes_sma

        Returns (strategy_id: str, signal: int, indicators: dict).
        """
        from main import _otc_signal_series

        adx_val = float(df['adx'].iloc[-1]) if 'adx' in df.columns else 0.0
        ao_val = (
            float(df['awesome_oscillator'].iloc[-1])
            if 'awesome_oscillator' in df.columns
            else 0.0
        )

        if adx_val >= min_adx:
            strategy_id = 'ema_adx_ao_trend_filter'
            sig_series = cls.live_signal_series(df, strategy_id, min_adx=min_adx)
            signal = int(sig_series.iloc[-1])
            indicators = {
                'ema_21': float(df['ema_21'].iloc[-1]) if 'ema_21' in df.columns else None,
                'adx': adx_val,
                'ao': ao_val,
            }
        else:
            strategy_id = 'fidelity_envelopes_sma'
            sig_series = _otc_signal_series(df, strategy_id)
            signal = int(sig_series.iloc[-1])
            indicators = {
                'bb_upper': float(df['bb_upper'].iloc[-1]) if 'bb_upper' in df.columns else None,
                'bb_lower': float(df['bb_lower'].iloc[-1]) if 'bb_lower' in df.columns else None,
                'ema_6': float(df['ema_6'].iloc[-1]) if 'ema_6' in df.columns else None,
                'adx': adx_val,
            }

        return strategy_id, signal, indicators

    @staticmethod
    def format_indicator_line(strategy_id: str, indicators: dict, signal: int) -> str:
        """Format indicator values into a human-readable Telegram message line."""
        lines = []
        adx = indicators.get('adx', 0.0)

        if strategy_id == 'ema_adx_ao_trend_filter':
            ema_val = indicators.get('ema_21')
            ao_val = indicators.get('ao', 0.0)
            trend_icon = (
                '✅' if (signal == 1 and ao_val > 0) or (signal == -1 and ao_val < 0)
                else '⚠️'
            )
            if ema_val:
                lines.append(f"📉 EMA21: {ema_val:.5f}")
            lines.append(
                f"📊 ADX: {adx:.1f} "
                f"({'tendência forte' if adx >= 25 else 'tendência moderada'})"
            )
            lines.append(f"🌊 AO: {ao_val:+.6f} {trend_icon}")
        elif strategy_id == 'fidelity_envelopes_sma':
            bb_upper = indicators.get('bb_upper')
            bb_lower = indicators.get('bb_lower')
            ema6 = indicators.get('ema_6')
            lines.append(f"📊 ADX: {adx:.1f} (mercado lateral)")
            if bb_upper and bb_lower:
                lines.append(f"📈 BB: {bb_lower:.5f} ─ {bb_upper:.5f}")
            if ema6:
                lines.append(f"📉 EMA6: {ema6:.5f}")

        return '\n'.join(lines)
