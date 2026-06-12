"""
Weekend analyzer service for trading bot.
Handles weekend binary mode with range-based setups.
"""
import os
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict


# Weekend configuration
WEEKEND_RANGE_LOOKBACK = int(os.getenv('WEEKEND_RANGE_LOOKBACK', '30'))
WEEKEND_MAX_ADX = float(os.getenv('WEEKEND_MAX_ADX', '32.0'))
WEEKEND_EXTREME_ZONE_THRESHOLD = float(os.getenv('WEEKEND_EXTREME_ZONE_THRESHOLD', '0.30'))
WEEKEND_RANGE_TOUCH_TOLERANCE = float(os.getenv('WEEKEND_RANGE_TOUCH_TOLERANCE', '0.005'))
WEEKEND_MAX_REENTRIES = int(os.getenv('WEEKEND_MAX_REENTRIES', '2'))
WEEKEND_1M_CONTINUATION_MIN_SCORE = int(os.getenv('WEEKEND_1M_CONTINUATION_MIN_SCORE', '5'))
WEEKEND_1M_CONTINUATION_MIN_PROBABILITY = float(os.getenv('WEEKEND_1M_CONTINUATION_MIN_PROBABILITY', '56.0'))

# Global state
weekend_reentry_tracker = {}


def is_weekend_binary_mode(reference_time: datetime | None = None, market_type: str = 'crypto_binary') -> bool:
    """
    Ativa operacional de fim de semana apenas para crypto binário.
    
    Args:
        reference_time: Datetime de referência (opcional, usa now se None)
        market_type: Tipo de mercado ('crypto_binary', 'forex', etc.)
    
    Returns:
        True se é fim de semana E mercado é crypto binário
    
    Examples:
        >>> is_weekend_binary_mode(datetime(2026, 6, 7))  # Sábado
        True
        >>> is_weekend_binary_mode(datetime(2026, 6, 9))  # Segunda
        False
    """
    if market_type != 'crypto_binary':
        return False
    
    current = reference_time or datetime.utcnow()
    return current.weekday() >= 5  # Sábado (5) ou Domingo (6)


