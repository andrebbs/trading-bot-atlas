from __future__ import annotations
from decimal import Decimal
from src.core.lot_defense import Candle, LotSide

class OpeningWickResolver:
    """Resolve o pavio relevante considerando o lado do lote (compra ou venda)."""
    
    @staticmethod
    def get_relevant_wick(candle: Candle, side: LotSide) -> Decimal | None:
        if side is LotSide.BUY:
            return candle.low if candle.low < candle.open else None
        return candle.high if candle.high > candle.open else None
