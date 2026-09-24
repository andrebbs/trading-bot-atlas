"""Testes do Setup Caixa Rápido (Wil Trader)."""
from __future__ import annotations

from typing import Optional

from datetime import datetime, timedelta
from decimal import Decimal

from src.core.caixa_rapido_setup import (
    CaixaRapidoAnalyzer,
    GapAnalysis,
    LockQuality,
    MarkSource,
    analyze_gap,
    classify_lock,
    detect_breakout,
    detect_lots_with_context,
    has_double_wick,
    has_liquidity_wick,
)
from src.core.lot_defense import Candle, LotSide


def candle(
    open_price: str,
    close_price: str,
    index: int,
    high_price: Optional[str] = None,
    low_price: Optional[str] = None,
) -> Candle:
    op = Decimal(open_price)
    cl = Decimal(close_price)
    hi = Decimal(high_price) if high_price is not None else max(op, cl)
    lo = Decimal(low_price) if low_price is not None else min(op, cl)
    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=index),
        open=op,
        high=hi,
        low=lo,
        close=cl,
    )


# ── Testes de detecção de lotes ─────────────────────────────────────────────

def test_detect_lots_groups_same_color_candles() -> None:
    candles = [
        candle("1.0800", "1.0810", 0),
        candle("1.0810", "1.0820", 1),
        candle("1.0820", "1.0815", 2),  # reversão
        candle("1.0815", "1.0805", 3),
    ]
    lots = detect_lots_with_context(candles)
    assert len(lots) == 2
    assert lots[0].side is LotSide.BUY
    assert lots[0].start_index == 0
    assert lots[0].end_index == 1
    assert lots[1].side is LotSide.SELL
    assert lots[1].start_index == 2
    assert lots[1].end_index == 3


def test_detect_lots_ignores_dojis() -> None:
    candles = [
        candle("1.0800", "1.0810", 0),
        candle("1.0810", "1.0810", 1),  # doji
        candle("1.0810", "1.0815", 2),
    ]
    lots = detect_lots_with_context(candles)
    assert len(lots) == 1
    assert lots[0].side is LotSide.BUY


# ── Testes de rompimento ─────────────────────────────────────────────────────

def test_detect_breakout_below_buy_lot_open() -> None:
    candles = [
        candle("1.0800", "1.0820", 0),
        candle("1.0820", "1.0815", 1),  # reversão inicia lote vendedor
        candle("1.0815", "1.0790", 2),  # rompe 1.0800 (abertura do lote comprador)
    ]
    lots = detect_lots_with_context(candles)
    buy_lot = lots[0]
    breakout = detect_breakout(buy_lot, candles)
    assert breakout is not None
    idx, brk_candle = breakout
    assert idx == 2
    assert brk_candle.close < buy_lot.primary_mark


# ── Testes de gap ────────────────────────────────────────────────────────────

def test_analyze_gap_no_gap_when_symmetric() -> None:
    c1 = candle("1.0800", "1.0820", 0)
    c2 = candle("1.0820", "1.0810", 1)
    gap = analyze_gap(c1, c2)
    assert not gap.has_gap


def test_analyze_gap_detects_upward_gap() -> None:
    c1 = candle("1.0800", "1.0810", 0)
    c2 = candle("1.0815", "1.0820", 1)  # abertura 5 pips acima do fechamento
    gap = analyze_gap(c1, c2)
    assert gap.has_gap
    assert gap.gap_direction is LotSide.BUY


# ── Testes de travamento ─────────────────────────────────────────────────────

def test_classify_lock_no_gap() -> None:
    prev = candle("1.0810", "1.0800", 0)
    conf = candle("1.0800", "1.0815", 1)
    quality, gap = classify_lock(conf, Decimal("1.0800"), prev)
    assert quality is LockQuality.LOCK_NO_GAP
    assert not gap.has_gap


def test_classify_lock_with_gap() -> None:
    prev = candle("1.0810", "1.0805", 0)
    conf = candle("1.0800", "1.0815", 1)  # abertura 5 pips abaixo do fechamento
    quality, gap = classify_lock(conf, Decimal("1.0800"), prev)
    assert quality is LockQuality.LOCK_WITH_GAP
    assert gap.has_gap


