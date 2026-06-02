"""Base classes for market-specific signal engines."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class EngineContext:
    """Normalized input for market engines."""

    market_type: str
    symbol: str
    timeframe: str
    data: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineSignal:
    """Standard output from market engines."""

    market_type: str
    symbol: str
    timeframe: str
    direction: str  # buy | sell | neutral
    probability: float
    score: float
    edge: float
    consensus: int
    reference_price: Optional[float] = None
    expires_at: Optional[datetime] = None
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseEngine:
    """Common interface for all market engines."""

    market_type = "base"

    def evaluate(self, context: EngineContext) -> EngineSignal:
        raise NotImplementedError("Engine must implement evaluate()")
