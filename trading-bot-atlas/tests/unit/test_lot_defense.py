"""Testes da formação de lotes do modo LOT_DEFENSE_MODE."""
from __future__ import annotations

from typing import Optional

from datetime import datetime, timedelta
from decimal import Decimal

from src.core.lot_defense import (
    BreakSituation,
    Candle,
    CandleDirection,
    DefenseSituation,
    Lot,
    LotReading,
    LotSide,
    LotStatus,
    build_lot_framework,
    detect_lots,
    detect_new_lot,
    evaluate_defense_candle,
    evaluate_lot_sequence,
    get_candle_direction,
    is_counter_trade_allowed,
    is_same_side_entry_allowed,
)


def candle(
    open_price: str,
    close_price: str,
    index: int,
    high_price: Optional[str] = None,
    low_price: Optional[str] = None,
) -> Candle:
    value_open = Decimal(open_price)
    value_close = Decimal(close_price)
    value_high = Decimal(high_price) if high_price is not None else max(value_open, value_close)
    value_low = Decimal(low_price) if low_price is not None else min(value_open, value_close)
    return Candle(
        timestamp=datetime(2026, 1, 1) + timedelta(minutes=index),
        open=value_open,
        high=value_high,
        low=value_low,
        close=value_close,
    )


def make_buy_lot(open_price: str, close_price: str, low_price: Optional[str] = None) -> Lot:
    """Lote de compra usando o exemplo numérico do documento (abre 100, fecha 110)."""

    reference = candle(open_price, close_price, 0, low_price=low_price)
    return Lot(id="buy-0", side=LotSide.BUY, reference_index=0, reference_candle=reference)


def test_identifies_buy_sell_and_doji() -> None:
    assert get_candle_direction(candle("1.00", "1.10", 0)) is CandleDirection.BUY
    assert get_candle_direction(candle("1.10", "1.00", 1)) is CandleDirection.SELL
    assert get_candle_direction(candle("1.00", "1.00", 2)) is CandleDirection.DOJI


def test_creates_buy_lot_after_sell() -> None:
    candles = [candle("2.00", "1.90", 0), candle("1.90", "2.10", 1)]

    lots = detect_lots(candles)

    assert len(lots) == 1
    assert lots[0].side is LotSide.BUY
    assert lots[0].reference_index == 1
    assert lots[0].reference_candle == candles[1]


def test_creates_sell_lot_after_buy() -> None:
    candles = [candle("2.00", "2.10", 0), candle("2.10", "1.90", 1)]

    lots = detect_lots(candles)

    assert len(lots) == 1
    assert lots[0].side is LotSide.SELL
    assert lots[0].reference_index == 1


def test_same_direction_does_not_create_additional_lot() -> None:
    candles = [
        candle("2.00", "2.10", 0),
        candle("2.10", "2.20", 1),
        candle("2.20", "2.30", 2),
    ]

    assert detect_lots(candles) == []


def test_doji_is_ignored_between_directional_candles() -> None:
    candles = [
        candle("2.00", "2.10", 0),
        candle("2.10", "2.10", 1),
        candle("2.10", "1.90", 2),
    ]

    lots = detect_lots(candles)

    assert len(lots) == 1
    assert lots[0].side is LotSide.SELL
    assert lots[0].reference_index == 2


def test_first_directional_candle_does_not_create_lot() -> None:
    candles = [candle("2.00", "2.10", 0)]

    assert detect_new_lot(candles, 0, []) is None


def test_lot_levels_match_documented_example() -> None:
    # Exemplo do documento: vela de comando verde abre 100, fecha 110, pavio 98.
    lot = make_buy_lot("100", "110", low_price="98")

    assert lot.command_level == Decimal("100")
    assert lot.confirmation_level == Decimal("110")
    assert lot.first_register == Decimal("98")


def test_lot_without_relevant_wick_has_no_first_register() -> None:
    lot = make_buy_lot("100", "110")

    assert lot.first_register is None


