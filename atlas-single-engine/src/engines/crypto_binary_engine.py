"""Engine for crypto binary operations (fixed expiry)."""
from datetime import datetime, timedelta

from .base import BaseEngine, EngineContext, EngineSignal


class CryptoBinaryEngine(BaseEngine):
    market_type = "crypto_binary"

    def evaluate(self, context: EngineContext) -> EngineSignal:
        signal = context.metadata.get("signal", {})
        direction = signal.get("type", "neutral")

        expiry_seconds = int(context.metadata.get("expiry_seconds", 120))
        expires_at = datetime.utcnow() + timedelta(seconds=expiry_seconds)

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
            expires_at=expires_at,
            reason="crypto binary engine decision",
        )
