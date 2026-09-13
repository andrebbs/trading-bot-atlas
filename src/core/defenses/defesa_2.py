from __future__ import annotations
from src.core.lot_defense import Candle, Lot, DefenseType, ActiveDefenseLevel, CandleDirection
from src.core.defenses.resolver import OpeningWickResolver

class NewPositionDefenseBuilder:
    """Constrói a Defesa 2: 2ª Nova Posição (Abertura e Pavio da Abertura)."""
    
    def build(self, lot: Lot, candles: list[Candle]) -> tuple[ActiveDefenseLevel, ...]:
        target_dir = CandleDirection(lot.side.value)
        for idx in range(lot.reference_index + 1, len(candles)):
            c = candles[idx]
            if c.close > c.open:
                c_dir = CandleDirection.BUY
            elif c.close < c.open:
                c_dir = CandleDirection.SELL
            else:
                c_dir = CandleDirection.DOJI
                
            if c_dir is target_dir:
                levels = [
                    ActiveDefenseLevel(
                        defense_type=DefenseType.NOVA_POSICAO,
                        side=lot.side,
                        price_level=c.open,
                        reference_index=idx
                    )
                ]
                wick = OpeningWickResolver.get_relevant_wick(c, lot.side)
                if wick is not None and wick != c.open:
                    levels.append(
                        ActiveDefenseLevel(
                            defense_type=DefenseType.NOVA_POSICAO,
                            side=lot.side,
                            price_level=wick,
                            reference_index=idx
                        )
                    )
                return tuple(levels)
        return ()
