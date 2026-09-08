"""ATLAS Crypto IDX — Rejection Strategy.

Implements the user-provided "ATLAS — OPERACIONAL CRYPTO IDX | REJEIÇÃO"
specification: a dedicated support/resistance rejection engine for the
Stockity Crypto IDX asset, distinct from the multi-technique ATLAS
confluence scanner used for other symbols.

Pipeline (mandatory order, per spec):
    M5 CONTEXT -> REGION (support/resistance) -> M1 REJECTION -> ENTRY

Core ideas encoded here:
- M5 candles establish trend context (bullish/bearish/lateral) and
  candidate support/resistance regions (swing highs/lows that price has
  reacted to more than once).
- M1 candles are scanned for a rejection pattern at those regions: price
  approaches/attempts to break the region, fails to sustain the break,
  and returns — evaluated using wick size, close position, and follow-
  through of the next candle(s), not a lone wick or a single red/green
  candle.
- Signals are graded A/B/C (quality) and mapped to an action
  (ENTRAR/AGUARDAR/NÃO OPERAR) per the spec's hierarchy and "golden rule"
  (never treat "wick = entry"; only "region + attempt + failure +
  return = rejection").

This module is intentionally data-source agnostic: it only consumes
``Candle`` objects (see ``src.core.stockity_market_data.Candle``), so it
can be reused/tested without live network calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional

from src.core.stockity_market_data import Candle

Context = Literal["ALTA", "BAIXA", "LATERAL"]
Region = Literal["SUPORTE", "RESISTENCIA", "NENHUMA"]
RejectionState = Literal["SIM", "NAO", "EM_FORMACAO"]
Direction = Literal["CALL", "PUT", "NEUTRO"]
Quality = Literal["A", "B", "C"]
Action = Literal["ENTRAR", "AGUARDAR", "NAO_OPERAR"]


@dataclass
class RejectionSignal:
    asset: str
    context_m5: Context
    region: Region
    region_price: Optional[float]
    rejection: RejectionState
    direction: Direction
    quality: Quality
    action: Action
    justification: str

    def format_message(self) -> str:
        action_label = {
            "ENTRAR": "ENTRAR",
            "AGUARDAR": "AGUARDAR",
            "NAO_OPERAR": "NÃO OPERAR",
        }[self.action]
        region_label = {
            "SUPORTE": "SUPORTE",
            "RESISTENCIA": "RESISTÊNCIA",
            "NENHUMA": "NENHUMA",
        }[self.region]
        rejection_label = {"SIM": "SIM", "NAO": "NÃO", "EM_FORMACAO": "EM FORMAÇÃO"}[self.rejection]
        return (
            f"*ATIVO:* {self.asset}\n"
            f"*CONTEXTO M5:* {self.context_m5}\n"
            f"*REGIÃO:* {region_label}\n"
            f"*REJEIÇÃO:* {rejection_label}\n"
            f"*DIREÇÃO:* {self.direction}\n"
            f"*QUALIDADE:* {self.quality}\n"
            f"*AÇÃO:* {action_label}\n"
            f"*JUSTIFICATIVA:* {self.justification}"
        )


def _swing_points(candles: List[Candle], window: int = 2) -> tuple[List[float], List[float]]:
    """Find local swing highs/lows (simple fractal: higher/lower than
    ``window`` neighbours on each side)."""
    highs: List[float] = []
    lows: List[float] = []
    n = len(candles)
    for i in range(window, n - window):
        seg = candles[i - window : i + window + 1]
        center = candles[i]
        if center.high == max(c.high for c in seg):
            highs.append(center.high)
        if center.low == min(c.low for c in seg):
            lows.append(center.low)
    return highs, lows


def _cluster_levels(levels: List[float], tolerance_pct: float = 0.0008) -> List[tuple[float, int]]:
    """Group nearby swing levels into regions; return (price, touch_count)
    sorted by touch_count desc. A region touched more than once is
    considered "already reacted" (spec section 5 — prioritize regions
    that already demonstrated price reaction)."""
    if not levels:
        return []
    sorted_levels = sorted(levels)
    clusters: List[List[float]] = [[sorted_levels[0]]]
    for lvl in sorted_levels[1:]:
        ref = clusters[-1][-1]
        if ref and abs(lvl - ref) / ref <= tolerance_pct:
            clusters[-1].append(lvl)
        else:
            clusters.append([lvl])
    result = [(sum(c) / len(c), len(c)) for c in clusters]
    result.sort(key=lambda t: t[1], reverse=True)
    return result


def _m5_context(m5_candles: List[Candle]) -> Context:
    """Determine M5 trend context from recent closes and swing structure
    (spec section 3/4: ascending/descending highs+lows => bullish/
    bearish structure)."""
    if len(m5_candles) < 6:
        return "LATERAL"
    recent = m5_candles[-12:] if len(m5_candles) >= 12 else m5_candles
    highs, lows = _swing_points(recent, window=1)
    closes = [c.close for c in recent]
    net_move = closes[-1] - closes[0]
    span = max(c.high for c in recent) - min(c.low for c in recent)
    if span == 0:
        return "LATERAL"
    trend_strength = net_move / span

    ascending_highs = len(highs) >= 2 and highs[-1] > highs[0]
    ascending_lows = len(lows) >= 2 and lows[-1] > lows[0]
    descending_highs = len(highs) >= 2 and highs[-1] < highs[0]
    descending_lows = len(lows) >= 2 and lows[-1] < lows[0]
    # No swing points found (e.g. a strictly monotonic run) still counts as
    # trend confirmation as long as net movement dominates the range.
    no_swing_data = not highs and not lows

    if trend_strength > 0.15 and (ascending_lows or ascending_highs or no_swing_data):
        return "ALTA"
    if trend_strength < -0.15 and (descending_highs or descending_lows or no_swing_data):
        return "BAIXA"
    return "LATERAL"


def _nearest_region(
    price: float, m5_candles: List[Candle], context: Context
) -> tuple[Region, Optional[float], int]:
    """Find the nearest relevant support/resistance region to the current
    price, per the context (spec section 3/4: PUT looks for resistance
    above during bearish/correction context; CALL looks for support below
    during bullish/correction context)."""
    highs, lows = _swing_points(m5_candles, window=1)
    resistances = _cluster_levels(highs)
    supports = _cluster_levels(lows)

    # Candidate regions within a reasonable distance of current price.
    def _closest(levels: List[tuple[float, int]], above: bool) -> Optional[tuple[float, int]]:
        candidates = [
            (lvl, touches)
            for lvl, touches in levels
            if (lvl >= price if above else lvl <= price)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda t: abs(t[0] - price))
        return candidates[0]

    nearest_resistance = _closest(resistances, above=True)
    nearest_support = _closest(supports, above=False)

    # Choose whichever region is operationally closer (spec section 6:
    # don't operate in the middle of the range).
    dist_r = abs(nearest_resistance[0] - price) / price if nearest_resistance else None
    dist_s = abs(nearest_support[0] - price) / price if nearest_support else None

    PROXIMITY_THRESHOLD = 0.003  # 0.3% — "near the region" cutoff

    if dist_r is not None and (dist_s is None or dist_r <= dist_s) and dist_r <= PROXIMITY_THRESHOLD:
        return "RESISTENCIA", nearest_resistance[0], nearest_resistance[1]
    if dist_s is not None and dist_s <= PROXIMITY_THRESHOLD:
        return "SUPORTE", nearest_support[0], nearest_support[1]
    return "NENHUMA", None, 0


def _detect_rejection(
    m1_candles: List[Candle], region: Region, region_price: float
) -> tuple[RejectionState, Direction, str]:
    """Scan the last few M1 candles for a rejection pattern at the region
    (spec section 2/3/4: attempt to break -> fail to sustain -> return ->
    loss of momentum). A single wick is NOT automatically a rejection."""
    if len(m1_candles) < 3:
        return "NAO", "NEUTRO", "dados M1 insuficientes para avaliar rejeição"

    last = m1_candles[-1]
    prev = m1_candles[-2]
    body_last = abs(last.close - last.open)
    range_last = last.high - last.low or 1e-9

    if region == "RESISTENCIA":
        attempted_break = max(last.high, prev.high) > region_price
        upper_wick = last.high - max(last.open, last.close)
        wick_ratio = upper_wick / range_last
        failed_to_sustain = last.close < region_price
        returning = last.close < prev.close or last.close < prev.open
        if attempted_break and failed_to_sustain and wick_ratio >= 0.3:
            if returning:
                return (
                    "SIM",
                    "PUT",
                    "preço testou/ultrapassou a resistência, deixou pavio superior relevante, "
                    "não sustentou o rompimento e retornou para dentro da região",
                )
            return (
                "EM_FORMACAO",
                "NEUTRO",
                "tentativa de rompimento da resistência com falha aparente, aguardando confirmação de retorno",
            )
        if attempted_break and not failed_to_sustain and body_last / range_last > 0.6:
            return (
                "NAO",
                "NEUTRO",
                "rompimento da resistência com força e permanência — possível rompimento verdadeiro, não operar contra",
            )
        return "NAO", "NEUTRO", "sem tentativa clara de rompimento da resistência ainda"

    if region == "SUPORTE":
        attempted_break = min(last.low, prev.low) < region_price
        lower_wick = min(last.open, last.close) - last.low
        wick_ratio = lower_wick / range_last
        failed_to_sustain = last.close > region_price
        returning = last.close > prev.close or last.close > prev.open
        if attempted_break and failed_to_sustain and wick_ratio >= 0.3:
            if returning:
                return (
                    "SIM",
                    "CALL",
                    "preço testou/rompeu o suporte, deixou pavio inferior relevante, "
                    "não sustentou abaixo da região e retornou para dentro dela",
                )
            return (
                "EM_FORMACAO",
                "NEUTRO",
                "tentativa de rompimento do suporte com falha aparente, aguardando confirmação de retorno",
            )
        if attempted_break and not failed_to_sustain and body_last / range_last > 0.6:
            return (
                "NAO",
                "NEUTRO",
                "rompimento do suporte com força e permanência — possível rompimento verdadeiro, não operar contra",
            )
        return "NAO", "NEUTRO", "sem tentativa clara de rompimento do suporte ainda"

    return "NAO", "NEUTRO", "preço fora de uma região relevante"


def _grade_quality(
    context: Context, region: Region, touches: int, rejection: RejectionState, direction: Direction
) -> tuple[Quality, Action]:
    """Apply the spec's A/B/C quality filter (section 11) and map to an
    action (section 14 — never force a signal; AGUARDAR/NÃO OPERAR are
    valid outcomes)."""
    if region == "NENHUMA" or rejection == "NAO" or direction == "NEUTRO" and rejection != "EM_FORMACAO":
        return "C", "NAO_OPERAR"

    context_favorable = (region == "RESISTENCIA" and context in {"BAIXA", "LATERAL"}) or (
        region == "SUPORTE" and context in {"ALTA", "LATERAL"}
    )

    if rejection == "SIM" and context_favorable and touches >= 2:
        return "A", "ENTRAR"
    if rejection == "SIM" and (context_favorable or touches >= 2):
        return "B", "AGUARDAR"
    if rejection == "EM_FORMACAO":
        return "B", "AGUARDAR"
    return "C", "NAO_OPERAR"


def analyze_rejection(
    m1_candles: List[Candle], m5_candles: List[Candle], asset: str = "Crypto IDX"
) -> RejectionSignal:
    """Run the full ATLAS Crypto IDX rejection pipeline:
    M5 CONTEXT -> REGION -> M1 REJECTION -> ENTRY.
    """
    if not m1_candles or not m5_candles:
        return RejectionSignal(
            asset=asset,
            context_m5="LATERAL",
            region="NENHUMA",
            region_price=None,
            rejection="NAO",
            direction="NEUTRO",
            quality="C",
            action="NAO_OPERAR",
            justification="dados insuficientes de candles M1/M5",
        )

    context = _m5_context(m5_candles)
    current_price = m1_candles[-1].close
    region, region_price, touches = _nearest_region(current_price, m5_candles, context)

    if region == "NENHUMA":
        return RejectionSignal(
            asset=asset,
            context_m5=context,
            region="NENHUMA",
            region_price=None,
            rejection="NAO",
            direction="NEUTRO",
            quality="C",
            action="NAO_OPERAR",
            justification="preço no meio da faixa, sem proximidade a região relevante de suporte/resistência",
        )

    rejection, direction, reason = _detect_rejection(m1_candles, region, region_price)
    quality, action = _grade_quality(context, region, touches, rejection, direction)

    return RejectionSignal(
        asset=asset,
        context_m5=context,
        region=region,
        region_price=region_price,
        rejection=rejection,
        direction=direction,
        quality=quality,
        action=action,
        justification=reason,
    )
