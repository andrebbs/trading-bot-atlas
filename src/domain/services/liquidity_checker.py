"""
Liquidity checker service for trading bot.
Validates trading sessions and asset liquidity based on tier classification.
"""
from datetime import datetime, timezone
from typing import Dict, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE TIERS DE LIQUIDEZ CRIPTO (ATLAS v1.1 - Jun 2026)
# ═══════════════════════════════════════════════════════════════════════════════
# Resolve problema de dojis em horários de baixa liquidez em alts (ADA, LTC, DOGE).
# 
# TIER 1 (Major - BTC/ETH):
#   - Liquidez profunda 24/7, opera qualquer horário
#   - Score ≥ 55%, ADX ≥ 24
#
# TIER 2 (Large Caps - SOL/XRP/BNB):
#   - Liquidez condicional, requer sessão ativa (Londres 7-16h ou NY 12-21h UTC)
#   - Bloqueado em finais de semana
#   - Score ≥ 55%, ADX ≥ 26
#
# TIER 3 (Alt Coins - ADA/DOGE/LTC/LINK):
#   - Alta volatilidade, APENAS overlap Londres+NY (12-16h UTC)
#   - Bloqueio TOTAL em finais de semana e madrugada asiática
#   - Score ≥ 60%, ADX ≥ 30
# ═══════════════════════════════════════════════════════════════════════════════

CRYPTO_TIER1_SYMBOLS = {'BTC', 'ETH'}  # Major - 24/7
CRYPTO_TIER2_SYMBOLS = {'SOL', 'XRP', 'BNB'}  # Large Caps - Sessão ativa
CRYPTO_TIER3_SYMBOLS = {'ADA', 'DOGE', 'LTC', 'LINK', 'DOT', 'MATIC'}  # Alts - Overlap apenas

CRYPTO_ALIAS_MAP = {
    'BITCOIN': 'BTC',
    'ETHEREUM': 'ETH',
    'DOGECOIN': 'DOGE',
    'LITECOIN': 'LTC',
    'CARDANO': 'ADA',
    'SOLANA': 'SOL',
    'RIPPLE': 'XRP',
    'BINANCECOIN': 'BNB',
    'POLKADOT': 'DOT',
    'POLYGON': 'MATIC',
    'CHAINLINK': 'LINK',
}


def _normalize_crypto_symbol(asset: str) -> str:
    """
    Normaliza símbolo cripto para base (ex: BTC/USDT → BTC).
    
    Args:
        asset: String do ativo ('BTC/USDT', 'BITCOIN', 'btc')
    
    Returns:
        Símbolo base normalizado ('BTC', 'ETH', etc.)
    
    Examples:
        >>> _normalize_crypto_symbol('BTC/USDT')
        'BTC'
        >>> _normalize_crypto_symbol('BITCOIN')
        'BTC'
    """
    raw = (asset or '').strip().upper().replace('-', '/').replace(' ', '')
    if '/' in raw:
        raw = raw.split('/', 1)[0]
    return CRYPTO_ALIAS_MAP.get(raw, raw)


