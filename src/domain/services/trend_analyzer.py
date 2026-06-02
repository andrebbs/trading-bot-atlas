"""
Trend analysis service for trading bot.
Analyzes trends, classifies entries, and scores trading candidates.
"""
import pandas as pd
from typing import Dict


def score_monitor_candidate(
    timeframe: str,
    probability: float,
    setup_score: int,
    consensus: int,
    adx_value: float,
    primary_trend: int,
    signal: int,
) -> float:
    """
    Rankeia candidatos do monitor por qualidade para operação binária.
    
    Calcula score composto baseado em múltiplos fatores de qualidade.
    Usado para ordenar sinais quando múltiplos ativos disparam alertas.
    
    Args:
        timeframe: String do timeframe ('1m', '5m', etc.)
        probability: Probabilidade do sinal (0-100)
        setup_score: Score de qualidade do setup (0-10+)
        consensus: Número de indicadores concordando
        adx_value: Valor do ADX (força de tendência)
        primary_trend: Tendência primária (+1, -1, 0)
        signal: Direção do sinal (+1 BUY, -1 SELL)
    
    Returns:
        Score composto (float, maior = melhor)
    
    Examples:
        >>> score_monitor_candidate('5m', 65.0, 6, 4, 28.0, 1, 1)
        105.0  # Alta qualidade, alinhado com tendência
        >>> score_monitor_candidate('5m', 60.0, 4, 3, 20.0, -1, 1)
        82.0  # Qualidade ok, contra tendência (penalizado)
    """
    from src.domain.utils.time_utils import timeframe_to_minutes
    
    # Score base: probabilidade + setup + consenso + ADX
    rank = probability + (setup_score * 6.0) + (consensus * 4.0)
    rank += min(adx_value, 35.0) * 0.5  # ADX até 35 (cap)
    
    # Bônus para timeframes maiores (até 30m)
    rank += min(timeframe_to_minutes(timeframe), 30) * 0.1
    
    # Alinhamento com tendência primária
    if primary_trend == signal:
        rank += 10.0  # Bônus por alinhamento
    elif primary_trend != 0:
        rank -= 8.0  # Penalidade por contra-tendência
    
    return rank


def classify_binary_entry(
    timeframe: str,
    signal: int,
    probability: float,
    setup: dict,
    consensus: int,
    primary_trend: int,
    confirm_signal: int = 0,
    confirm_primary_trend: int = 0,
) -> dict:
    """
    Classifica o sinal binário como entrada direta, aceita 1 proteção ou descarte.
    
    Avalia múltiplos fatores de qualidade e retorna perfil de risco:
    - Entrada direta: Setup premium, executa sem proteção
    - Aceita 1 proteção: Setup bom, permite 1 martingale
    - Descartar: Setup abaixo do padrão
    
    Args:
        timeframe: String do timeframe
        signal: Direção do sinal (+1 BUY, -1 SELL)
        probability: Probabilidade do sinal
        setup: Dict com dados do setup (adx, score, warnings)
        consensus: Número de indicadores concordando
        primary_trend: Tendência primária do HTF
        confirm_signal: Sinal do timeframe de confirmação (para 1m)
        confirm_primary_trend: Tendência primária do TF confirmação
    
    Returns:
        Dict com classificação:
        - allowed: bool (se pode operar)
        - profile: str ('entrada direta', 'aceita 1 protecao', 'descartar')
        - reason: str (justificativa da decisão)
    
    Examples:
        >>> classify_binary_entry('5m', 1, 68.0, {'adx': 25, 'score': 7, 'warnings': []}, 4, 1)
        {'allowed': True, 'profile': 'entrada direta', 'reason': 'setup forte e alinhado'}
        
        >>> classify_binary_entry('5m', 1, 62.0, {'adx': 17, 'score': 5, 'warnings': []}, 3, 0)
        {'allowed': True, 'profile': 'aceita 1 protecao', 'reason': 'setup bom, mas nao premium'}
    """
    adx_value = float(setup.get('adx', 0.0))
    setup_score = int(setup.get('score', 0))
    warnings = setup.get('warnings', [])
    has_ema_warning = any('EMAs' in warning for warning in warnings)
    has_adx_warning = any('ADX' in warning for warning in warnings)

    # Regra global: nunca opera contra tendência primária definida
    if primary_trend != 0 and primary_trend != signal:
        return {
            'allowed': False,
            'profile': 'descartar',
            'reason': 'contra tendencia primaria',
        }

    # ═══════════════════════════════════════════════════════════════════
    # TIMEFRAME 1M: Requer confirmação obrigatória do M5
    # ═══════════════════════════════════════════════════════════════════
    if timeframe == '1m':
        # Sem confirmação M5: descarta
        if confirm_signal != signal:
            return {
                'allowed': False,
                'profile': 'descartar',
                'reason': 'M1 sem confirmacao operacional no M5',
            }

        # M5 contra tendência: descarta
        if confirm_primary_trend not in (0, signal):
            return {
                'allowed': False,
                'profile': 'descartar',
                'reason': 'M5 sem alinhamento de contexto',
            }

        # Entrada direta M1: setup PREMIUM + confirmação M5 alinhada
        if (
            probability >= 64.0
            and setup_score >= 6
            and consensus >= 4
            and adx_value >= 18.0
            and not has_ema_warning
            and not has_adx_warning
            and confirm_primary_trend == signal
        ):
            return {
                'allowed': True,
                'profile': 'entrada direta',
                'reason': 'M1 forte com confirmacao do M5',
            }

        # Aceita 1 proteção M1: setup BOM com confirmação básica
        if (
            probability >= 58.0
            and setup_score >= 5
            and consensus >= 3
            and adx_value >= 16.0
        ):
            return {
                'allowed': True,
                'profile': 'aceita 1 protecao',
                'reason': 'M1 valido, mas ainda exige gestao conservadora',
            }

        # M1 abaixo do padrão: descarta
        return {
            'allowed': False,
            'profile': 'descartar',
            'reason': 'M1 sem qualidade suficiente para binaria profissional',
        }

    # ═══════════════════════════════════════════════════════════════════
    # TIMEFRAMES 5M+: Critérios padrão (sem confirmação obrigatória)
    # ═══════════════════════════════════════════════════════════════════
    
    # Entrada direta: setup PREMIUM
    if (
        probability >= 65.0
        and setup_score >= 6
        and consensus >= 4
        and adx_value >= 18.0
        and not has_ema_warning
        and not has_adx_warning
    ):
        return {
            'allowed': True,
            'profile': 'entrada direta',
            'reason': 'setup forte e alinhado',
        }

    # Aceita 1 proteção: setup BOM
    if (
        probability >= 60.0
        and setup_score >= 5
        and consensus >= 3
        and adx_value >= 16.0
    ):
        return {
            'allowed': True,
            'profile': 'aceita 1 protecao',
            'reason': 'setup bom, mas nao premium',
        }

    # Abaixo do padrão: descarta
    return {
        'allowed': False,
        'profile': 'descartar',
        'reason': 'setup abaixo do padrao profissional',
    }


