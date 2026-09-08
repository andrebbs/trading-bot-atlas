import importlib.util
import sys
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "core" / "stockity_executor.py"
_spec = importlib.util.spec_from_file_location("stockity_executor", _MODULE_PATH)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

StockityExecutor = _module.StockityExecutor
StockitySettings = _module.StockitySettings
direction_to_trend = _module.direction_to_trend
normalize_asset_ric = _module.normalize_asset_ric


class TestHelpers(unittest.TestCase):
    def test_direction_to_trend(self):
        self.assertEqual(direction_to_trend("BUY"), "call")
        self.assertEqual(direction_to_trend("SELL"), "put")
        self.assertEqual(direction_to_trend(1), "call")
        self.assertEqual(direction_to_trend(0), "put")
        with self.assertRaises(ValueError):
            direction_to_trend("SIDEWAYS")

    def test_normalize_asset_ric_defaults_to_crypto_idx(self):
        self.assertEqual(normalize_asset_ric("Z-CRY/IDX"), "Z-CRY/IDX")
        self.assertEqual(normalize_asset_ric("BTC/USDT"), "Z-CRY/IDX")
        self.assertEqual(normalize_asset_ric(""), "Z-CRY/IDX")


class TestValidation(unittest.TestCase):
    def _settings(self, **overrides):
        base = dict(
            enabled=True,
            mode="demo",
            confirm_live=False,
            platform="stockity.id",
            email="user@example.com",
            password="secret",
            default_amount_cents=500,
            default_expiration_minutes=1,
            default_asset_ric="Z-CRY/IDX",
            connect_timeout_seconds=1.0,
        )
        base.update(overrides)
        return StockitySettings(**base)

    def test_disabled_blocks_execution(self):
        executor = StockityExecutor(self._settings(enabled=False))
        result = executor.place_order(symbol="Z-CRY/IDX", direction="BUY")
        self.assertFalse(result["ok"])
        self.assertIn("STOCKITY_ENABLED", result["error"])

    def test_live_without_confirm_blocks_execution(self):
        executor = StockityExecutor(self._settings(mode="live", confirm_live=False))
        result = executor.place_order(symbol="Z-CRY/IDX", direction="BUY")
        self.assertFalse(result["ok"])
        self.assertIn("STOCKITY_CONFIRM_LIVE", result["error"])

    def test_missing_credentials_blocks_execution(self):
        executor = StockityExecutor(self._settings(email="", password=""))
        result = executor.place_order(symbol="Z-CRY/IDX", direction="BUY")
        self.assertFalse(result["ok"])
        self.assertIn("STOCKITY_EMAIL", result["error"])


if __name__ == "__main__":
    unittest.main()
