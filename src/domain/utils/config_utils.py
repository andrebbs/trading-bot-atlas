"""
Configuration utilities for trading bot.
Functions for environment variable handling and bot configuration.
"""
import os
import re
import logging

logger = logging.getLogger(__name__)


def get_profile_env(base_key: str, bot_profile: str | None = None) -> str | None:
    """
    Busca variável por perfil com fallback para chave global.
    
    Padrão de busca:
    1. {BASE_KEY}_{PROFILE_SUFFIX} (ex: TELEGRAM_BOT_TOKEN_ABBS_FOREX)
    2. {BASE_KEY} (ex: TELEGRAM_BOT_TOKEN)
    
    Args:
        base_key: Chave base da variável de ambiente
        bot_profile: Perfil do bot ou None para usar BOT_PROFILE env var
    
    Returns:
        Valor da variável ou None se não encontrada
    
    Examples:
        >>> os.environ['TELEGRAM_BOT_TOKEN'] = 'default_token'
        >>> os.environ['TELEGRAM_BOT_TOKEN_FOREX'] = 'forex_token'
        >>> get_profile_env('TELEGRAM_BOT_TOKEN', 'forex')
        'forex_token'
        >>> get_profile_env('TELEGRAM_BOT_TOKEN', 'main')
        'default_token'
    """
    if bot_profile is None:
        bot_profile = os.getenv('BOT_PROFILE', 'main').strip().lower() or 'main'
    
    profile_suffix = re.sub(r'[^A-Z0-9]+', '_', bot_profile.upper()).strip('_')
    candidate_keys = []
    
    if profile_suffix:
        candidate_keys.append(f"{base_key}_{profile_suffix}")
    candidate_keys.append(base_key)

    for key in candidate_keys:
        value = os.getenv(key)
        if value:
            return value
    
    return None


def _env_int(name: str, default: int, min_value: int = 1) -> int:
    """
    Lê inteiro de ambiente com fallback e limite mínimo.
    
    Args:
        name: Nome da variável de ambiente
        default: Valor padrão se não encontrada ou inválida
        min_value: Valor mínimo permitido
    
    Returns:
        Valor inteiro >= min_value
    
    Examples:
        >>> os.environ['TEST_VAR'] = '50'
        >>> _env_int('TEST_VAR', 10, 1)
        50
        >>> _env_int('MISSING_VAR', 10, 1)
        10
        >>> os.environ['SMALL_VAR'] = '0'
        >>> _env_int('SMALL_VAR', 10, 5)
        5  # Enforces minimum
    """
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Valor inválido para %s=%r. Usando padrão %s.",
            name, raw, default
        )
        return default
    return max(min_value, value)


def _env_float(name: str, default: float, min_value: float | None = None) -> float:
    """
    Lê float de ambiente com fallback e limite mínimo opcional.
    
    Args:
        name: Nome da variável de ambiente
        default: Valor padrão se não encontrada ou inválida
        min_value: Valor mínimo permitido (opcional)
    
    Returns:
        Valor float
    
    Examples:
        >>> os.environ['TEST_FLOAT'] = '3.14'
        >>> _env_float('TEST_FLOAT', 1.0)
        3.14
        >>> _env_float('MISSING_FLOAT', 2.5)
        2.5
    """
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
        if min_value is not None:
            value = max(min_value, value)
        return value
    except (TypeError, ValueError):
        logger.warning(
            "Valor inválido para %s=%r. Usando padrão %s.",
            name, raw, default
        )
        return default


def _env_flag(raw_value: str | None, default: bool = False) -> bool:
    """
    Converte string de ambiente para booleano.
    
    Valores truthy: '1', 'true', 'yes', 'on', 'enabled'
    Valores falsy: '0', 'false', 'no', 'off', 'disabled', ''
    
    Args:
        raw_value: Valor da variável de ambiente
        default: Valor padrão se None ou vazio
    
    Returns:
        Booleano interpretado
    
    Examples:
        >>> _env_flag('1')
        True
        >>> _env_flag('true')
        True
        >>> _env_flag('0')
        False
        >>> _env_flag('disabled')
        False
        >>> _env_flag(None)
        False
        >>> _env_flag('', default=True)
        True
    """
    if raw_value is None or not raw_value.strip():
        return default
    
    normalized = raw_value.strip().lower()
    truthy = {'1', 'true', 'yes', 'on', 'enabled', 'sim', 's', 'y'}
    
    return normalized in truthy


def _parse_csv_list(raw_value: str | None, defaults: list[str] | None = None) -> list[str]:
    """
    Parseia lista CSV de variável de ambiente.
    
    Args:
        raw_value: String CSV da variável de ambiente
        defaults: Lista padrão se raw_value vazio/None
    
    Returns:
        Lista de strings (stripped, uppercase)
    
    Examples:
        >>> _parse_csv_list('BTC, ETH, SOL')
        ['BTC', 'ETH', 'SOL']
        >>> _parse_csv_list('  btc,eth  ')
        ['BTC', 'ETH']
        >>> _parse_csv_list(None, ['DEFAULT'])
        ['DEFAULT']
    """
    if not raw_value or not raw_value.strip():
        return list(defaults) if defaults else []
    
    items = [item.strip().upper() for item in raw_value.split(',') if item.strip()]
    return items


def get_telegram_bot_token(bot_profile: str | None = None) -> str | None:
    """
    Obtém token do bot Telegram respeitando perfil.
    
    Args:
        bot_profile: Perfil do bot ou None para usar env var
    
    Returns:
        Token do bot ou None se não configurado
    """
    return get_profile_env('TELEGRAM_BOT_TOKEN', bot_profile)


def get_telegram_chat_id(bot_profile: str | None = None) -> str | None:
    """
    Obtém chat ID do Telegram respeitando perfil.
    
    Args:
        bot_profile: Perfil do bot ou None para usar env var
    
    Returns:
        Chat ID ou None se não configurado
    """
    return get_profile_env('TELEGRAM_CHAT_ID', bot_profile)