def get_primary_trend(exchange, symbol: str, timeframe: str) -> int:
    """
    Verifica tendência primária no timeframe superior usando EMA 9/21.
    
    Busca dados do Higher TimeFrame (HTF) e compara EMAs:
    - EMA9 > EMA21 e preço > EMA9 = tendência de alta (+1)
    - EMA9 < EMA21 e preço < EMA9 = tendência de baixa (-1)
    - Casos mistos ou laterais = indefinido (0)
    
    Args:
        exchange: Instância do ExchangeConnector
        symbol: Símbolo do ativo
        timeframe: Timeframe atual (função calcula HTF automaticamente)
    
    Returns:
        +1 (alta), -1 (baixa), 0 (indefinido/lateral)
    
    Examples:
        >>> get_primary_trend(exchange, 'BTC/USDT', '5m')
        1  # Tendência de alta no 15m
        >>> get_primary_trend(exchange, 'ETH/USDT', '1h')
        0  # Lateral no 4h
    """
    from src.domain.utils.time_utils import get_higher_timeframe
    
    higher_tf = get_higher_timeframe(timeframe)
    
    try:
        df_higher = exchange.fetch_ohlcv(symbol, higher_tf, limit=30)
        
        if df_higher is None or len(df_higher) < 21:
            return 0  # Dados insuficientes
        
        closes = df_higher['close'].values.astype(float)
        
        # Calcula EMAs
        ema9 = pd.Series(closes).ewm(span=9, adjust=False).mean().iloc[-1]
        ema21 = pd.Series(closes).ewm(span=21, adjust=False).mean().iloc[-1]
        last_close = float(closes[-1])
        
        # Tendência de alta: preço > EMA9 > EMA21
        if last_close > ema9 > ema21:
            return 1
        
        # Tendência de baixa: preço < EMA9 < EMA21
        if last_close < ema9 < ema21:
            return -1
        
        # Lateral ou misto
        return 0
        
    except Exception:
        return 0  # Erro: retorna indefinido


def get_trend_alignment_bonus(primary_trend: int, signal: int) -> float:
    """
    Retorna bônus/penalidade baseado em alinhamento de tendência.
    
    Args:
        primary_trend: Tendência primária (+1, -1, 0)
        signal: Direção do sinal (+1, -1)
    
    Returns:
        Bônus positivo (alinhado) ou penalidade (contra-tendência)
    
    Examples:
        >>> get_trend_alignment_bonus(1, 1)
        10.0  # Alinhado
        >>> get_trend_alignment_bonus(-1, 1)
        -8.0  # Contra-tendência
        >>> get_trend_alignment_bonus(0, 1)
        0.0   # Neutro
    """
    if primary_trend == signal:
        return 10.0  # Bônus
    elif primary_trend != 0:
        return -8.0  # Penalidade
    return 0.0  # Neutro
