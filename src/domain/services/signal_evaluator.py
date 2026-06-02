"""
Signal evaluation service for trading bot.
Evaluates setup quality, detects patterns, and validates signal strength.
"""
import pandas as pd
from typing import Dict, Tuple
from config import config


def _last_fractal_level(df: pd.DataFrame, direction: str) -> float | None:
    """
    Retorna o último topo/fundo fractal confirmado.
    
    Args:
        df: DataFrame com dados OHLCV e fractals
        direction: 'high' para topo, 'low' para fundo
    
    Returns:
        Preço do último fractal ou None se não houver
    
    Examples:
        >>> _last_fractal_level(df, 'high')
        45250.50  # Último topo fractal
        >>> _last_fractal_level(df, 'low')
        44800.00  # Último fundo fractal
    """
    column = 'fractal_high' if direction == 'high' else 'fractal_low'
    price_column = 'high' if direction == 'high' else 'low'
    
    if column not in df.columns:
        return None

    fractals = df[df[column] == True]
    
    if fractals.empty:
        return None
    
    return float(fractals.iloc[-1][price_column])


def _three_candle_confirmation(df: pd.DataFrame, signal: int) -> Tuple[bool, str]:
    """
    Padrão dos 3 candles (Dow / price action):
    - Bull: [exaustão/doji] → [sweep de mínima ou pullback] → [confirmação bullish forte]
    - Bear: [exaustão/doji] → [sweep de máxima ou pullback] → [confirmação bearish forte]
    
    Args:
        df: DataFrame com dados OHLCV
        signal: +1 (BUY) ou -1 (SELL)
    
    Returns:
        Tupla (matched: bool, descrição: str)
    
    Examples:
        >>> _three_candle_confirmation(df, 1)
        (True, 'exaustao + sweep de minima + confirmacao bullish')
        >>> _three_candle_confirmation(df, -1)
        (False, '')
    """
    if len(df) < 3:
        return False, ''

    c3 = df.iloc[-3]  # hesitação / exaustão
    c2 = df.iloc[-2]  # negação / sweep
    c1 = df.iloc[-1]  # confirmação

    def _br(c):
        """Calcula body ratio do candle."""
        r = max(float(c['high']) - float(c['low']), 1e-9)
        return abs(float(c['close']) - float(c['open'])) / r

    c3_br = _br(c3)
    c1_br = _br(c1)
    c1_bullish = float(c1['close']) > float(c1['open'])
    c1_bearish = float(c1['close']) < float(c1['open'])
    c2_bearish = float(c2['close']) < float(c2['open'])
    c2_bullish = float(c2['close']) > float(c2['open'])
    c3_doji = c3_br < 0.35
    c1_strong = c1_br >= 0.50

    # ═══════════════════════════════════════════════════════════════════
    # SINAL DE COMPRA (BUY)
    # ═══════════════════════════════════════════════════════════════════
    if signal == 1:
        # Reversão: exaustão → sweep de mínima → confirmação bullish
        sweep_reversal = (
            c3_doji
            and c2_bearish
            and float(c2['low']) <= float(c3['low'])
            and c1_bullish and c1_strong
            and float(c1['close']) > max(float(c2['open']), float(c2['close']))
        )
        
        # Continuação: impulso → pullback curto → retomada
        continuation = (
            float(c3['close']) > float(c3['open'])  # c3 bullish
            and c2_bearish
            and float(c2['low']) > float(c3['low'])  # pullback não viola c3
            and c1_bullish and c1_strong
            and float(c1['close']) > float(c2['high'])
        )
        
        if sweep_reversal:
            return True, 'exaustao + sweep de minima + confirmacao bullish'
        if continuation:
            return True, 'impulso + pullback + continuacao bullish'

    # ═══════════════════════════════════════════════════════════════════
    # SINAL DE VENDA (SELL)
    # ═══════════════════════════════════════════════════════════════════
    elif signal == -1:
        # Reversão: exaustão → sweep de máxima → confirmação bearish
        sweep_reversal = (
            c3_doji
            and c2_bullish
            and float(c2['high']) >= float(c3['high'])
            and c1_bearish and c1_strong
            and float(c1['close']) < min(float(c2['open']), float(c2['close']))
        )
        
        # Continuação: impulso → pullback curto → retomada
        continuation = (
            float(c3['close']) < float(c3['open'])  # c3 bearish
            and c2_bullish
            and float(c2['high']) < float(c3['high'])  # pullback não viola c3
            and c1_bearish and c1_strong
            and float(c1['close']) < float(c2['low'])
        )
        
        if sweep_reversal:
            return True, 'exaustao + sweep de maxima + confirmacao bearish'
        if continuation:
            return True, 'impulso + pullback + continuacao bearish'

    return False, ''


