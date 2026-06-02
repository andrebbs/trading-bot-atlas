"""
Quality gates service for trading bot.
Defines quality thresholds and scoring criteria based on timeframe and mode.
"""
import os


# Quality gate constants
MIN_ALERT_PROBABILITY = 60.0  # Perfil equilibrado para 5m+
MIN_ALERT_EDGE = 0.10  # Distância mínima de 0.5 (score 0.60 ou 0.40)
MIN_SIGNAL_CONSENSUS = 3  # Pelo menos 3 dos 4 indicadores principais devem concordar

# Ajuste para 1m: ainda seletivo, mas sem zerar completamente a frequência
MIN_ALERT_PROBABILITY_1M = 58.0
MIN_ALERT_EDGE_1M = 0.08
MIN_SIGNAL_CONSENSUS_1M = 3

# Setup quality scores
MIN_SETUP_SCORE = 4  # score mínimo 4/8 para 5m+ (elimina setups sem estrutura)
MIN_SETUP_SCORE_1M = 6  # 1m requer score mais alto

# Monitor configuration
MONITOR_INTERVAL_SECONDS = int(os.getenv('MONITOR_INTERVAL_SECONDS', '60'))
MONITOR_TARGET_SYMBOL_REVISIT_SECONDS = int(os.getenv('MONITOR_TARGET_SYMBOL_REVISIT_SECONDS', '240'))


def get_quality_gates(timeframe: str, is_weekend_mode: bool = False) -> tuple[float, float, int]:
    """
    Retorna gates de qualidade por timeframe e modo operacional.
    
    Gates de qualidade controlam filtros de sinal:
    - min_probability: Probabilidade mínima (50-100%)
    - min_edge: Distância mínima do neutro (0-0.5)
    - min_consensus: Número mínimo de indicadores concordando
    
    Args:
        timeframe: String do timeframe ('1m', '5m', etc.)
        is_weekend_mode: Se está em modo fim de semana
    
    Returns:
        Tupla (min_probability, min_edge, min_consensus)
    
    Examples:
        >>> get_quality_gates('5m')
        (60.0, 0.10, 3)
        >>> get_quality_gates('1m')
        (58.0, 0.08, 3)
        >>> get_quality_gates('5m', is_weekend_mode=True)
        (58.0, 0.06, 0)
    """
    # Modo fim de semana: gates mais relaxados para range trading
    if is_weekend_mode:
        return 58.0, 0.06, 0
    
    # Importa aqui para evitar circular import
    from src.domain.utils.time_utils import timeframe_to_minutes
    
    tf_minutes = timeframe_to_minutes(timeframe)
    
    # Timeframes de 1m: gates ligeiramente mais baixos
    if tf_minutes <= 1:
        return MIN_ALERT_PROBABILITY_1M, MIN_ALERT_EDGE_1M, MIN_SIGNAL_CONSENSUS_1M
    
    # Timeframes 5m+: gates padrão
    return MIN_ALERT_PROBABILITY, MIN_ALERT_EDGE, MIN_SIGNAL_CONSENSUS


def get_setup_min_score(timeframe: str, is_weekend_mode: bool = False) -> int:
    """
    Retorna score mínimo de setup por timeframe.
    
    Score de setup mede a qualidade estrutural do sinal:
    - Baseado em confirmações técnicas (EMAs, volume, momentum, etc.)
    - Timeframes menores requerem scores mais altos
    - Modo weekend tem scores diferentes
    
    Args:
        timeframe: String do timeframe
        is_weekend_mode: Se está em modo fim de semana
    
    Returns:
        Score mínimo (inteiro 0-10+)
    
    Examples:
        >>> get_setup_min_score('5m')
        4
        >>> get_setup_min_score('1m')
        6
        >>> get_setup_min_score('1m', is_weekend_mode=True)
        5
    """
    # Importa aqui para evitar circular import
    from src.domain.utils.time_utils import timeframe_to_minutes
    
    tf_minutes = timeframe_to_minutes(timeframe)
    
    # Modo fim de semana
    if is_weekend_mode:
        return 5 if tf_minutes <= 1 else 4
    
    # Timeframes de 1m requerem score mais alto
    if tf_minutes <= 1:
        return MIN_SETUP_SCORE_1M
    
    # Timeframes 5m+ usam score padrão
    return MIN_SETUP_SCORE