def _count_range_touches(values: pd.Series, level: float, tolerance: float) -> int:
    """
    Conta toques em uma zona para validar range operacional.
    
    Args:
        values: Série de valores (highs ou lows)
        level: Nível do range (topo ou fundo)
        tolerance: Tolerância para considerar toque
    
    Returns:
        Número de toques dentro da tolerância
    
    Examples:
        >>> _count_range_touches(pd.Series([100, 99, 101, 100.5]), 100.0, 1.0)
        4  # Todos dentro da tolerância de ±1
        >>> _count_range_touches(pd.Series([95, 96, 104]), 100.0, 1.0)
        0  # Nenhum toque
    """
    if values.empty:
        return 0
    
    # Calcula distância absoluta de cada valor ao nível
    distances = (values.astype(float) - float(level)).abs()
    
    # Conta quantos estão dentro da tolerância
    return int((distances <= tolerance).sum())


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Evita divisão por zero em cálculos."""
    try:
        if denominator in (0, None) or pd.isna(denominator):
            return default
        return float(numerator) / float(denominator)
    except Exception:
        return default


def evaluate_weekend_binary_setup(
    df: pd.DataFrame,
    timeframe: str,
    signal_data: dict | None = None,
    market_type: str = 'crypto_binary'
) -> Dict:
    """
    Detecta setup de fim de semana baseado em range, rejeição e falsa quebra.
    
    Estratégias específicas para fim de semana:
    1. Range trading: Identifica topo/fundo com múltiplos toques
    2. Falsa quebra: Furou extremo e fechou de volta (liquidity grab)
    3. Rejeição: Defendeu extremo com pavio forte
    4. Exaustão: Esticou extremo com perda de momentum
    5. Continuação micro (1m): Setup de scalp dentro de tendência
    
    Args:
        df: DataFrame com dados OHLCV e indicadores
        timeframe: String do timeframe
        signal_data: Dict com dados do sinal (opcional, para continuação)
        market_type: Tipo de mercado
    
    Returns:
        Dict completo com:
        - signal: +1 (BUY), -1 (SELL), 0 (neutro)
        - score: 0-10+
        - probability: 50-86%
        - setup_type: descrição do padrão
        - confirmations: list[str]
        - warnings: list[str]
        - expiry_candles: 2-3
        - range_high, range_low, adx, close_position
        - score_source: 'range', 'micro_continuation' ou 'continuation'
    
    Examples:
        >>> evaluate_weekend_binary_setup(df, '1m')
        {
            'signal': 1,
            'score': 7,
            'probability': 78.0,
            'setup_type': 'falsa quebra + rejeicao no suporte',
            'confirmations': ['furou o fundo e fechou de volta...'],
            'expiry_candles': 2,
            ...
        }
    """
    from src.domain.utils.time_utils import timeframe_to_minutes
    from src.domain.services.signal_evaluator import evaluate_signal_setup
    
    neutral_response = {
        'signal': 0,
        'score': 0,
        'probability': 50.0,
        'setup_type': 'aguardando extremo do range',
        'confirmations': [],
        'warnings': ['sem setup de fim de semana no candle atual'],
        'expiry_candles': 2,
        'range_high': None,
        'range_low': None,
        'adx': 0.0,
        'close_position': 0.5,
        'score_source': 'range',
    }

    if len(df) < WEEKEND_RANGE_LOOKBACK + 5:
        neutral_response['warnings'] = ['historico insuficiente para range de fim de semana']
        return neutral_response

    # ═══════════════════════════════════════════════════════════════════
    # ANÁLISE DO RANGE
    # ═══════════════════════════════════════════════════════════════════
    window = df.iloc[-(WEEKEND_RANGE_LOOKBACK + 1):-1].copy()
    last_closed = df.iloc[-1]
    prev_closed = df.iloc[-2]

    range_high = float(window['high'].max())
    range_low = float(window['low'].min())
    range_size = max(range_high - range_low, 1e-9)
    
    close = float(last_closed['close'])
    open_price = float(last_closed['open'])
    high = float(last_closed['high'])
    low = float(last_closed['low'])
    
    candle_range = max(high - low, 1e-9)
    body_ratio = abs(close - open_price) / candle_range
    upper_wick_ratio = (high - max(open_price, close)) / candle_range
    lower_wick_ratio = (min(open_price, close) - low) / candle_range
    close_position = min(max((close - range_low) / range_size, 0.0), 1.0)

    # Indicadores
    atr = float(last_closed.get('atr', range_size / 8.0))
    adx = float(last_closed.get('adx', 0.0))
    rsi = float(last_closed.get('rsi', 50.0))
    bb_upper = float(last_closed.get('bb_upper', range_high))
    bb_lower = float(last_closed.get('bb_lower', range_low))
    bb_middle = float(last_closed.get('bb_middle', close))
    stoch_k = float(last_closed.get('stoch_k', 50.0))
    stoch_d = float(last_closed.get('stoch_d', 50.0))
    macd_diff = float(last_closed.get('macd_diff', 0.0))
    prev_macd_diff = float(prev_closed.get('macd_diff', macd_diff))

    # Validação do range
    tolerance = max(range_size * WEEKEND_RANGE_TOUCH_TOLERANCE, atr * 0.8)
    top_touches = _count_range_touches(window['high'], range_high, tolerance)
    bottom_touches = _count_range_touches(window['low'], range_low, tolerance)
    range_pct = _safe_ratio(range_size, close, default=0.0) * 100.0
    is_range = top_touches >= 2 and bottom_touches >= 2 and adx <= WEEKEND_MAX_ADX

    # ═══════════════════════════════════════════════════════════════════
    # PADRÕES DE CANDLE
    # ═══════════════════════════════════════════════════════════════════
    bullish_engulf = (
        float(prev_closed['close']) < float(prev_closed['open'])
        and close > open_price
        and close >= float(prev_closed['open'])
        and open_price <= float(prev_closed['close'])
    )
    bearish_engulf = (
        float(prev_closed['close']) > float(prev_closed['open'])
        and close < open_price
        and close <= float(prev_closed['open'])
        and open_price >= float(prev_closed['close'])
    )

    # ═══════════════════════════════════════════════════════════════════
    # DETECÇÃO DE SETUPS
    # ═══════════════════════════════════════════════════════════════════
    false_break_buy = (
        low < range_low
        and close > range_low
        and lower_wick_ratio >= 0.35
        and close_position <= 0.38
    )
    false_break_sell = (
        high > range_high
        and close < range_high
        and upper_wick_ratio >= 0.35
        and close_position >= 0.62
    )
    
    rejection_buy = (
        close_position <= WEEKEND_EXTREME_ZONE_THRESHOLD
        and lower_wick_ratio >= 0.35
        and close >= bb_lower
        and (close >= open_price or bullish_engulf)
    )
    rejection_sell = (
        close_position >= 1.0 - WEEKEND_EXTREME_ZONE_THRESHOLD
        and upper_wick_ratio >= 0.35
        and close <= bb_upper
        and (close <= open_price or bearish_engulf)
    )

    # ═══════════════════════════════════════════════════════════════════
    # AVALIAÇÃO INICIAL
    # ═══════════════════════════════════════════════════════════════════
    signal = 0
    setup_type = 'aguardando extremo do range'
    confirmations = []
    warnings = []
    score = 0
    
    tf_minutes = timeframe_to_minutes(timeframe)
    expiry_candles = 2 if tf_minutes <= 1 else 3
    score_source = 'range'

    if not is_range:
        warnings.append(
            f'contexto sem range limpo (ADX {adx:.1f}, toques topo/fundo {top_touches}/{bottom_touches})'
        )
    else:
        score += 2
        confirmations.append(f'range validado com {top_touches} toques no topo e {bottom_touches} no fundo')
        confirmations.append(f'ADX comportado para reversao ({adx:.1f})')

    # Setups principais
    if is_range and false_break_buy:
        signal = 1
        setup_type = 'falsa quebra + rejeicao no suporte'
        score += 4
        confirmations.append('furou o fundo e fechou de volta para dentro do range')
        confirmations.append('pavio inferior confirma captura de liquidez')
    elif is_range and false_break_sell:
        signal = -1
        setup_type = 'falsa quebra + rejeicao na resistencia'
        score += 4
        confirmations.append('furou o topo e fechou de volta para dentro do range')
        confirmations.append('pavio superior confirma captura de liquidez')
    elif is_range and rejection_buy:
        signal = 1
        setup_type = 'rejeicao no fundo do range'
        score += 3
        confirmations.append('suporte defendido com rejeicao clara')
    elif is_range and rejection_sell:
        signal = -1
        setup_type = 'rejeicao no topo do range'
        score += 3
        confirmations.append('resistencia defendida com rejeicao clara')

    # ═══════════════════════════════════════════════════════════════════
    # SETUP DE EXAUSTÃO (ANTECIPAÇÃO)
    # ═══════════════════════════════════════════════════════════════════
    anticipation_zone_threshold = min(0.38, WEEKEND_EXTREME_ZONE_THRESHOLD + 0.08)
    anticipation_buy = (
        is_range
        and signal == 0
        and close_position <= anticipation_zone_threshold
        and (stoch_k <= 12 or (stoch_k >= stoch_d and stoch_k <= 35))
        and (rsi <= 44 or lower_wick_ratio >= 0.25)
        and macd_diff >= prev_macd_diff
    )
    anticipation_sell = (
        is_range
        and signal == 0
        and close_position >= 1.0 - anticipation_zone_threshold
        and (stoch_k >= 88 or (stoch_k <= stoch_d and stoch_k >= 65))
        and (rsi >= 56 or upper_wick_ratio >= 0.30)
        and macd_diff <= prev_macd_diff
    )

    if anticipation_buy:
        signal = 1
        setup_type = 'exaustao no fundo do range'
        score += 3
        confirmations.append('preco esticado no suporte com perda de pressao vendedora')
        confirmations.append('estocastico/RSI sugerem reversao antecipada no extremo')
    elif anticipation_sell:
        signal = -1
        setup_type = 'exaustao no topo do range'
        score += 3
        confirmations.append('preco esticado na resistencia com perda de pressao compradora')
        confirmations.append('estocastico/RSI sugerem reversao antecipada no extremo')

    # ═══════════════════════════════════════════════════════════════════
    # CONFIRMAÇÕES ADICIONAIS POR DIREÇÃO
    # ═══════════════════════════════════════════════════════════════════
    if signal == 1:
        if bullish_engulf:
            score += 1
            confirmations.append('engolfo de alta na zona extrema')
        if rsi <= 45:
            score += 1
            confirmations.append(f'RSI comprimido para reversao ({rsi:.1f})')
        if stoch_k >= stoch_d and stoch_k <= 35:
            score += 1
            confirmations.append('estocastico virou para cima na sobrevenda')
        if close > bb_middle and false_break_buy:
            score += 1
            confirmations.append('retorno rapido acima da media do range')
        if close_position > 0.45:
            warnings.append('retorno ja avancou demais; entrada pode ficar tardia')
    
    elif signal == -1:
        if bearish_engulf:
            score += 1
            confirmations.append('engolfo de baixa na zona extrema')
        if rsi >= 55:
            score += 1
            confirmations.append(f'RSI esticado para reversao ({rsi:.1f})')
        if stoch_k <= stoch_d and stoch_k >= 65:
            score += 1
            confirmations.append('estocastico virou para baixo na sobrecompra')
        if close < bb_middle and false_break_sell:
            score += 1
            confirmations.append('retorno rapido abaixo da media do range')
        if close_position < 0.55:
            warnings.append('retorno ja avancou demais; entrada pode ficar tardia')

    # Avisos gerais
    if range_pct < 0.35:
        warnings.append(f'range curto demais ({range_pct:.2f}%); payoff pode ficar apertado')
        score -= 1
    if body_ratio > 0.70 and signal != 0:
        warnings.append('candle de gatilho grande demais; risco de entrada atrasada')
        score -= 1
    if 0.35 <= close_position <= 0.65 and signal == 0:
        warnings.append('preco no meio do range; sem vantagem estatistica')

    # ═══════════════════════════════════════════════════════════════════
    # FALLBACK: MICRO CONTINUAÇÃO (1M)
    # ═══════════════════════════════════════════════════════════════════
    if signal == 0 and signal_data is not None and tf_minutes <= 1:
        continuation_signal = int(signal_data.get('signal', 0))
        continuation_score_hint = float(signal_data.get('score', 0.5))

        if continuation_signal == 0:
            if continuation_score_hint >= 0.55:
                continuation_signal = 1
            elif continuation_score_hint <= 0.45:
                continuation_signal = -1

        if continuation_signal != 0:
            continuation_setup = evaluate_signal_setup(df, continuation_signal, signal_data, timeframe)
            confirmations_blob = ' '.join(continuation_setup.get('confirmations', []))
            setup_type_hint = continuation_setup.get('setup_type', '')
            
            if (
                continuation_setup['score'] >= WEEKEND_1M_CONTINUATION_MIN_SCORE
                and float(continuation_setup.get('adx', adx)) >= max(20.0, WEEKEND_MAX_ADX - 8.0)
                and float(signal_data.get('probability', 50.0)) >= WEEKEND_1M_CONTINUATION_MIN_PROBABILITY
                and (
                    'pullback' in setup_type_hint
                    or 'rompimento' in setup_type_hint
                    or 'MACD acelerando' in confirmations_blob
                    or 'estocastico confirma' in confirmations_blob
                )
            ):
                signal = continuation_signal
                score = max(score, int(continuation_setup['score']))
                score_source = 'micro_continuation'
                setup_type = f"micro continuidade ({continuation_setup['setup_type']})"
                confirmations = list(continuation_setup['confirmations'][:4])
                warnings = list(continuation_setup['warnings'][:2])
                warnings.append('scalp weekend: setup de continuidade curta, aceitar no maximo 2 martingales')

    # ═══════════════════════════════════════════════════════════════════
    # FALLBACK: CONTINUAÇÃO EXCEPCIONAL (5M+)
    # ═══════════════════════════════════════════════════════════════════
    if signal == 0 and signal_data is not None and tf_minutes >= 5:
        continuation_signal = int(signal_data.get('signal', 0))
        continuation_score_hint = float(signal_data.get('score', 0.5))

        if continuation_signal == 0:
            if continuation_score_hint >= 0.58:
                continuation_signal = 1
            elif continuation_score_hint <= 0.42:
                continuation_signal = -1

        if continuation_signal != 0:
            continuation_setup = evaluate_signal_setup(df, continuation_signal, signal_data, timeframe)
            continuation_min_score = 6 if abs(continuation_score_hint - 0.5) >= 0.10 else 8
            
            if (
                continuation_setup['score'] >= continuation_min_score
                and float(continuation_setup.get('adx', adx)) >= max(28.0, WEEKEND_MAX_ADX - 2.0)
                and float(signal_data.get('probability', 50.0)) >= 58.0
            ):
                signal = continuation_signal
                score = max(score, int(continuation_setup['score']))
                score_source = 'continuation'
                setup_type = f"continuidade excepcional ({continuation_setup['setup_type']})"
                confirmations = list(continuation_setup['confirmations'][:4])
                warnings = [
                    warning
                    for warning in continuation_setup['warnings'][:3]
                    if 'sem alinhamento limpo das EMAs' not in warning
                ]
                warnings.append('fim de semana fora de range: operar apenas com contexto premium')

    # ═══════════════════════════════════════════════════════════════════
    # RESULTADO FINAL
    # ═══════════════════════════════════════════════════════════════════
    score = max(score, 0)
    probability = min(86.0, 50.0 + score * 4.0)

    return {
        'signal': signal,
        'score': int(score),
        'probability': float(probability),
        'setup_type': setup_type,
        'confirmations': confirmations[:4],
        'warnings': warnings[:3],
        'expiry_candles': expiry_candles,
        'range_high': range_high,
        'range_low': range_low,
        'adx': adx,
        'close_position': close_position,
        'score_source': score_source,
    }


def allow_weekend_reentry(symbol_key: str, signal: int, now: datetime, timeframe: str) -> bool:
    """
    Permite reemitir setup scalp no fim de semana até 2 martingales.
    
    Gerencia estado de reentrada para evitar spam de alertas repetidos,
    mas permitindo até WEEKEND_MAX_REENTRIES (padrão: 2) proteções.
    
    Args:
        symbol_key: Chave do símbolo
        signal: Direção do sinal (+1 ou -1)
        now: Timestamp atual
        timeframe: String do timeframe
    
    Returns:
        True se pode reemitir sinal (ainda tem proteções disponíveis)
    
    Examples:
        >>> allow_weekend_reentry('BTC/USDT', 1, now, '1m')
        True  # Primeiro alerta
        >>> allow_weekend_reentry('BTC/USDT', 1, now + 60s, '1m')
        True  # Segunda tentativa (proteção 1)
        >>> allow_weekend_reentry('BTC/USDT', 1, now + 120s, '1m')
        False  # Terceira tentativa (limite atingido)
    """
    from src.domain.utils.time_utils import timeframe_to_minutes
    
    if timeframe_to_minutes(timeframe) > 1:
        return False

    state_key = f"{symbol_key}:{signal}"
    state = weekend_reentry_tracker.get(state_key)
    
    if state is None:
        return False

    last_at = state.get('last_at')
    if last_at is None:
        return False

    # Limpa estado se passou muito tempo
    max_gap = timedelta(minutes=timeframe_to_minutes(timeframe) * (WEEKEND_MAX_REENTRIES + 1))
    if now - last_at > max_gap:
        weekend_reentry_tracker.pop(state_key, None)
        return False

    # Verifica se ainda tem proteções disponíveis
    return int(state.get('alerts_sent', 1)) < (WEEKEND_MAX_REENTRIES + 1)


def update_weekend_reentry_state(symbol_key: str, signal: int, now: datetime):
    """
    Atualiza estado de reentrada após emitir alerta.
    
    Args:
        symbol_key: Chave do símbolo
        signal: Direção do sinal
        now: Timestamp atual
    """
    state_key = f"{symbol_key}:{signal}"
    
    if state_key not in weekend_reentry_tracker:
        weekend_reentry_tracker[state_key] = {
            'alerts_sent': 1,
            'last_at': now,
        }
    else:
        state = weekend_reentry_tracker[state_key]
        state['alerts_sent'] = state.get('alerts_sent', 0) + 1
        state['last_at'] = now


def get_weekend_reentry_stats(symbol_key: str, signal: int) -> Dict:
    """
    Retorna estatísticas de reentrada para debug.
    
    Args:
        symbol_key: Chave do símbolo
        signal: Direção do sinal
    
    Returns:
        Dict com alerts_sent, last_at, remaining_entries
    """
    state_key = f"{symbol_key}:{signal}"
    state = weekend_reentry_tracker.get(state_key, {})
    
    alerts_sent = state.get('alerts_sent', 0)
    remaining = max(0, WEEKEND_MAX_REENTRIES + 1 - alerts_sent)
    
    return {
        'alerts_sent': alerts_sent,
        'last_at': state.get('last_at'),
        'remaining_entries': remaining,
        'max_entries': WEEKEND_MAX_REENTRIES + 1,
    }


def clear_weekend_reentry_tracker():
    """Limpa todo o estado de reentrada (útil ao iniciar nova sessão)."""
    weekend_reentry_tracker.clear()
