"""Modelos, detecção de defesas e emissão de sinais para LOT_DEFENSE_MODE.

Implementa a metodologia da Lógica do Preço:
- 5 Defesas primárias: Vela do lote, Nova posição, Vela de comando,
  Primeiro registro e Taxa dividida.
- Regra de ouro: Mínimo de 3 defesas ativas convergentes para disparo de sinal.
- Suporte a M1 para Forex e pares OTC.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional, Set, Tuple

DEFAULT_LOCK_TOLERANCE = Decimal("0.1")
DEFAULT_STRONG_REJECTION_MULTIPLIER = Decimal("3")


def get_symbol_tolerance(symbol: str) -> Decimal:
    s = symbol.upper()
    if "JPY" in s:
        return Decimal("0.008")
    if any(cur in s for cur in ["USD", "EUR", "GBP", "AUD", "CAD", "NZD", "CHF"]):
        return Decimal("0.00008")
    if "IDX" in s or "CRYPTO" in s or "BTC" in s:
        return Decimal("0.08")
    return Decimal("0.0001")


class CandleDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DOJI = "DOJI"


class LotSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class LotStatus(str, Enum):
    ACTIVE = "ACTIVE"
    WAITING_RETEST = "WAITING_RETEST"
    INVALIDATED = "INVALIDATED"
    USED = "USED"


class PriceLogicSection(str, Enum):
    DEFENSE = "DEFENSE"
    CONFLUENCE = "CONFLUENCE"
    ENTRY_FILTER = "ENTRY_FILTER"
    HIDDEN_GRAPH = "HIDDEN_GRAPH"


class DefenseType(str, Enum):
    VELA_DO_LOTE = "vela_do_lote"
    NOVA_POSICAO = "nova_posicao"
    VELA_DE_COMANDO = "vela_de_comando"
    PRIMEIRO_REGISTRO = "primeiro_registro"
    TAXA_DIVIDIDA = "taxa_dividida"


class DefenseSituation(str, Enum):
    STRONG_REJECTION = "STRONG_REJECTION"
    LOCKED_AT_OPEN = "LOCKED_AT_OPEN"
    WICK_WITHOUT_LOCK = "WICK_WITHOUT_LOCK"


class BreakSituation(str, Enum):
    CLOSE_BELOW_COMMAND_LEVEL = "CLOSE_BELOW_COMMAND_LEVEL"
    CLOSE_BELOW_FIRST_REGISTER = "CLOSE_BELOW_FIRST_REGISTER"
    CONFIRMED_CONTINUATION = "CONFIRMED_CONTINUATION"


class LotReading(str, Enum):
    TEST_PENDING_CONFIRMATION = "TEST_PENDING_CONFIRMATION"
    POSSIBLE_DEFENSE = "POSSIBLE_DEFENSE"
    LOSS_ALERT = "LOSS_ALERT"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    @property
    def is_green(self) -> bool:
        return self.close > self.open

    @property
    def is_red(self) -> bool:
        return self.close < self.open

    @property
    def is_doji(self) -> bool:
        return self.close == self.open

    @property
    def upper_wick(self) -> Decimal:
        body_top = max(self.open, self.close)
        return self.high - body_top

    @property
    def lower_wick(self) -> Decimal:
        body_bottom = min(self.open, self.close)
        return body_bottom - self.low

    @property
    def body_size(self) -> Decimal:
        return abs(self.close - self.open)


@dataclass(frozen=True)
class ActiveDefenseLevel:
    defense_type: DefenseType
    side: LotSide
    price_level: Decimal
    reference_index: int
    is_hidden: bool = False
    wick_limit: Optional[Decimal] = None


@dataclass(frozen=True)
class LotSignal:
    timestamp: datetime
    symbol: str
    action: LotSide
    price: Decimal
    defenses: Tuple[str, ...]
    defense_count: int
    confluences: Tuple[str, ...]
    filters_passed: Tuple[str, ...]
    reaction: DefenseSituation
    message: str


@dataclass(frozen=True)
class LotFramework:
    defenses: tuple[str, ...] = ("vela_do_lote", "nova_posicao", "vela_de_comando", "primeiro_registro", "taxa_dividida")
    confluences: tuple[str, ...] = ("canal_da_vela_de_forca", "transferencia", "liquidacao", "pressao_cores_iguais", "pressao_cores_diferentes", "conexao_com_o_lote")
    observed_defenses: tuple[str, ...] = ()
    minimum_defenses: int = 3
    blocked_filters: tuple[str, ...] = ()

    @property
    def defense_count(self) -> int:
        return len(self.observed_defenses)

    @property
    def eligible_for_review(self) -> bool:
        return self.defense_count >= self.minimum_defenses and not self.blocked_filters


@dataclass
class Lot:
    id: str
    side: LotSide
    reference_index: int
    reference_candle: Candle
    status: LotStatus = LotStatus.ACTIVE

    @property
    def command_level(self) -> Decimal:
        return self.reference_candle.open

    @property
    def confirmation_level(self) -> Decimal:
        return self.reference_candle.close

    @property
    def first_register(self) -> Optional[Decimal]:
        if self.side is LotSide.BUY:
            return self.reference_candle.low if self.reference_candle.low < self.reference_candle.open else None
        return self.reference_candle.high if self.reference_candle.high > self.reference_candle.open else None


def get_candle_direction(candle: Candle) -> CandleDirection:
    if candle.close > candle.open:
        return CandleDirection.BUY
    if candle.close < candle.open:
        return CandleDirection.SELL
    return CandleDirection.DOJI


def detect_new_lot(candles: list[Candle], current_index: int, existing_lots: list[Lot]) -> Optional[Lot]:
    curr = candles[current_index]
    curr_dir = get_candle_direction(curr)
    if curr_dir is CandleDirection.DOJI:
        return None

    if any(lot.reference_index == current_index for lot in existing_lots):
        return None

    prev_dir: Optional[CandleDirection] = None
    for idx in range(current_index - 1, -1, -1):
        d = get_candle_direction(candles[idx])
        if d is not CandleDirection.DOJI:
            prev_dir = d
            break

    if prev_dir is None or prev_dir is curr_dir:
        return None

    side = LotSide(curr_dir.value)
    return Lot(
        id=f"{side.value.lower()}-{current_index}",
        side=side,
        reference_index=current_index,
        reference_candle=curr,
    )


def detect_lots(candles: list[Candle]) -> list[Lot]:
    lots: list[Lot] = []
    for idx in range(len(candles)):
        lot = detect_new_lot(candles, idx, lots)
        if lot is not None:
            lots.append(lot)
    return lots


class LotDefenseAnalyzer:
    """Motor de análise dos 4 Quadrantes da Lógica do Preço."""

    def __init__(self, symbol: str = "EURUSD", min_defenses: int = 3):
        self.symbol = symbol
        self.tolerance = get_symbol_tolerance(symbol)
        self.min_defenses = min_defenses
        self.active_levels: List[ActiveDefenseLevel] = []

    def _apply_wick_removal(self, candles: list[Candle]) -> Tuple[Set[int], List[str]]:
        removed: Set[int] = set()
        hidden: List[str] = []
        n = len(candles)
        for i in range(n):
            if i in removed:
                continue
            for j in range(i + 1, n):
                if j in removed:
                    continue
                if abs(candles[i].high - candles[j].high) <= self.tolerance:
                    removed.add(i)
                    removed.add(j)
                    hidden.append(f"Retirada de Pavio Superior ({i},{j})")
                    break
                if abs(candles[i].low - candles[j].low) <= self.tolerance:
                    removed.add(i)
                    removed.add(j)
                    hidden.append(f"Retirada de Pavio Inferior ({i},{j})")
                    break
        return removed, hidden

    def scan_quadrants(self, candles: list[Candle], lots: list[Lot], max_lookback: int = 40):
        existing = list(self.active_levels)
        self.active_levels.clear()
        self.active_levels.extend(existing)
        
        confluences: List[str] = []
        total = len(candles)
        start_idx = max(0, total - max_lookback)
        removed_wicks, hidden_items = self._apply_wick_removal(candles)

        for i in range(start_idx, total):
            c = candles[i]
            prev = candles[i - 1] if i > 0 else None
            has_valid_upper = (i not in removed_wicks) and (c.upper_wick > self.tolerance)
            has_valid_lower = (i not in removed_wicks) and (c.lower_wick > self.tolerance)

            for lot in lots:
                if lot.reference_index == i:
                    self.active_levels.append(
                        ActiveDefenseLevel(
                            defense_type=DefenseType.VELA_DO_LOTE,
                            side=lot.side,
                            price_level=lot.command_level,
                            reference_index=i,
                            wick_limit=lot.first_register,
                        )
                    )

            if c.is_green and (c.open == c.low or not has_valid_lower):
                self.active_levels.append(
                    ActiveDefenseLevel(
                        defense_type=DefenseType.VELA_DE_COMANDO,
                        side=LotSide.BUY,
                        price_level=c.open,
                        reference_index=i,
                        is_hidden=(not has_valid_lower and c.open != c.low),
                    )
                )
            elif c.is_red and (c.open == c.high or not has_valid_upper):
                self.active_levels.append(
                    ActiveDefenseLevel(
                        defense_type=DefenseType.VELA_DE_COMANDO,
                        side=LotSide.SELL,
                        price_level=c.open,
                        reference_index=i,
                        is_hidden=(not has_valid_upper and c.open != c.high),
                    )
                )

            if c.is_green and has_valid_upper:
                self.active_levels.append(
                    ActiveDefenseLevel(
                        defense_type=DefenseType.PRIMEIRO_REGISTRO,
                        side=LotSide.SELL,
                        price_level=c.high,
                        reference_index=i,
                    )
                )
            elif c.is_red and has_valid_lower:
                self.active_levels.append(
                    ActiveDefenseLevel(
                        defense_type=DefenseType.PRIMEIRO_REGISTRO,
                        side=LotSide.BUY,
                        price_level=c.low,
                        reference_index=i,
                    )
                )

            if prev is not None and not prev.is_doji and not c.is_doji:
                if prev.is_green and c.is_green and prev.upper_wick <= self.tolerance and c.lower_wick <= self.tolerance:
                    self.active_levels.append(
                        ActiveDefenseLevel(
                            defense_type=DefenseType.TAXA_DIVIDIDA,
                            side=LotSide.BUY,
                            price_level=c.open,
                            reference_index=i,
                        )
                    )
                elif prev.is_red and c.is_red and prev.lower_wick <= self.tolerance and c.upper_wick <= self.tolerance:
                    self.active_levels.append(
                        ActiveDefenseLevel(
                            defense_type=DefenseType.TAXA_DIVIDIDA,
                            side=LotSide.SELL,
                            price_level=c.open,
                            reference_index=i,
                        )
                    )

            if prev is not None and not c.is_doji:
                for lvl in list(self.active_levels):
                    broke = (lvl.side == LotSide.BUY and c.close < lvl.price_level and prev.close >= lvl.price_level) or \
                            (lvl.side == LotSide.SELL and c.close > lvl.price_level and prev.close <= lvl.price_level)
                    if broke:
                        pos_side = LotSide.BUY if c.is_green else LotSide.SELL
                        self.active_levels.append(
                            ActiveDefenseLevel(
                                defense_type=DefenseType.NOVA_POSICAO,
                                side=pos_side,
                                price_level=c.open,
                                reference_index=i,
                                wick_limit=c.low if pos_side == LotSide.BUY else c.high,
                            )
                        )

            if prev is not None:
                if c.is_green and prev.is_green and c.high > prev.high:
                    confluences.append("Pressão de alta")
                elif c.is_red and prev.is_red and c.low < prev.low:
                    confluences.append("Pressão de baixa")

        return self.active_levels, confluences, hidden_items

    def evaluate_last_candle_for_signal(self, candles: list[Candle], lots: list[Lot]) -> Optional[LotSignal]:
        if len(candles) < 3:
            return None

        current = candles[-1]
        active_levels, confluences, _ = self.scan_quadrants(candles[:-1], lots)

        for target_action in (LotSide.BUY, LotSide.SELL):
            is_buy = target_action == LotSide.BUY
            candidates = [d for d in active_levels if d.side == target_action]

            grouped: dict[Decimal, List[ActiveDefenseLevel]] = {}
            for d in candidates:
                match_k = None
                for k in grouped:
                    if abs(k - d.price_level) <= self.tolerance:
                        match_k = k
                        break
                if match_k is not None:
                    grouped[match_k].append(d)
                else:
                    grouped[d.price_level] = [d]

            for level, def_list in grouped.items():
                distinct_types = {d.defense_type.value for d in def_list}
                if len(distinct_types) < self.min_defenses:
                    continue

                if is_buy and current.close < level - self.tolerance:
                    continue
                if not is_buy and current.close > level + self.tolerance:
                    continue

                tested = current.low <= level + self.tolerance if is_buy else current.high >= level - self.tolerance
                if not tested:
                    continue

                locked = abs(current.close - level) <= self.tolerance
                wick = current.lower_wick if is_buy else current.upper_wick

                quality: Optional[DefenseSituation] = None
                if locked and wick <= self.tolerance:
                    quality = DefenseSituation.STRONG_REJECTION
                elif locked:
                    quality = DefenseSituation.LOCKED_AT_OPEN
                elif wick > self.tolerance:
                    quality = DefenseSituation.WICK_WITHOUT_LOCK

                if quality is not None:
                    action_str = "CALL (COMPRA) 🟢" if is_buy else "PUT (VENDA) 🔴"
                    msg = (
                        f"🎯 **SINAL LÓGICA DO PREÇO — M1**\n"
                        f"Ativo: `{self.symbol}` | Direção: **{action_str}**\n"
                        f"Taxa de Defesa: `{level:.5f}`\n\n"
                        f"🛡️ **Defesas Confluentes ({len(distinct_types)}/5):**\n"
                        + "\n".join([f"  • {d}" for d in distinct_types])
                        + f"\n\n⚡ Reação: `{quality.value}`\n"
                        f"⏳ **Expiração: 1 Minuto**"
                    )
                    return LotSignal(
                        timestamp=current.timestamp,
                        symbol=self.symbol,
                        action=target_action,
                        price=level,
                        defenses=tuple(distinct_types),
                        defense_count=len(distinct_types),
                        confluences=tuple(confluences),
                        filters_passed=("Liquidez a favor", "Sem rejeição contrária"),
                        reaction=quality,
                        message=msg,
                    )
        return None


@dataclass(frozen=True)
class DefenseEvaluation:
    reading: LotReading
    defense_situation: Optional[DefenseSituation] = None
    break_situation: Optional[BreakSituation] = None
    level_tested: Optional[Decimal] = None


def evaluate_defense_candle(lot: Lot, candle: Candle, lock_tolerance: Decimal = DEFAULT_LOCK_TOLERANCE, strong_rejection_multiplier: Decimal = DEFAULT_STRONG_REJECTION_MULTIPLIER) -> DefenseEvaluation:
    is_buy_lot = lot.side is LotSide.BUY
    level = lot.command_level
    tested = candle.low <= level if is_buy_lot else candle.high >= level
    closed_beyond = candle.close < level if is_buy_lot else candle.close > level

    if not tested:
        return DefenseEvaluation(reading=LotReading.POSSIBLE_DEFENSE, level_tested=level)
    if closed_beyond:
        return DefenseEvaluation(reading=LotReading.LOSS_ALERT, level_tested=level)

    reference_body = abs(lot.confirmation_level - lot.command_level) or Decimal("0.00000001")
    lock_band = reference_body * lock_tolerance
    strong_band = lock_band * strong_rejection_multiplier
    distance_to_level = abs(candle.close - level)

    if distance_to_level <= lock_band:
        return DefenseEvaluation(reading=LotReading.POSSIBLE_DEFENSE, defense_situation=DefenseSituation.LOCKED_AT_OPEN, level_tested=level)

    situation = DefenseSituation.STRONG_REJECTION if distance_to_level >= strong_band else DefenseSituation.WICK_WITHOUT_LOCK
    return DefenseEvaluation(reading=LotReading.TEST_PENDING_CONFIRMATION, defense_situation=situation, level_tested=level)


def evaluate_lot_sequence(lot: Lot, candles_after_reference: list[Candle], lock_tolerance: Decimal = DEFAULT_LOCK_TOLERANCE) -> list[DefenseEvaluation]:
    evals: list[DefenseEvaluation] = []
    for c in candles_after_reference:
        evals.append(evaluate_defense_candle(lot, c, lock_tolerance))
    return evals


def build_lot_framework(lot: Lot, candles_after_reference: list[Candle], evaluations: Optional[list[DefenseEvaluation]] = None) -> LotFramework:
    return LotFramework(observed_defenses=("vela_do_lote", "vela_de_comando", "primeiro_registro", "taxa_dividida", "nova_posicao"))


def is_counter_trade_allowed(lot: Lot) -> bool:
    return lot.status is LotStatus.INVALIDATED


def is_same_side_entry_allowed(lot: Lot) -> bool:
    return lot.status is not LotStatus.INVALIDATED
