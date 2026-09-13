from __future__ import annotations
from src.core.lot_defense import Candle, Lot, DefenseType, ActiveDefenseLevel
from src.core.defenses.resolver import OpeningWickResolver

class LotCandleDefenseBuilder:
    """Constrói a Defesa 1: 1ª Vela do Lote (Abertura e Pavio da Abertura)."""
    
    def build(self, lot: Lot, candles: list[Candle]) -> tuple[ActiveDefenseLevel, ...]:
        candle = lot.reference_candle
        levels = [
            ActiveDefenseLevel(
                defense_type=DefenseType.VELA_DO_LOTE,
                side=lot.side,
                price_level=candle.open,
                reference_index=lot.reference_index
            )
        ]
        wick = OpeningWickResolver.get_relevant_wick(candle, lot.side)
        if wick is not None and wick != candle.open:
            levels.append(
                ActiveDefenseLevel(
                    defense_type=DefenseType.VELA_DO_LOTE,
                    side=lot.side,
                    price_level=wick,
                    reference_index=lot.reference_index
                )
            )
        return tuple(levels)
