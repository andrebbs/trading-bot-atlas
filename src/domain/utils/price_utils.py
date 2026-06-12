"""
Price utilities for trading bot.
Functions for price resolution, formatting, and calculations.
"""
import pandas as pd


def _to_float(value: str, default: float) -> float:
    """
    Converte string para float com fallback seguro.
    
    Args:
        value: String a converter
        default: Valor padrão se conversão falhar
    
    Returns:
        Float convertido ou valor padrão
    
    Examples:
        >>> _to_float('123.45', 0.0)
        123.45
        >>> _to_float('invalid', 10.0)
        10.0
    """
    try:
        return float(value)
    except (ValueError, TypeError, AttributeError):
        return default


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Calcula razão evitando divisão por zero.
    
    Args:
        numerator: Numerador
        denominator: Denominador
        default: Valor padrão se denominador for zero
    
    Returns:
        Razão ou valor padrão
    
    Examples:
        >>> _safe_ratio(10, 2)
        5.0
        >>> _safe_ratio(10, 0)
        0.0
        >>> _safe_ratio(10, 0, default=1.0)
        1.0
    """
    try:
        if denominator in (0, None) or pd.isna(denominator):
            return default
        return float(numerator) / float(denominator)
    except Exception:
        return default


def format_price(price: float, decimals: int = 2) -> str:
    """
    Formata preço com número adequado de decimais.
    
    Args:
        price: Valor do preço
        decimals: Número de casas decimais (padrão: 2)
    
    Returns:
        String formatada do preço
    
    Examples:
        >>> format_price(1234.5678)
        '1234.57'
        >>> format_price(0.00012345, 8)
        '0.00012345'
    """
    if price == 0:
        return '0.00'
    
    # Para preços muito pequenos (< 0.01), usa mais decimais
    if abs(price) < 0.01:
        return f"{price:.8f}".rstrip('0').rstrip('.')
    
    # Para preços normais, usa decimals especificado
    return f"{price:.{decimals}f}"


def calculate_risk_reward(
    entry: float,
    target: float,
    stop: float,
    direction: str
) -> float | None:
    """
    Calcula risk/reward ratio.
    
    Args:
        entry: Preço de entrada
        target: Preço alvo
        stop: Preço de stop
        direction: 'buy' ou 'sell'
    
    Returns:
        Razão risk/reward ou None se inválido
    
    Examples:
        >>> calculate_risk_reward(100, 110, 95, 'buy')
        2.0  # Reward: 10, Risk: 5, RR: 2.0
    """
    if direction == 'buy':
        reward = abs(target - entry)
        risk = abs(entry - stop)
    else:  # sell
        reward = abs(entry - target)
        risk = abs(stop - entry)
    
    if risk == 0:
        return None
    
    return reward / risk
