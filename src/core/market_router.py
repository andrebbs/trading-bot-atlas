"""Market type router for selecting the correct engine."""
from typing import Dict

from src.engines import CryptoBinaryEngine, ForexEngine, BaseEngine


_SUPPORTED_MARKET_TYPES = {
    "crypto_binary": CryptoBinaryEngine,
    "forex": ForexEngine,
    "stocks": ForexEngine,
    "commodities": ForexEngine,
}


def normalize_market_type(value: str) -> str:
    """Normalize market type aliases to canonical values."""
    raw = (value or "").strip().lower()
    aliases = {
        "crypto": "crypto_binary",
        "binary": "crypto_binary",
        "crypto-binario": "crypto_binary",
        "crypto_binario": "crypto_binary",
        "fx": "forex",
        "acoes": "stocks",
        "ações": "stocks",
        "commodities": "commodities",
    }
    return aliases.get(raw, raw or "crypto_binary")


def create_engine(market_type: str) -> BaseEngine:
    """Create the engine for the requested market type."""
    canonical = normalize_market_type(market_type)
    engine_cls = _SUPPORTED_MARKET_TYPES.get(canonical)
    if engine_cls is None:
        supported = ", ".join(sorted(_SUPPORTED_MARKET_TYPES.keys()))
        raise ValueError(f"Unsupported market_type '{market_type}'. Supported: {supported}")
    return engine_cls()


def supported_market_types() -> Dict[str, str]:
    """Return supported market types and class names."""
    return {k: v.__name__ for k, v in _SUPPORTED_MARKET_TYPES.items()}