def test_classify_no_lock_when_open_far_from_mark() -> None:
    prev = candle("1.0810", "1.0805", 0)
    conf = candle("1.0850", "1.0860", 1)
    quality, _ = classify_lock(conf, Decimal("1.0800"), prev)
    assert quality in (LockQuality.NO_LOCK_NO_GAP, LockQuality.NO_LOCK_WITH_GAP)


# ── Testes de pavios ─────────────────────────────────────────────────────────

def test_liquidity_wick_for_buy_needs_lower_wick() -> None:
    c = candle("1.0810", "1.0820", 0, high_price="1.0822", low_price="1.0800")
    assert has_liquidity_wick(c, LotSide.BUY) is True


def test_liquidity_wick_for_sell_needs_upper_wick() -> None:
    c = candle("1.0820", "1.0810", 0, high_price="1.0830", low_price="1.0808")
    assert has_liquidity_wick(c, LotSide.SELL) is True


def test_double_wick_detected_in_confirmation() -> None:
    c = candle("1.0810", "1.0815", 0, high_price="1.0820", low_price="1.0805")
    assert has_double_wick(c) is True


def test_double_wick_absent_when_single_side_only() -> None:
    c = candle("1.0810", "1.0820", 0, high_price="1.0820", low_price="1.0810")
    assert has_double_wick(c) is False


# ── Teste integrado do sinal ─────────────────────────────────────────────────

def test_full_setup_generates_buy_signal() -> None:
    """Cenário completo: lote comprador -> rompimento -> conexão -> confirmação."""
    candles = [
        # Lote comprador (0-1)
        candle("1.0800", "1.0820", 0, high_price="1.0822", low_price="1.0798"),
        candle("1.0820", "1.0830", 1, high_price="1.0835", low_price="1.0818"),
        # Reversão + rompimento abaixo de 1.0800
        candle("1.0830", "1.0795", 2, high_price="1.0832", low_price="1.0790"),
        # 1ª vela após rompimento (marcação secundária = 1.0795)
        candle("1.0795", "1.0790", 3, high_price="1.0798", low_price="1.0788"),
        # Conexão: toca a marcação (1.0795) com pavio inferior (liquidez de compra)
        candle("1.0792", "1.0798", 4, high_price="1.0800", low_price="1.0785"),
        # Confirmação: trava na marcação, pavios nos dois lados, fecha a favor
        candle("1.0795", "1.0810", 5, high_price="1.0815", low_price="1.0790"),
        # Buffer
        candle("1.0810", "1.0812", 6),
    ]
    analyzer = CaixaRapidoAnalyzer(
        mark_tolerance=Decimal("0.0002"),
        gap_tolerance=Decimal("0.00003"),
        min_wick_ratio=Decimal("0.15"),
    )
    signal = analyzer.analyze(candles)
    assert signal is not None
    assert signal.action is LotSide.BUY
    assert signal.mark_source in (MarkSource.FIRST_CANDLE_AFTER_BREAKOUT, MarkSource.FIRST_LOT_CANDLE)
    assert signal.lock_quality in (LockQuality.LOCK_NO_GAP, LockQuality.LOCK_WITH_GAP)
    assert signal.expiration_minutes == 1
    assert "Conexao com pavio de liquidez" in signal.reason


def test_no_signal_when_confirmation_missing_double_wick() -> None:
    """Sem pavio nos dois lados na confirmação, não gera sinal."""
    candles = [
        candle("1.0800", "1.0820", 0),
        candle("1.0820", "1.0830", 1),
        candle("1.0830", "1.0795", 2),
        candle("1.0795", "1.0790", 3),
        candle("1.0792", "1.0798", 4, high_price="1.0800", low_price="1.0785"),
        # Confirmação sem pavio superior
        candle("1.0795", "1.0810", 5, high_price="1.0810", low_price="1.0795"),
        candle("1.0810", "1.0812", 6),
    ]
    analyzer = CaixaRapidoAnalyzer(require_double_wick_on_confirmation=True)
    signal = analyzer.analyze(candles)
    assert signal is None


def test_no_signal_when_not_enough_candles() -> None:
    analyzer = CaixaRapidoAnalyzer()
    assert analyzer.analyze([]) is None
    assert analyzer.analyze([candle("1.0", "1.1", 0)]) is None