def test_situation_1_strong_rejection_when_wick_pierces_and_close_recovers_far() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    # Vela vermelha testa a região (pavio até 97) mas fecha com folga acima de 100.
    reaction = candle("104", "103", 1, low_price="97")

    evaluation = evaluate_defense_candle(lot, reaction)

    assert evaluation.reading is LotReading.TEST_PENDING_CONFIRMATION
    assert evaluation.defense_situation is DefenseSituation.STRONG_REJECTION


def test_situation_2_locked_at_open() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    # Vela vermelha fecha praticamente na abertura da vela de comando (100).
    reaction = candle("103", "100.02", 1, low_price="99.5")

    evaluation = evaluate_defense_candle(lot, reaction)

    assert evaluation.reading is LotReading.POSSIBLE_DEFENSE
    assert evaluation.defense_situation is DefenseSituation.LOCKED_AT_OPEN


def test_situation_3_wick_without_lock() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    # Testa o nível com pavio, mas fecha numa faixa intermediária (nem
    # travado no nível, nem com rejeição clara) — exige mais confirmação.
    reaction = candle("105", "102", 1, low_price="99")

    evaluation = evaluate_defense_candle(lot, reaction)

    assert evaluation.reading is LotReading.TEST_PENDING_CONFIRMATION
    assert evaluation.defense_situation is DefenseSituation.WICK_WITHOUT_LOCK


def test_situation_not_tested_keeps_possible_defense() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    reaction = candle("108", "105", 1)  # não chega perto de 100

    evaluation = evaluate_defense_candle(lot, reaction)

    assert evaluation.reading is LotReading.POSSIBLE_DEFENSE
    assert evaluation.defense_situation is None


def test_sell_situation_1_close_below_command_level() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    # Fecha abaixo de 100, mas ainda não perde o primeiro registro (98).
    reaction = candle("102", "99", 1, low_price="98.5")

    evaluation = evaluate_defense_candle(lot, reaction)

    assert evaluation.reading is LotReading.LOSS_ALERT
    assert evaluation.break_situation is BreakSituation.CLOSE_BELOW_COMMAND_LEVEL


def test_sell_situation_2_close_below_first_register() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    # Fecha abaixo do primeiro registro (98), perda de mais de uma referência.
    reaction = candle("101", "97", 1, low_price="96")

    evaluation = evaluate_defense_candle(lot, reaction)

    assert evaluation.reading is LotReading.LOSS_ALERT
    assert evaluation.break_situation is BreakSituation.CLOSE_BELOW_FIRST_REGISTER


def test_sequence_invalidates_lot_on_confirmed_continuation_without_recovery() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    following = [
        candle("102", "99", 1, low_price="98.5"),  # rompe, fecha abaixo de 100
        candle("99", "97", 2),  # continua sem recuperar 100
    ]

    evaluations = evaluate_lot_sequence(lot, following)

    assert evaluations[0].reading is LotReading.LOSS_ALERT
    assert evaluations[1].reading is LotReading.INVALIDATED
    assert evaluations[1].break_situation is BreakSituation.CONFIRMED_CONTINUATION
    assert lot.status is LotStatus.INVALIDATED
    assert is_counter_trade_allowed(lot) is True
    assert is_same_side_entry_allowed(lot) is False


def test_sequence_reverts_to_waiting_retest_on_recovery() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    following = [
        candle("102", "99", 1, low_price="98.5"),  # rompe, fecha abaixo de 100
        candle("99", "103", 2),  # recupera acima de 100
    ]

    evaluations = evaluate_lot_sequence(lot, following)

    assert evaluations[0].reading is LotReading.LOSS_ALERT
    assert evaluations[1].reading is LotReading.POSSIBLE_DEFENSE
    assert lot.status is LotStatus.WAITING_RETEST
    assert is_counter_trade_allowed(lot) is False
    assert is_same_side_entry_allowed(lot) is True


def test_counter_trade_blocked_while_lot_active() -> None:
    lot = make_buy_lot("100", "110", low_price="98")

    assert is_counter_trade_allowed(lot) is False
    assert is_same_side_entry_allowed(lot) is True


