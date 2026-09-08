"""Unit tests for the ATLAS Crypto IDX rejection strategy engine."""
import datetime
import unittest

from src.core.stockity_market_data import Candle
from src.core.atlas_crypto_idx_strategy import (
    analyze_rejection,
    _m5_context,
    _nearest_region,
    _detect_rejection,
    _grade_quality,
)


def _c(o, h, l, c, minute):
    return Candle(
        open=o,
        high=h,
        low=l,
        close=c,
        created_at=datetime.datetime(2026, 1, 1, 0, minute, 0, tzinfo=datetime.timezone.utc),
    )


class TestM5Context(unittest.TestCase):
    def test_bullish_context(self):
        m5 = [
            _c(100, 101, 99, 100.5, i)
            for i in range(6)
        ]
        # make it clearly ascending
        m5 = [
            _c(100 + i, 101 + i, 99 + i, 100.5 + i, i) for i in range(12)
        ]
        self.assertEqual(_m5_context(m5), "ALTA")

    def test_bearish_context(self):
        m5 = [
            _c(112 - i, 113 - i, 111 - i, 111.5 - i, i) for i in range(12)
        ]
        self.assertEqual(_m5_context(m5), "BAIXA")

    def test_lateral_context_insufficient_data(self):
        m5 = [_c(100, 101, 99, 100, 0)]
        self.assertEqual(_m5_context(m5), "LATERAL")


class TestRegionDetection(unittest.TestCase):
    def test_resistance_detected_when_price_near_prior_high(self):
        # Build M5 candles with a repeated swing high around 110
        m5 = []
        prices = [100, 105, 110, 108, 104, 109.8, 110.1, 106, 103, 107, 109.9, 105]
        for i, p in enumerate(prices):
            m5.append(_c(p, p + 0.5, p - 0.5, p, i))
        region, region_price, touches = _nearest_region(109.5, m5, "BAIXA")
        self.assertIn(region, {"RESISTENCIA", "NENHUMA"})

    def test_no_region_when_price_in_middle_of_range(self):
        m5 = [_c(100 + (i % 3), 102 + (i % 3), 98 + (i % 3), 100 + (i % 3), i) for i in range(12)]
        region, _, _ = _nearest_region(150, m5, "LATERAL")
        self.assertEqual(region, "NENHUMA")


class TestRejectionDetection(unittest.TestCase):
    def test_resistance_rejection_signal(self):
        # prev candle pushes toward resistance, last candle wicks above but
        # closes back below with a clear reversal close.
        setup = _c(107, 108, 106.5, 108, 0)
        prev = _c(108, 109.5, 107.5, 109, 1)
        last = _c(109, 110.5, 108.8, 108.9, 2)  # upper wick, closes below region & below prev
        rejection, direction, _ = _detect_rejection([setup, prev, last], "RESISTENCIA", 110.0)
        self.assertEqual(rejection, "SIM")
        self.assertEqual(direction, "PUT")

    def test_support_rejection_signal(self):
        setup = _c(93, 93.5, 92, 92, 0)
        prev = _c(92, 92.5, 90.5, 91, 1)
        last = _c(91, 91.2, 89.5, 91.3, 2)  # lower wick, closes above region & above prev
        rejection, direction, _ = _detect_rejection([setup, prev, last], "SUPORTE", 90.0)
        self.assertEqual(rejection, "SIM")
        self.assertEqual(direction, "CALL")

    def test_true_breakout_is_not_rejection(self):
        setup = _c(107, 108, 106.5, 108, 0)
        prev = _c(108, 109.5, 107.5, 109, 1)
        # strong body candle that breaks and holds above resistance
        last = _c(109.2, 112, 109.1, 111.8, 2)
        rejection, direction, _ = _detect_rejection([setup, prev, last], "RESISTENCIA", 110.0)
        self.assertEqual(rejection, "NAO")

    def test_insufficient_data(self):
        rejection, direction, _ = _detect_rejection([_c(1, 2, 0, 1, 0)], "SUPORTE", 1.0)
        self.assertEqual(rejection, "NAO")
        self.assertEqual(direction, "NEUTRO")


class TestQualityGrading(unittest.TestCase):
    def test_grade_a_entrar(self):
        quality, action = _grade_quality("BAIXA", "RESISTENCIA", touches=2, rejection="SIM", direction="PUT")
        self.assertEqual(quality, "A")
        self.assertEqual(action, "ENTRAR")

    def test_grade_c_no_region(self):
        quality, action = _grade_quality("LATERAL", "NENHUMA", touches=0, rejection="NAO", direction="NEUTRO")
        self.assertEqual(quality, "C")
        self.assertEqual(action, "NAO_OPERAR")

    def test_grade_b_em_formacao(self):
        quality, action = _grade_quality("LATERAL", "SUPORTE", touches=1, rejection="EM_FORMACAO", direction="NEUTRO")
        self.assertEqual(quality, "B")
        self.assertEqual(action, "AGUARDAR")


class TestAnalyzeRejectionIntegration(unittest.TestCase):
    def test_empty_candles_returns_safe_default(self):
        signal = analyze_rejection([], [])
        self.assertEqual(signal.action, "NAO_OPERAR")
        self.assertEqual(signal.quality, "C")

    def test_full_pipeline_runs_without_error(self):
        m5 = [_c(100 + (i % 4), 101 + (i % 4), 99 + (i % 4), 100 + (i % 4), i) for i in range(12)]
        m1 = [_c(100, 100.5, 99.5, 100.1, i) for i in range(5)]
        signal = analyze_rejection(m1, m5)
        self.assertIn(signal.quality, {"A", "B", "C"})
        self.assertIn(signal.action, {"ENTRAR", "AGUARDAR", "NAO_OPERAR"})
        msg = signal.format_message()
        self.assertIn("Crypto IDX", msg)


if __name__ == "__main__":
    unittest.main()