def _detect_sweep(df: pd.DataFrame, signal: int, lookback: int = 10) -> Tuple[bool, str]:
    """
    Detecta candle de sweep: furou extremo recente com sombra longa e fechou de volta.
    Indica captura de liquidez / armadilha antes de movimento real.
    
    Args:
        df: DataFrame com dados OHLCV
        signal: +1 (BUY) ou -1 (SELL)
        lookback: Número de candles para buscar extremos
    
    Returns:
        Tupla (matched: bool, descrição: str)
    
    Examples:
        >>> _detect_sweep(df, 1)
        (True, 'sweep de minima recente com rejeicao forte (liquidity grab)')
        >>> _detect_sweep(df, -1)
        (False, '')
    """
    if len(df) < lookback + 2:
        return False, ''

    c1 = df.iloc[-1]
    window = df.iloc[-(lookback + 1):-1]
    
    h = float(c1['high'])
    l = float(c1['low'])
    o = float(c1['open'])
    c = float(c1['close'])
    rng = max(h - l, 1e-9)
    
    upper_wick = (h - max(o, c)) / rng
    lower_wick = (min(o, c) - l) / rng
    
    recent_high = float(window['high'].max())
    recent_low = float(window['low'].min())

    # Sweep para COMPRA: furou mínima recente e fechou acima dela
    if signal == 1:
        swept = l < recent_low and c > recent_low
        if swept and lower_wick >= 0.40:
            return True, 'sweep de minima recente com rejeicao forte (liquidity grab)'

    # Sweep para VENDA: furou máxima recente e fechou abaixo dela
    elif signal == -1:
        swept = h > recent_high and c < recent_high
        if swept and upper_wick >= 0.40:
            return True, 'sweep de maxima recente com rejeicao forte (liquidity grab)'

    return False, ''


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Evita divisão por zero em cálculos de setup."""
    try:
        if denominator in (0, None) or pd.isna(denominator):
            return default
        return float(numerator) / float(denominator)
    except Exception:
        return default


def evaluate_signal_setup(df: pd.DataFrame, signal: int, signal_data: dict, timeframe: str) -> Dict:
    """
    Avalia a qualidade estrutural do setup para filtrar sinais fracos.
    
    Analisa múltiplos fatores técnicos e atribui score de qualidade:
    - EMAs (alinhamento de tendência)
    - ADX (força de tendência)
    - MACD (momentum)
    - Volume (confirmação)
    - RSI e Estocástico (posicionamento)
    - Padrões de preço (rompimento, pullback, sweep, 3 candles)
    
    Args:
        df: DataFrame com dados OHLCV e indicadores
        signal: +1 (BUY) ou -1 (SELL)
        signal_data: Dict com scores dos indicadores
        timeframe: String do timeframe
    
    Returns:
        Dict com avaliação completa:
        - score: int (0-15+)
        - setup_type: str ('rompimento', 'pullback', etc.)
        - confirmations: list[str] (fatores a favor)
        - warnings: list[str] (riscos identificados)
        - volume_ratio, adx, rsi, body_ratio, signal_probability
    
    Examples:
        >>> evaluate_signal_setup(df, 1, signal_data, '5m')
        {
            'score': 9,
            'setup_type': 'rompimento / sweep',
            'confirmations': ['tendencia acima das EMAs 9/21', ...],
            'warnings': [],
            'volume_ratio': 1.45,
            'adx': 28.5,
            ...
        }
    """
    if len(df) < 30:
        return {
            'score': 0,
            'setup_type': 'indefinido',
            'confirmations': [],
            'warnings': ['historico insuficiente'],
        }

    # ═══════════════════════════════════════════════════════════════════
    # EXTRAÇÃO DE DADOS DO CANDLE ATUAL
    # ═══════════════════════════════════════════════════════════════════
    last_closed = df.iloc[-1]
    prev_closed = df.iloc[-2]
    recent_window = df.tail(21)
    
    close = float(last_closed['close'])
    open_price = float(last_closed['open'])
    high = float(last_closed['high'])
    low = float(last_closed['low'])
    prev_high = float(prev_closed['high'])
    prev_low = float(prev_closed['low'])
    
    candle_range = max(high - low, 1e-9)
    body_ratio = abs(close - open_price) / candle_range
    upper_wick_ratio = (high - max(open_price, close)) / candle_range
    lower_wick_ratio = (min(open_price, close) - low) / candle_range

    # ═══════════════════════════════════════════════════════════════════
    # INDICADORES TÉCNICOS
    # ═══════════════════════════════════════════════════════════════════
    ema_short = float(last_closed.get(f"ema_{config.INDICATORS_CONFIG['EMA_SHORT']['period']}", close))
    ema_long = float(last_closed.get(f"ema_{config.INDICATORS_CONFIG['EMA_LONG']['period']}", close))
    prev_ema_short = float(prev_closed.get(f"ema_{config.INDICATORS_CONFIG['EMA_SHORT']['period']}", ema_short))
    bb_middle = float(last_closed.get('bb_middle', close))
    
    macd = float(last_closed.get('macd', 0.0))
    macd_signal = float(last_closed.get('macd_signal', 0.0))
    macd_diff = float(last_closed.get('macd_diff', 0.0))
    prev_macd_diff = float(prev_closed.get('macd_diff', macd_diff))
    
    rsi = float(last_closed.get('rsi', 50.0))
    adx = float(last_closed.get('adx', 0.0))
    adx_pos = float(last_closed.get('adx_pos', 0.0))
    adx_neg = float(last_closed.get('adx_neg', 0.0))
    
    stoch_k = float(last_closed.get('stoch_k', 50.0))
    stoch_d = float(last_closed.get('stoch_d', 50.0))
    
    volume = float(last_closed.get('volume', 0.0))
    volume_ma = float(last_closed.get('volume_ma', volume))
    volume_ratio = _safe_ratio(volume, volume_ma, default=1.0)

    # ═══════════════════════════════════════════════════════════════════
    # NÍVEIS ESTRUTURAIS
    # ═══════════════════════════════════════════════════════════════════
    recent_breakout_high = float(recent_window['high'].iloc[:-1].max()) if len(recent_window) > 1 else high
    recent_breakout_low = float(recent_window['low'].iloc[:-1].min()) if len(recent_window) > 1 else low
    
    recent_low_now = float(df['low'].tail(6).min())
    previous_low_block = float(df['low'].iloc[-12:-6].min()) if len(df) >= 12 else recent_low_now
    recent_high_now = float(df['high'].tail(6).max())
    previous_high_block = float(df['high'].iloc[-12:-6].max()) if len(df) >= 12 else recent_high_now
    
    last_fractal_high = _last_fractal_level(df.iloc[:-1], 'high') if len(df) > 5 else None
    last_fractal_low = _last_fractal_level(df.iloc[:-1], 'low') if len(df) > 5 else None

    # ═══════════════════════════════════════════════════════════════════
    # PADRÕES DE PREÇO
    # ═══════════════════════════════════════════════════════════════════
    three_candle_match, three_candle_desc = _three_candle_confirmation(df, signal)
    sweep_match, sweep_desc = _detect_sweep(df, signal)

    # ═══════════════════════════════════════════════════════════════════
    # AVALIAÇÃO POR DIREÇÃO
    # ═══════════════════════════════════════════════════════════════════
    setup_score = 0
    confirmations = []
    warnings = []
    setup_tags = []

    if signal == 1:  # BUY
        # Condições técnicas
        trend_ok = close > ema_short > ema_long and ema_short >= prev_ema_short
        momentum_ok = macd > macd_signal and macd_diff >= prev_macd_diff
        regime_ok = adx >= 18 and adx_pos >= adx_neg
        volume_ok = volume_ratio >= 1.10
        rsi_ok = 48 <= rsi <= 68
        stoch_ok = stoch_k >= stoch_d and stoch_k <= 88
        higher_lows = recent_low_now > previous_low_block
        broke_recent_top = close > recent_breakout_high and body_ratio >= 0.55 and upper_wick_ratio <= 0.25
        broke_fractal_top = last_fractal_high is not None and close > last_fractal_high
        pulled_back_to_mean = (
            close > ema_short
            and low <= max(ema_short, bb_middle) * 1.002
            and lower_wick_ratio >= 0.25
        )

        # Pontuação
        if trend_ok:
            setup_score += 2
            confirmations.append('tendencia acima das EMAs 9/21')
        else:
            warnings.append('sem alinhamento limpo das EMAs')

        if regime_ok:
            setup_score += 1
            confirmations.append(f'ADX forte ({adx:.1f}) com DI+ dominante')
        else:
            warnings.append('tendencia fraca no ADX')

        if momentum_ok:
            setup_score += 2
            confirmations.append('MACD acelerando a favor da compra')
        else:
            warnings.append('MACD sem expansao suficiente')

        if volume_ok:
            setup_score += 1
            confirmations.append(f'volume acima da media ({volume_ratio:.2f}x)')

        if rsi_ok:
            setup_score += 1
            confirmations.append(f'RSI equilibrado para continuidade ({rsi:.1f})')
        else:
            warnings.append(f'RSI fora da faixa ideal ({rsi:.1f})')

        if stoch_ok:
            setup_score += 1
            confirmations.append('estocastico confirma impulso comprador')

        if higher_lows:
            setup_score += 1
            confirmations.append('fundos ascendentes no curto prazo')

        if broke_recent_top or broke_fractal_top:
            setup_score += 2
            setup_tags.append('rompimento')
            confirmations.append('rompimento confirmado de topo/resistencia')
        elif pulled_back_to_mean:
            setup_score += 2
            setup_tags.append('pullback')
            confirmations.append('pullback defendido na media curta')
        else:
            warnings.append('sem rompimento ou pullback tecnico claro')

        if sweep_match:
            setup_score += 2
            setup_tags.append('sweep')
            confirmations.append(sweep_desc)

        if three_candle_match:
            setup_score += 2
            setup_tags.append('3-candles')
            confirmations.append(f'padrao 3 candles: {three_candle_desc}')

        if upper_wick_ratio > 0.35 and close > recent_breakout_high:
            warnings.append('risco de falso rompimento por rejeicao superior')
            setup_score -= 2

    elif signal == -1:  # SELL
        # Condições técnicas
        trend_ok = close < ema_short < ema_long and ema_short <= prev_ema_short
        momentum_ok = macd < macd_signal and macd_diff <= prev_macd_diff
        regime_ok = adx >= 18 and adx_neg >= adx_pos
        volume_ok = volume_ratio >= 1.10
        rsi_ok = 32 <= rsi <= 52
        stoch_ok = stoch_k <= stoch_d and stoch_k >= 12
        lower_highs = recent_high_now < previous_high_block
        broke_recent_bottom = close < recent_breakout_low and body_ratio >= 0.55 and lower_wick_ratio <= 0.25
        broke_fractal_bottom = last_fractal_low is not None and close < last_fractal_low
        pulled_back_to_mean = (
            close < ema_short
            and high >= min(ema_short, bb_middle) * 0.998
            and upper_wick_ratio >= 0.25
        )

        # Pontuação
        if trend_ok:
            setup_score += 2
            confirmations.append('tendencia abaixo das EMAs 9/21')
        else:
            warnings.append('sem alinhamento limpo das EMAs')

        if regime_ok:
            setup_score += 1
            confirmations.append(f'ADX forte ({adx:.1f}) com DI- dominante')
        else:
            warnings.append('tendencia fraca no ADX')

        if momentum_ok:
            setup_score += 2
            confirmations.append('MACD acelerando a favor da venda')
        else:
            warnings.append('MACD sem expansao suficiente')

        if volume_ok:
            setup_score += 1
            confirmations.append(f'volume acima da media ({volume_ratio:.2f}x)')

        if rsi_ok:
            setup_score += 1
            confirmations.append(f'RSI equilibrado para continuidade ({rsi:.1f})')
        else:
            warnings.append(f'RSI fora da faixa ideal ({rsi:.1f})')

        if stoch_ok:
            setup_score += 1
            confirmations.append('estocastico confirma impulso vendedor')

        if lower_highs:
            setup_score += 1
            confirmations.append('topos descendentes no curto prazo')

        if broke_recent_bottom or broke_fractal_bottom:
            setup_score += 2
            setup_tags.append('rompimento')
            confirmations.append('rompimento confirmado de fundo/suporte')
        elif pulled_back_to_mean:
            setup_score += 2
            setup_tags.append('pullback')
            confirmations.append('pullback rejeitado na media curta')
        else:
            warnings.append('sem rompimento ou pullback tecnico claro')

        if sweep_match:
            setup_score += 2
            setup_tags.append('sweep')
            confirmations.append(sweep_desc)

        if three_candle_match:
            setup_score += 2
            setup_tags.append('3-candles')
            confirmations.append(f'padrao 3 candles: {three_candle_desc}')

        if lower_wick_ratio > 0.35 and close < recent_breakout_low:
            warnings.append('risco de falso rompimento por rejeicao inferior')
            setup_score -= 2

    # ═══════════════════════════════════════════════════════════════════
    # RESULTADO FINAL
    # ═══════════════════════════════════════════════════════════════════
    setup_type = ' / '.join(setup_tags) if setup_tags else 'continuidade'
    setup_score = max(setup_score, 0)

    return {
        'score': int(setup_score),
        'setup_type': setup_type,
        'confirmations': confirmations[:4],  # Top 4
        'warnings': warnings[:3],  # Top 3
        'volume_ratio': volume_ratio,
        'adx': adx,
        'rsi': rsi,
        'body_ratio': body_ratio,
        'signal_probability': float(signal_data.get('probability', 0.0)),
    }


def signal_quality_consensus(signal_data: dict, signal: int) -> int:
    """
    Conta quantos indicadores direcionais concordam com o sinal.
    
    Indicadores considerados:
    - RSI score
    - MACD score
    - EMA score
    - Bollinger score
    
    Args:
        signal_data: Dict com scores dos indicadores
        signal: +1 (BUY) ou -1 (SELL)
    
    Returns:
        Número de indicadores em consenso (0-4)
    
    Examples:
        >>> signal_quality_consensus({'rsi_score': 0.8, 'macd_score': 0.6, 'ema_score': 0.5, 'bollinger_score': -0.2}, 1)
        3  # RSI, MACD, EMA concordam com BUY
        >>> signal_quality_consensus({'rsi_score': -0.7, 'macd_score': -0.5}, -1)
        2  # RSI e MACD concordam com SELL
    """
    directional_scores = [
        float(signal_data.get('rsi_score', 0.0)),
        float(signal_data.get('macd_score', 0.0)),
        float(signal_data.get('ema_score', 0.0)),
        float(signal_data.get('bollinger_score', 0.0)),
    ]
    
    if signal == 1:  # BUY: scores positivos
        return sum(1 for s in directional_scores if s > 0)
    
    if signal == -1:  # SELL: scores negativos
        return sum(1 for s in directional_scores if s < 0)
    
    return 0


def is_false_breakout_risk(df: pd.DataFrame, signal: int, timeframe: str) -> bool:
    """
    Filtro simples para evitar entrada em possível falso rompimento no M5+.
    
    Args:
        df: DataFrame com dados OHLCV
        signal: +1 (BUY) ou -1 (SELL)
        timeframe: String do timeframe
    
    Returns:
        True se há risco de falso rompimento
    
    Examples:
        >>> is_false_breakout_risk(df, 1, '5m')
        True  # Rompimento com corpo fraco ou rejeição forte
        >>> is_false_breakout_risk(df, 1, '1m')
        False  # Não aplica em 1m
    """
    from src.domain.utils.time_utils import timeframe_to_minutes
    
    if timeframe_to_minutes(timeframe) < 5 or len(df) < 4:
        return False

    # Usa candles fechados para reduzir ruído
    last_closed = df.iloc[-2]
    prev_closed = df.iloc[-3]

    o = float(last_closed['open'])
    h = float(last_closed['high'])
    l = float(last_closed['low'])
    c = float(last_closed['close'])

    candle_range = max(h - l, 1e-9)
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    body_ratio = body / candle_range
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range

    # Rompimento recente do candle anterior
    broke_up = c > float(prev_closed['high'])
    broke_down = c < float(prev_closed['low'])

    if signal == 1:
        # Compra após rompimento com corpo fraco ou forte rejeição superior tende a falhar
        if (broke_up and body_ratio < 0.45) or upper_wick_ratio > 0.45:
            return True
            
    elif signal == -1:
        # Venda após rompimento com corpo fraco ou forte rejeição inferior tende a falhar
        if (broke_down and body_ratio < 0.45) or lower_wick_ratio > 0.45:
            return True

    return False