def get_symbols_per_cycle(
    total_symbols: int,
    actionable_timeframes: list[str] | None = None,
    monitor_interval: int | None = None,
    target_revisit: int | None = None
) -> int:
    """
    Calcula quantos ativos devem ser verificados por ciclo de monitoramento.
    
    Garante que todos os símbolos sejam revisitados dentro do tempo alvo,
    considerando múltiplos timeframes se aplicável.
    
    Args:
        total_symbols: Número total de símbolos a monitorar
        actionable_timeframes: Lista de timeframes ativos (opcional)
        monitor_interval: Intervalo entre ciclos em segundos (padrão: MONITOR_INTERVAL_SECONDS)
        target_revisit: Tempo alvo para revisitar símbolo em segundos (padrão: MONITOR_TARGET_SYMBOL_REVISIT_SECONDS)
    
    Returns:
        Número de símbolos a processar por ciclo
    
    Examples:
        >>> get_symbols_per_cycle(10)
        3  # Com 60s ciclo e 240s target: 10*60/240 ≈ 3
        >>> get_symbols_per_cycle(5)
        2
    """
    if total_symbols <= 0:
        return 1
    
    interval = monitor_interval or MONITOR_INTERVAL_SECONDS
    revisit = target_revisit or MONITOR_TARGET_SYMBOL_REVISIT_SECONDS
    
    # Cálculo básico: quantos símbolos precisam ser processados por ciclo
    # para garantir que todos sejam revisitados dentro do tempo alvo
    symbols_per_cycle = max(
        1,
        (total_symbols * interval + revisit - 1) // revisit,
    )

    # Se há múltiplos timeframes, precisa ajustar para janela mais estreita
    if actionable_timeframes:
        from src.domain.utils.time_utils import timeframe_to_minutes
        
        narrowest_cycles = None
        
        for tf in actionable_timeframes:
            # Importa função de time_utils (já criada)
            # get_pre_alert_window_seconds retorna (max_s, min_s)
            # mas está em time_utils, então vou usar cálculo simplificado aqui
            # ou fazer import local
            
            tf_minutes = timeframe_to_minutes(tf)
            
            # Janela de pré-alerta (simplificado)
            if tf_minutes >= 5:
                window_seconds = 45 - 10  # 35 segundos
            else:
                window_seconds = 180 - 30  # 150 segundos
            
            cycles_available = max(1, -(-window_seconds // interval))
            
            if narrowest_cycles is None or cycles_available < narrowest_cycles:
                narrowest_cycles = cycles_available

        if narrowest_cycles:
            symbols_needed = max(1, -(-total_symbols // narrowest_cycles))
            symbols_per_cycle = max(symbols_per_cycle, symbols_needed)

    return min(symbols_per_cycle, total_symbols)


def validate_signal_quality(
    probability: float,
    score: float,
    consensus: int,
    timeframe: str,
    is_weekend_mode: bool = False
) -> tuple[bool, str]:
    """
    Valida se sinal atende os quality gates.
    
    Args:
        probability: Probabilidade do sinal (0-100)
        score: Score normalizado (0.0-1.0)
        consensus: Número de indicadores em consenso
        timeframe: String do timeframe
        is_weekend_mode: Se está em modo fim de semana
    
    Returns:
        Tupla (aprovado: bool, motivo: str)
    
    Examples:
        >>> validate_signal_quality(65.0, 0.65, 3, '5m')
        (True, 'Aprovado nos quality gates')
        >>> validate_signal_quality(55.0, 0.55, 2, '5m')
        (False, 'Probabilidade 55.0% abaixo do mínimo 60.0%')
    """
    min_prob, min_edge, min_cons = get_quality_gates(timeframe, is_weekend_mode)
    
    # Valida probabilidade
    if probability < min_prob:
        return False, f"Probabilidade {probability:.1f}% abaixo do mínimo {min_prob:.1f}%"
    
    # Valida edge (distância do neutro 0.5)
    edge = abs(score - 0.5)
    if edge < min_edge:
        return False, f"Edge {edge:.2f} abaixo do mínimo {min_edge:.2f}"
    
    # Valida consenso
    if consensus < min_cons:
        return False, f"Consenso {consensus} abaixo do mínimo {min_cons}"
    
    return True, "Aprovado nos quality gates"


def get_quality_profile(timeframe: str, is_weekend_mode: bool = False) -> dict:
    """
    Retorna perfil completo de quality gates para um timeframe.
    
    Args:
        timeframe: String do timeframe
        is_weekend_mode: Se está em modo fim de semana
    
    Returns:
        Dict com todas as configurações de qualidade
    
    Examples:
        >>> get_quality_profile('5m')
        {
            'min_probability': 60.0,
            'min_edge': 0.10,
            'min_consensus': 3,
            'min_setup_score': 4,
            'timeframe': '5m',
            'is_weekend_mode': False
        }
    """
    min_prob, min_edge, min_cons = get_quality_gates(timeframe, is_weekend_mode)
    min_setup = get_setup_min_score(timeframe, is_weekend_mode)
    
    return {
        'min_probability': min_prob,
        'min_edge': min_edge,
        'min_consensus': min_cons,
        'min_setup_score': min_setup,
        'timeframe': timeframe,
        'is_weekend_mode': is_weekend_mode,
    }
