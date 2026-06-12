"""
Symbol utilities for trading bot.
Functions for symbol normalization, resolution, and market routing.
"""
import os
from typing import Tuple


# Mapa de proxies para ativos OTC sem feed direto na Binance
FOREX_PROXY_MAP = {
    'EUR/USD': 'EUR/USDT',
    'EURUSD': 'EUR/USDT',
    'GBP/USD': 'GBP/USDT',
    'GBPUSD': 'GBP/USDT',
    'AUD/USD': 'AUD/USDT',
    'AUDUSD': 'AUD/USDT',
    'NZD/USD': 'NZD/USDT',
    'NZDUSD': 'NZD/USDT',
    'USD/CAD': 'USDC/USDT',  # Proxy aproximado
    'USDCAD': 'USDC/USDT',
    'USD/CHF': None,  # Sem proxy confiável
    'USDCHF': None,
    'USD/JPY': None,  # Sem proxy confiável
    'USDJPY': None,
    'XAU/USD': 'PAXG/USDT',  # Gold via PAX Gold
    'XAUUSD': 'PAXG/USDT',
    'XAG/USD': None,  # Silver - sem proxy
    'XAGUSD': None,
}


def _normalize_crypto_symbol(asset: str) -> str:
    """
    Normaliza símbolo crypto para formato padrão BASE/USDT.
    
    Args:
        asset: String do ativo ('BTC', 'BTCUSDT', 'BTC/USDT', 'bitcoin')
    
    Returns:
        Símbolo normalizado no formato 'BASE/USDT'
    
    Examples:
        >>> _normalize_crypto_symbol('BTC')
        'BTC/USDT'
        >>> _normalize_crypto_symbol('BTCUSDT')
        'BTC/USDT'
        >>> _normalize_crypto_symbol('ethereum')
        'ETH/USDT'
    """
    raw = (asset or '').upper().strip()
    
    # Aliases comuns
    alias_map = {
        'BITCOIN': 'BTC',
        'ETHEREUM': 'ETH',
        'SOLANA': 'SOL',
        'CARDANO': 'ADA',
        'RIPPLE': 'XRP',
        'POLKADOT': 'DOT',
        'DOGECOIN': 'DOGE',
        'POLYGON': 'MATIC',
        'CHAINLINK': 'LINK',
        'LITECOIN': 'LTC',
        'BINANCE': 'BNB',
        'BINANCECOIN': 'BNB',
    }
    
    if raw in alias_map:
        raw = alias_map[raw]
    
    # Já está no formato BASE/USDT
    if '/' in raw:
        return raw
    
    # Remove sufixo USDT se presente
    if raw.endswith('USDT'):
        base = raw[:-4]
        return f"{base}/USDT"
    
    # Assume que é apenas a base
    return f"{raw}/USDT"


def _normalize_otc_symbol(symbol: str) -> str:
    """
    Normaliza símbolo OTC para formato BASE/QUOTE sem sufixo OTC.
    
    Args:
        symbol: String do símbolo OTC ('EUR/USD OTC', 'EURUSD_OTC')
    
    Returns:
        Símbolo normalizado sem sufixo OTC
    
    Examples:
        >>> _normalize_otc_symbol('EUR/USD OTC')
        'EUR/USD'
        >>> _normalize_otc_symbol('EURUSD_OTC')
        'EURUSD'
    """
    raw = (symbol or '').upper().replace(' OTC', '').replace('OTC', '').strip()
    
    if '/' in raw:
        base, quote = raw.split('/', 1)
        return f"{base.strip()}/{quote.strip()}"
    
    return raw


def _is_price_parity_compatible(requested_symbol: str, market_symbol: str) -> bool:
    """
    Indica se o proxy pode representar preço absoluto do ativo solicitado.
    
    Usado para validar se podemos mostrar o preço do market_symbol
    como representativo do requested_symbol (OTC).
    
    Args:
        requested_symbol: Símbolo solicitado (OTC)
        market_symbol: Símbolo de mercado disponível (Binance)
    
    Returns:
        True se há paridade de preço aceitável
    
    Examples:
        >>> _is_price_parity_compatible('EUR/USD', 'EUR/USDT')
        True
        >>> _is_price_parity_compatible('XAU/USD', 'PAXG/USDT')
        True
        >>> _is_price_parity_compatible('GBP/JPY', 'GBP/USDT')
        False
    """
    req = _normalize_otc_symbol(requested_symbol)
    mkt = (market_symbol or '').upper().strip()

    # Mesmo símbolo (ou similar) é seguro para exibir preço
    if req == mkt or req.replace('/', '') == mkt.replace('/', ''):
        return True

    # Casos especiais conhecidos com boa paridade aproximada
    special_pairs = {
        ('XAU/USD', 'PAXG/USDT'),  # Gold
    }
    if (req, mkt) in special_pairs:
        return True

    # Para FX OTC, só tratamos como comparável quando é XXX/USD via XXX/USDT
    if '/' in req and '/' in mkt:
        req_base, req_quote = req.split('/', 1)
        mkt_base, mkt_quote = mkt.split('/', 1)
        if req_base == mkt_base and req_quote in {'USD', 'USDT'} and mkt_quote == 'USDT':
            return True

    return False