def test_sell_lot_mirrors_buy_lot_levels() -> None:
    reference = candle("110", "100", 0, high_price="112")
    lot = Lot(id="sell-0", side=LotSide.SELL, reference_index=0, reference_candle=reference)

    assert lot.command_level == Decimal("110")
    assert lot.confirmation_level == Decimal("100")
    assert lot.first_register == Decimal("112")


def test_framework_requires_three_observed_defenses_before_review() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    following = [
        candle("104", "103", 1, low_price="97"),
        candle("103", "102", 2),
    ]

    framework = build_lot_framework(lot, following)

    assert framework.defense_count == 5
    assert framework.eligible_for_review is True
    assert "primeiro_registro" in framework.observed_defenses
    assert "taxa_dividida" in framework.observed_defenses


def test_framework_blocks_review_after_confirmed_invalidation() -> None:
    lot = make_buy_lot("100", "110", low_price="98")
    following = [
        candle("102", "99", 1, low_price="98.5"),
        candle("99", "97", 2),
    ]

    evaluations = evaluate_lot_sequence(lot, following)
    framework = build_lot_framework(lot, following, evaluations)

    assert lot.status is LotStatus.INVALIDATED
    assert framework.eligible_for_review is False
    assert "rejeicao_nas_defesas" in framework.blocked_filters


# ── TESTES DOS 4 QUADRANTES (AULAS 1 A 20) ───────────────────────────────────

from src.core.lot_defense import (
    LotDefenseAnalyzer,
    DefenseType,
    ActiveDefenseLevel,
)


def test_analyzer_detects_wick_removal_hidden_command() -> None:
    """Aula 17 e 19: Retirada de pavio simétrico gera leitura de gráfico oculto."""
    analyzer = LotDefenseAnalyzer(symbol="EURUSD", min_defenses=3)
    # Candles 0 e 1 com a mesma máxima (pavio superior simétrico anulado)
    c0 = candle("1.0800", "1.0820", 0, high_price="1.0830", low_price="1.0800")
    c1 = candle("1.0820", "1.0810", 1, high_price="1.0830", low_price="1.0805")

    removed, hidden = analyzer._apply_wick_removal([c0, c1])
    assert 0 in removed
    assert 1 in removed
    assert len(hidden) >= 1


def test_signal_requires_minimum_three_distinct_defenses() -> None:
    """Regra de ouro: Junte pelo menos 3 defesas para ter um gatilho de entrada."""
    analyzer = LotDefenseAnalyzer(symbol="EURUSD", min_defenses=3)

    # 1. Vela de comando verde (abre 1.0800 sem pavio inferior)
    c0 = candle("1.0800", "1.0820", 0, high_price="1.0825", low_price="1.0800")
    # 2. Continuação de alta formando taxa dividida em 1.0820
    c1 = candle("1.0820", "1.0840", 1, high_price="1.0840", low_price="1.0820")

    lots = detect_lots([c0, c1])
    # 3. Vela vermelha desce e trava perfeitamente na taxa
    c2 = candle("1.0835", "1.0800", 2, high_price="1.0835", low_price="1.0799")

    # Adicionar nível para totalizar 3 defesas confluentes
    analyzer.active_levels.extend([
        ActiveDefenseLevel(defense_type=DefenseType.VELA_DO_LOTE, side=LotSide.BUY, price_level=Decimal("1.0800"), reference_index=0),
        ActiveDefenseLevel(defense_type=DefenseType.VELA_DE_COMANDO, side=LotSide.BUY, price_level=Decimal("1.0800"), reference_index=0),
        ActiveDefenseLevel(defense_type=DefenseType.TAXA_DIVIDIDA, side=LotSide.BUY, price_level=Decimal("1.0800"), reference_index=1),
    ])

    signal = analyzer.evaluate_last_candle_for_signal([c0, c1, c2], lots)
    assert signal is not None
    assert signal.action is LotSide.BUY
    assert signal.defense_count >= 3
    assert "SINAL LÓGICA DO PREÇO" in signal.message
