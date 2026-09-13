from __future__ import annotations
from src.core.lot_defense import Candle, Lot, DefenseType, ActiveDefenseLevel
from src.core.defenses.resolver import OpeningWickResolver

class FirstRegisterDefenseBuilder:
    """Constrói a Defesa 4: 4ª 1º Registro (Ponta do Pavio)."""
    
    def build(self, lot: Lot, candles: list[Candle]) -> tuple[ActiveDefenseLevel, ...]:
        wick = OpeningWickResolver.get_relevant_wick(lot.reference_candle, lot.side)
        if wick is not None:
            return (
                ActiveDefenseLevel(
                    defense_type=DefenseType.PRIMEIRO_REGISTRO,
                    side=lot.side,
                    price_level=wick,
                    reference_index=lot.reference_index
                ),
            )
        return ()