def resolve_market_symbol(symbol: str) -> Tuple[str | None, str | None]:
    """
    Resolve símbolo solicitado para um símbolo de mercado disponível.
    
    Mapeia símbolos OTC/Forex para proxies na Binance quando possível.
    
    Args:
        symbol: Símbolo solicitado pelo usuário
    
    Returns:
        Tupla (market_symbol, message) onde:
        - market_symbol: Símbolo disponível na exchange ou None
        - message: Mensagem de aviso/proxy ou None
    
    Examples:
        >>> resolve_market_symbol('BTC')
        ('BTC/USDT', None)
        >>> resolve_market_symbol('EUR/USD')
        ('EUR/USDT', 'proxy: EUR/USDT')
        >>> resolve_market_symbol('SPX500')
        (None, 'sem feed Binance para S&P 500 (use MT5/Fundscap ou TradingView como fonte)')
    """
    if not symbol:
        return None, None

    raw = symbol.strip().upper()
    
    # Verifica mapa de proxies forex/OTC
    mapped = FOREX_PROXY_MAP.get(raw)
    if mapped:
        return mapped, f"proxy: {mapped}"

    # Símbolos nativos já compatíveis com Binance
    if '/' in raw and raw.endswith('USDT'):
        return raw, None

    # Bloqueios conhecidos sem feed
    if raw.startswith('HK'):
        return None, "sem feed Binance para HK (use MT5/TradingView como fonte)"

    if raw in {'SP500', 'US500', 'SPX500', 'SPX', 'S&P500', 'S&P 500'}:
        return None, "sem feed Binance para S&P 500 (use MT5/Fundscap ou TradingView como fonte)"

    # Se não houver mapeamento explícito, tenta usar como veio
    return raw, None


def _normalize_external_direction(raw_direction: str) -> str | None:
    """
    Normaliza direção de sinais externos para padrão interno.
    
    Args:
        raw_direction: Direção do sinal externo ('buy', 'sell', 'CALL', 'PUT', etc.)
    
    Returns:
        'buy', 'sell' ou None se inválido
    
    Examples:
        >>> _normalize_external_direction('CALL')
        'buy'
        >>> _normalize_external_direction('PUT')
        'sell'
        >>> _normalize_external_direction('compra')
        'buy'
    """
    if not raw_direction:
        return None
    
    direction_lower = raw_direction.strip().lower()
    
    # Mapeamento de variações comuns
    buy_variations = {'buy', 'compra', 'call', 'long', 'alta', 'acima'}
    sell_variations = {'sell', 'venda', 'put', 'short', 'baixa', 'abaixo'}
    
    if direction_lower in buy_variations:
        return 'buy'
    if direction_lower in sell_variations:
        return 'sell'
    
    return None


def _external_asset_group(asset: str) -> str:
    """
    Classifica ativo externo em grupo para validação de allowlist.
    
    Args:
        asset: String do ativo
    
    Returns:
        Grupo do ativo ('crypto', 'forex', 'indices', 'commodities', 'unknown')
    
    Examples:
        >>> _external_asset_group('BTCUSDT')
        'crypto'
        >>> _external_asset_group('EUR/USD')
        'forex'
        >>> _external_asset_group('SPX500')
        'indices'
        >>> _external_asset_group('XAU/USD')
        'commodities'
    """
    if not asset:
        return 'unknown'
    
    raw = asset.upper().strip()
    
    # Cripto: termina com USDT ou pares cripto conhecidos
    crypto_bases = {'BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOT', 'DOGE', 'MATIC', 'LINK', 'LTC', 'BNB'}
    if any(raw.startswith(base) for base in crypto_bases) or raw.endswith('USDT'):
        return 'crypto'
    
    # Forex: pares de moedas comuns
    forex_bases = {'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY'}
    if '/' in raw:
        parts = raw.split('/')
        if len(parts) == 2 and all(p in forex_bases for p in parts):
            return 'forex'
    
    # Índices: SPX, US500, etc
    if any(idx in raw for idx in ['SPX', 'SP500', 'US500', 'NAS', 'DOW', 'DAX', 'FTSE']):
        return 'indices'
    
    # Commodities: XAU (gold), XAG (silver), OIL, etc
    if any(com in raw for com in ['XAU', 'XAG', 'GOLD', 'SILVER', 'OIL', 'BRENT']):
        return 'commodities'
    
    return 'unknown'


def get_monitor_signal_scope_key(symbol: str, timeframe: str) -> str:
    """
    Gera chave única para cachear sinais por símbolo e timeframe.
    
    Args:
        symbol: String do símbolo
        timeframe: String do timeframe
    
    Returns:
        Chave única para o par símbolo/timeframe
    
    Examples:
        >>> get_monitor_signal_scope_key('BTC/USDT', '5m')
        'BTC/USDT:5m'
    """
    return f"{symbol}:{timeframe}"


def _parse_external_allowlist(env_var_value: str | None, defaults: list[str]) -> list[str]:
    """
    Parseia lista de ativos permitidos de variável de ambiente.
    
    Args:
        env_var_value: Valor da variável de ambiente (CSV)
        defaults: Lista padrão se env var não definida
    
    Returns:
        Lista de símbolos permitidos (uppercase, stripped)
    
    Examples:
        >>> _parse_external_allowlist('BTC,ETH,SOL', [])
        ['BTC', 'ETH', 'SOL']
        >>> _parse_external_allowlist(None, ['BTC'])
        ['BTC']
    """
    if not env_var_value or not env_var_value.strip():
        return list(defaults)
    
    raw_list = env_var_value.split(',')
    normalized = [s.strip().upper() for s in raw_list if s.strip()]
    
    return normalized if normalized else list(defaults)
