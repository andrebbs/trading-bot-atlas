"""
OTC strategy catalog and query helpers.

This module turns free-form channel notes into a structured knowledge base
that can be filtered by market/timeframe/risk and checked against indicators
currently implemented in this codebase.
"""
import json
from pathlib import Path
from typing import Dict, List


RISK_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
}

# Indicators already available in this project.
SUPPORTED_INDICATORS = {
    "rsi",
    "macd",
    "bollinger",
    "ema",
    "volume",
    "atr",
    "stochastic",
    "adx",
    "awesome_oscillator",
    "fractals",
}

# Basic synonym map from notes to project indicator names.
INDICATOR_ALIASES = {
    "sma": "ema",
    "moving_average": "ema",
    "envelopes": "bollinger",
    "support_resistance": "price_action",
    "bulls_power": "bulls_power",
    "bears_power": "bears_power",
    "stochastic": "stochastic",
    "adx": "adx",
    "awesome_oscillator": "awesome_oscillator",
    "fractals": "fractals",
}


class StrategyCatalog:
    """Loads and filters OTC strategy entries from JSON catalog."""

    def __init__(self, catalog_path: str = "config/otc_strategy_catalog.json"):
        path = Path(catalog_path)
        if not path.is_absolute():
            root = Path(__file__).resolve().parents[2]
            path = root / catalog_path

        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        self.version = payload.get("version", 1)
        self.source = payload.get("source", "unknown")
        self.strategies = payload.get("strategies", [])

    def _normalize_indicator(self, name: str) -> str:
        key = str(name).strip().lower()
        return INDICATOR_ALIASES.get(key, key)

    def _is_risk_allowed(self, risk_profile: str, max_risk: str) -> bool:
        risk_value = RISK_ORDER.get(str(risk_profile).lower(), RISK_ORDER["high"])
        max_value = RISK_ORDER.get(str(max_risk).lower(), RISK_ORDER["medium"])
        return risk_value <= max_value

    def _is_market_match(self, markets: List[str], market: str) -> bool:
        normalized = {str(item).lower() for item in markets}
        return "any" in normalized or str(market).lower() in normalized

    def _is_timeframe_match(self, timeframes: List[str], timeframe: str) -> bool:
        normalized = {str(item).lower() for item in timeframes}
        return "any" in normalized or str(timeframe).lower() in normalized

    def get_matches(
        self,
        market: str = "otc",
        timeframe: str = "5m",
        max_risk: str = "medium",
    ) -> List[Dict]:
        """
        Return matching strategies enriched with support analysis.
        """
        matches: List[Dict] = []

        for strategy in self.strategies:
            if not self._is_market_match(strategy.get("markets", []), market):
                continue

            if not self._is_timeframe_match(strategy.get("timeframes", []), timeframe):
                continue

            if not self._is_risk_allowed(strategy.get("risk_profile", "high"), max_risk):
                continue

            raw_indicators = strategy.get("indicators", [])
            normalized = [self._normalize_indicator(item) for item in raw_indicators]
            supported = sorted([item for item in normalized if item in SUPPORTED_INDICATORS])
            missing = sorted([item for item in normalized if item not in SUPPORTED_INDICATORS])

            support_ratio = (len(supported) / len(normalized)) if normalized else 0.0
            readiness = "ready" if support_ratio >= 0.75 else "partial" if support_ratio >= 0.4 else "needs-build"

            enriched = dict(strategy)
            enriched["supported_indicators"] = supported
            enriched["missing_indicators"] = missing
            enriched["support_ratio"] = round(support_ratio, 2)
            enriched["readiness"] = readiness
            matches.append(enriched)

        # Prefer lower risk and higher project-readiness.
        matches.sort(
            key=lambda item: (
                RISK_ORDER.get(item.get("risk_profile", "high"), 2),
                -item.get("support_ratio", 0),
                item.get("name", ""),
            )
        )
        return matches
