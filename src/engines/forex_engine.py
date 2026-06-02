"""Engine for forex spot/CFD operations."""
from .base import BaseEngine, EngineContext, EngineSignal


class ForexEngine(BaseEngine):
    market_type = "forex"

    def evaluate(self, context: EngineContext) -> EngineSignal:
        signal = context.metadata.get("signal", {})
        direction = signal.get("type", "neutral")

        return EngineSignal(
            market_type=self.market_type,
            symbol=context.symbol,
            timeframe=context.timeframe,
            direction=direction,
            probability=float(signal.get("probability", 0.0)),
            score=float(signal.get("score", 0.0)),
            edge=float(signal.get("edge", 0.0)),
            consensus=int(signal.get("consensus", 0)),
            reference_price=signal.get("reference_price"),
            reason="forex engine decision",
        )
