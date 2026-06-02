"""
Time utilities for trading bot.
Pure functions for timeframe conversions and datetime manipulations.
"""
from datetime import datetime, timedelta
from typing import Tuple
import pandas as pd
import numpy as np


def timeframe_to_minutes(timeframe: str) -> int:
    """
    Converte timeframe para minutos.
    
    Args:
        timeframe: String do timeframe ('1m', '5m', '15m', '30m', '1h', '4h', '1d')
    
    Returns:
        Número de minutos correspondente ao timeframe
    
    Examples:
        >>> timeframe_to_minutes('5m')
        5
        >>> timeframe_to_minutes('1h')
        60
    """
    mapping = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '4h': 240,
        '1d': 1440
    }
    return mapping.get(timeframe, 1)


def get_next_candle_start(now: datetime, timeframe: str) -> datetime:
    """
    Retorna o início do próximo candle para o timeframe.
    
    Args:
        now: Datetime atual
        timeframe: String do timeframe
    
    Returns:
        Datetime do início do próximo candle
    
    Examples:
        >>> now = datetime(2026, 6, 1, 14, 23, 45)
        >>> get_next_candle_start(now, '5m')
        datetime(2026, 6, 1, 14, 25, 0)
        >>> get_next_candle_start(now, '1h')
        datetime(2026, 6, 1, 15, 0, 0)
    """
    tf_minutes = timeframe_to_minutes(timeframe)

    # Para timeframes diários, próximo candle é 00:00 do próximo dia
    if tf_minutes >= 1440:
        next_day = now + timedelta(days=1)
        return next_day.replace(hour=0, minute=0, second=0, microsecond=0)

    # Para timeframes intraday, calcular próximo bloco
    base = now.replace(second=0, microsecond=0)
    minute_block = (base.minute // tf_minutes) * tf_minutes
    current_block_start = base.replace(minute=minute_block)
    return current_block_start + timedelta(minutes=tf_minutes)


def get_pre_alert_window_seconds(timeframe: str, default_max: int = 180, default_min: int = 30) -> Tuple[int, int]:
    """
    Retorna janela de pré-alerta (max_s, min_s) por timeframe.
    
    Para timeframes >= 5m, usa janela reduzida para sinal mais próximo da abertura.
    
    Args:
        timeframe: String do timeframe
        default_max: Segundos máximos de antecedência (para timeframes curtos)
        default_min: Segundos mínimos de antecedência (para timeframes curtos)
    
    Returns:
        Tupla (max_seconds, min_seconds)
    
    Examples:
        >>> get_pre_alert_window_seconds('5m')
        (45, 10)
        >>> get_pre_alert_window_seconds('1m')
        (180, 30)
    """
    tf_minutes = timeframe_to_minutes(timeframe)
    if tf_minutes >= 5:
        # Janela reduzida para sinal mais próximo da abertura do candle
        return 45, 10
    return default_max, default_min


def get_higher_timeframe(timeframe: str) -> str:
    """
    Retorna timeframe superior para análise de tendência primária.
    
    Args:
        timeframe: String do timeframe atual
    
    Returns:
        String do timeframe superior
    
    Examples:
        >>> get_higher_timeframe('1m')
        '5m'
        >>> get_higher_timeframe('15m')
        '30m'
        >>> get_higher_timeframe('4h')
        '1d'
    """
    tf_map = {
        '1m': '5m',
        '3m': '15m',
        '5m': '15m',
        '15m': '30m',
        '30m': '1h',
        '1h': '4h',
        '4h': '1d',
    }
    return tf_map.get(timeframe, '1h')


def parse_monitor_duration_to_minutes(raw: str) -> int | None:
    """
    Converte argumento de duração para minutos (ex: 60, 60m, 1h).
    
    Args:
        raw: String com a duração ('60', '60m', '1h')
    
    Returns:
        Número de minutos ou None se inválido
    
    Examples:
        >>> parse_monitor_duration_to_minutes('60')
        60
        >>> parse_monitor_duration_to_minutes('1h')
        60
        >>> parse_monitor_duration_to_minutes('30m')
        30
    """
    value = (raw or '').strip().lower()
    if not value:
        return None

    try:
        if value.endswith('h'):
            return int(value[:-1]) * 60
        if value.endswith('m'):
            return int(value[:-1])
        return int(value)
    except ValueError:
        return None


def _to_naive_utc(dt_value) -> datetime | None:
    """
    Normaliza datetime para UTC sem timezone para comparações simples.
    
    Aceita:
    - Timestamps numéricos (epoch em segundos ou milissegundos)
    - pd.Timestamp (com ou sem timezone)
    - datetime objects
    
    Args:
        dt_value: Valor de datetime em diversos formatos
    
    Returns:
        datetime UTC naive ou None se conversão falhar
    """
    if dt_value is None:
        return None
    
    try:
        # Alguns feeds retornam epoch numérico; inferimos segundos/ms explicitamente
        if isinstance(dt_value, (int, float, np.integer, np.floating)):
            raw = float(dt_value)
            if raw > 1e12:  # epoch em milissegundos
                return datetime.utcfromtimestamp(raw / 1000.0)
            if raw > 1e9:   # epoch em segundos
                return datetime.utcfromtimestamp(raw)

        ts = pd.Timestamp(dt_value)
        if ts.tzinfo is not None:
            ts = ts.tz_convert('UTC').tz_localize(None)
        return ts.to_pydatetime()
    except Exception:
        return None


def _extract_ticker_timestamp(ticker: dict) -> datetime | None:
    """
    Extrai timestamp do ticker CCXT em UTC (naive), quando disponível.
    
    Args:
        ticker: Dicionário do ticker CCXT
    
    Returns:
        datetime UTC naive ou None se não disponível
    """
    if not ticker:
        return None

    raw_ts = ticker.get('timestamp')
    if raw_ts is not None:
        try:
            # CCXT usa milissegundos
            return datetime.utcfromtimestamp(float(raw_ts) / 1000.0)
        except Exception:
            pass

    raw_dt = ticker.get('datetime')
    return _to_naive_utc(raw_dt)


def direction_cooldown_elapsed(
    last_alert_time: datetime | None,
    now: datetime,
    timeframe: str,
    cooldown_candles: int = 2
) -> bool:
    """
    Verifica se cooldown de direção já passou.
    
    Permite repetir sinal na mesma direção após cooldown de candles.
    
    Args:
        last_alert_time: Datetime do último alerta nesta direção ou None
        now: Datetime atual
        timeframe: String do timeframe
        cooldown_candles: Número de candles de cooldown
    
    Returns:
        True se cooldown passou ou não há último alerta
    
    Examples:
        >>> last = datetime(2026, 6, 1, 14, 0, 0)
        >>> now = datetime(2026, 6, 1, 14, 11, 0)
        >>> direction_cooldown_elapsed(last, now, '5m', 2)
        True  # Passaram 2 candles de 5m
    """
    if last_alert_time is None:
        return True

    cooldown_minutes = timeframe_to_minutes(timeframe) * cooldown_candles
    return (now - last_alert_time) >= timedelta(minutes=cooldown_minutes)
