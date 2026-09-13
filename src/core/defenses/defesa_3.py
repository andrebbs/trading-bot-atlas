from __future__ import annotations
from src.core.lot_defense import Candle, Lot, DefenseType, ActiveDefenseLevel

class CommandCandleDefenseBuilder:
    """Constrói a Defesa 3: 3ª Vela de Comando (Abertura)."""
    
    def build(self, lot: Lot, candles: list[Candle]) -> tuple[ActiveDefenseLevel, ...]:
        return (
            ActiveDefenseLevel(
                defense_type=DefenseType.VELA_DE_COMANDO,
                side=lot.side,
                price_level=lot.reference_candle.open,
                reference_index=lot.reference_index
            ),
        )