def get_crypto_signal_profile(asset: str) -> Dict[str, any]:
    """
    Retorna perfil de sinal baseado no tier de liquidez do ativo.
    
    Perfis por tier:
    - Tier 1 (BTC/ETH): 24/7, score 55%, ADX 24
    - Tier 2 (SOL/XRP/BNB): Sessão ativa, score 55%, ADX 26
    - Tier 3 (ADA/DOGE/LTC): Overlap only, score 60%, ADX 30
    
    Args:
        asset: String do ativo
    
    Returns:
        Dict com configurações do tier:
        - tier: 1, 2 ou 3
        - tier_name: Nome do tier
        - min_score: Score mínimo (0.55-0.60)
        - min_adx: ADX mínimo (24-30)
        - liquidity_check: Se requer validação de horário
        - min_session_level: 'any' ou 'overlap'
    
    Examples:
        >>> get_crypto_signal_profile('BTC')
        {'tier': 1, 'tier_name': 'Major', 'min_score': 0.55, ...}
        >>> get_crypto_signal_profile('ADA')
        {'tier': 3, 'tier_name': 'Alt Coin', 'min_score': 0.60, ...}
    """
    symbol = _normalize_crypto_symbol(asset)
    
    # TIER 1: BTC/ETH - Majors com liquidez 24/7
    if symbol in CRYPTO_TIER1_SYMBOLS:
        return {
            'tier': 1,
            'tier_name': 'Major',
            'min_score': 0.55,           # Score 55%
            'min_adx': 24.0,
            'buy_rsi_block': 70.0,
            'sell_rsi_block': 30.0,
            'require_mtf_for_all': False,
            'min_score_without_mtf': 5,
            'liquidity_check': False,    # Opera 24/7
        }
    
    # TIER 2: SOL/XRP/BNB - Large Caps com liquidez condicional
    elif symbol in CRYPTO_TIER2_SYMBOLS:
        return {
            'tier': 2,
            'tier_name': 'Large Cap',
            'min_score': 0.55,           # Score 55%
            'min_adx': 26.0,             # ADX mais alto que Tier 1
            'buy_rsi_block': 68.0,
            'sell_rsi_block': 32.0,
            'require_mtf_for_all': False,
            'min_score_without_mtf': 5,
            'liquidity_check': True,     # Requer sessão ativa
            'min_session_level': 'any',  # Londres OU NY (não precisa overlap)
        }
    
    # TIER 3: ADA/DOGE/LTC - Alts com alta volatilidade
    elif symbol in CRYPTO_TIER3_SYMBOLS:
        return {
            'tier': 3,
            'tier_name': 'Alt Coin',
            'min_score': 0.60,           # Score 60% (mais rigoroso)
            'min_adx': 30.0,             # ADX 30+ (tendência forte obrigatória)
            'buy_rsi_block': 64.0,
            'sell_rsi_block': 36.0,
            'require_mtf_for_all': True, # Confirmação MTF obrigatória
            'min_score_without_mtf': 7,  # Pontuação alta sem MTF
            'liquidity_check': True,     # Requer sessão ativa
            'min_session_level': 'overlap',  # APENAS overlap Londres+NY (12-16h UTC)
        }
    
    # Default: trata como Tier 3 (mais conservador)
    else:
        return {
            'tier': 3,
            'tier_name': 'Desconhecido',
            'min_score': 0.60,
            'min_adx': 30.0,
            'buy_rsi_block': 64.0,
            'sell_rsi_block': 36.0,
            'require_mtf_for_all': True,
            'min_score_without_mtf': 7,
            'liquidity_check': True,
            'min_session_level': 'overlap',
        }


def check_crypto_liquidity_session(asset: str) -> Tuple[bool, str]:
    """
    Valida se o ativo cripto pode operar no horário atual baseado no tier de liquidez.
    
    Regras:
    - TIER 1 (BTC/ETH): Opera 24/7 (sempre retorna True)
    - TIER 2 (SOL/XRP/BNB): Requer sessão Londres OU NY, bloqueia finais de semana
    - TIER 3 (ADA/DOGE/LTC): APENAS overlap Londres+NY (12-16h UTC), bloqueia finais de semana
    
    Args:
        asset: String do ativo
    
    Returns:
        Tupla (pode_operar: bool, motivo: str)
        - pode_operar: True se ativo pode operar agora
        - motivo: Explicação da decisão
    
    Examples:
        >>> # Segunda-feira 14:00 UTC (overlap)
        >>> check_crypto_liquidity_session('BTC')
        (True, 'Tier 1 (Major) - Opera 24/7')
        >>> check_crypto_liquidity_session('ADA')
        (True, 'Tier 3 (Alt Coin) - Overlap Londres+NY (melhor liquidez)')
        
        >>> # Sábado 10:00 UTC
        >>> check_crypto_liquidity_session('ADA')
        (False, '❌ Tier 3 (Alt Coin) bloqueado em finais de semana...')
    """
    profile = get_crypto_signal_profile(asset)
    
    # TIER 1: sem restrição de horário
    if not profile.get('liquidity_check', False):
        return True, f"Tier {profile['tier']} ({profile['tier_name']}) - Opera 24/7"
    
    utc = datetime.now(timezone.utc)
    weekday = utc.weekday()  # 0=Segunda, 6=Domingo
    h = utc.hour + utc.minute / 60
    
    # Bloqueio de finais de semana para TIER 2 e TIER 3
    # Sábado (5) e Domingo (6)
    if weekday >= 5:
        return (
            False,
            f"❌ Tier {profile['tier']} ({profile['tier_name']}) bloqueado em finais de semana "
            f"(atual: {'Sábado' if weekday == 5 else 'Domingo'} {utc.hour:02d}:{utc.minute:02d} UTC). "
            f"Alts geram muitos dojis sem liquidez."
        )
    
    # Sessões
    london_session = 7.0 <= h < 16.0
    ny_session = 12.0 <= h < 21.0
    overlap_session = 12.0 <= h < 16.0
    
    min_session = profile.get('min_session_level', 'any')
    
    # TIER 2: aceita qualquer sessão ativa (Londres OU NY)
    if min_session == 'any':
        if london_session or ny_session:
            session_label = 'Overlap Londres+NY' if overlap_session else ('Londres' if london_session else 'Nova York')
            return True, f"Tier {profile['tier']} ({profile['tier_name']}) - Sessão ativa: {session_label}"
        else:
            return (
                False,
                f"❌ Tier {profile['tier']} ({profile['tier_name']}) requer sessão ativa. "
                f"Atual: {utc.hour:02d}:{utc.minute:02d} UTC (Asiática/Fechado). "
                f"Opere entre 07-16h UTC (Londres) ou 12-21h UTC (NY)."
            )
    
    # TIER 3: APENAS overlap Londres+NY (12-16h UTC)
    elif min_session == 'overlap':
        if overlap_session:
            return True, f"Tier {profile['tier']} ({profile['tier_name']}) - Overlap Londres+NY (melhor liquidez)"
        else:
            session_now = 'Londres' if london_session else ('Nova York' if ny_session else 'Asiática/Fechado')
            return (
                False,
                f"❌ Tier {profile['tier']} ({profile['tier_name']}) requer OVERLAP Londres+NY (12-16h UTC). "
                f"Atual: {utc.hour:02d}:{utc.minute:02d} UTC ({session_now}). "
                f"Alts de baixa liquidez geram dojis fora do overlap."
            )
    
    # Fallback: bloqueia se não conhece a regra
    return False, f"⚠️ Tier {profile['tier']} - Configuração de sessão desconhecida: {min_session}"


def is_forex_session_active() -> Tuple[bool, str]:
    """
    Retorna se há sessão forex líquida aberta.
    
    Sessões consideradas (UTC):
    - Londres: 07:00 – 16:00
    - Nova York: 12:00 – 21:00
    - Overlap London+NY: 12:00-16:00 (melhor momento)
    - Asiática: 21:00 – 07:00 (evitar para binários de 5 min)
    
    Returns:
        Tupla (ativo: bool, label: str)
        - ativo: True se sessão forex está ativa
        - label: Nome da sessão ou motivo de fechamento
    
    Examples:
        >>> # Segunda-feira 14:00 UTC
        >>> is_forex_session_active()
        (True, 'London+NY overlap')
        
        >>> # Terça-feira 23:00 UTC
        >>> is_forex_session_active()
        (False, 'Sessão asiática/fechado (23:00 UTC)')
        
        >>> # Sábado 10:00 UTC
        >>> is_forex_session_active()
        (False, 'Mercado fechado (fim de semana 10:00 UTC)')
    """
    utc = datetime.now(timezone.utc)
    
    # Forex spot fica fechado no fim de semana; evita alertas falsos em sábado/domingo
    if utc.weekday() >= 5:
        return False, f'Mercado fechado (fim de semana {utc.hour:02d}:{utc.minute:02d} UTC)'

    h = utc.hour + utc.minute / 60
    london = 7.0 <= h < 16.0
    new_york = 12.0 <= h < 21.0
    
    if london and new_york:
        return True, 'London+NY overlap'
    if london:
        return True, 'Londres'
    if new_york:
        return True, 'Nova York'
    
    return False, f'Sessão asiática/fechado ({utc.hour:02d}:{utc.minute:02d} UTC)'


def get_active_session_info() -> Dict[str, any]:
    """
    Retorna informações detalhadas sobre sessão de trading atual.
    
    Returns:
        Dict com informações da sessão:
        - is_active: Se há sessão ativa
        - session_name: Nome da sessão
        - is_overlap: Se está em overlap Londres+NY
        - hour_utc: Hora UTC atual
        - is_weekend: Se é fim de semana
    
    Examples:
        >>> get_active_session_info()
        {
            'is_active': True,
            'session_name': 'London+NY overlap',
            'is_overlap': True,
            'hour_utc': 14.5,
            'is_weekend': False
        }
    """
    utc = datetime.now(timezone.utc)
    h = utc.hour + utc.minute / 60
    is_weekend = utc.weekday() >= 5
    
    london = 7.0 <= h < 16.0
    new_york = 12.0 <= h < 21.0
    is_overlap = 12.0 <= h < 16.0
    
    is_active, session_name = is_forex_session_active()
    
    return {
        'is_active': is_active,
        'session_name': session_name,
        'is_overlap': is_overlap,
        'hour_utc': h,
        'is_weekend': is_weekend,
        'london_active': london,
        'ny_active': new_york,
    }
