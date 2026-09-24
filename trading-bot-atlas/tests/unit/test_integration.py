"""Testes de integração: Feed -> Buffer -> Analisador -> Alerta -> Paper Trader."""
from datetime import datetime, timedelta
from decimal import Decimal
from src.core.lot_defense import Candle, LotSide, LotDefenseAnalyzer, detect_lots
from src.feed.candle_buffer import ClosedCandleBuffer
from src.notifications.telegram_notifier import TelegramNotifier, TelegramConfig
from src.execution.paper_trader import PaperTrader, TradeResult

def candle(open_p: str, close_p: str, idx: int, high_p: Optional[str] = None, low_p: Optional[str] = None) -> Candle:
    vo = Decimal(open_p)
    vc = Decimal(close_p)
    vh = Decimal(high_p) if high_p is not None else max(vo, vc)
    vl = Decimal(low_p) if low_p is not None else min(vo, vc)
    return Candle(
        timestamp=datetime(2026, 1, 1, 10, 0) + timedelta(minutes=idx),
        open=vo,
        high=vh,
        low=vl,
        close=vc,
    )

def test_closed_candle_buffer_deduplication():
    buffer = ClosedCandleBuffer(max_history=10)
    c0 = candle("1.0800", "1.0810", 0)
    assert buffer.add_closed_candle("EURUSD", c0) is True
    # Duplicate timestamp rejected
    assert buffer.add_closed_candle("EURUSD", c0) is False
    assert buffer.count("EURUSD") == 1

def test_full_pipeline_simulation():
    buffer = ClosedCandleBuffer(max_history=50)
    analyzer = LotDefenseAnalyzer(symbol="EURUSD", min_defenses=3)
    notifier = TelegramNotifier()
    trader = PaperTrader(default_stake=Decimal("100.0"))

    # Feed 3 candles
    c0 = candle("1.0800", "1.0820", 0, high_p="1.0825", low_p="1.0800")
    c1 = candle("1.0820", "1.0840", 1, high_p="1.0840", low_p="1.0820")
    c2 = candle("1.0835", "1.0800", 2, high_p="1.0835", low_p="1.0799")

    for c in [c0, c1, c2]:
        buffer.add_closed_candle("EURUSD", c)

    candles = buffer.get_candles("EURUSD")
    lots = detect_lots(candles[:2])

    # Simulate signal trigger
    from src.core.lot_defense import ActiveDefenseLevel, DefenseType
    analyzer.active_levels.extend([
        ActiveDefenseLevel(defense_type=DefenseType.VELA_DO_LOTE, side=LotSide.BUY, price_level=Decimal("1.0800"), reference_index=0),
        ActiveDefenseLevel(defense_type=DefenseType.VELA_DE_COMANDO, side=LotSide.BUY, price_level=Decimal("1.0800"), reference_index=0),
        ActiveDefenseLevel(defense_type=DefenseType.TAXA_DIVIDIDA, side=LotSide.BUY, price_level=Decimal("1.0800"), reference_index=1),
    ])

    signal = analyzer.evaluate_last_candle_for_signal(candles, lots)
    assert signal is not None
    assert signal.action is LotSide.BUY

    # Send notification
    sent = notifier.send_signal(signal)
    assert sent is True
    assert len(notifier.history) == 1

    # Open paper trade
    trade = trader.open_trade_from_signal(signal)
    assert trade.status == "OPEN"

    # Next candle closes in profit (BUY wins when close > 1.0800)
    c3 = candle("1.0800", "1.0820", 3)
    buffer.add_closed_candle("EURUSD", c3)
    resolved = trader.process_closed_candle("EURUSD", c3)

    assert len(resolved) == 1
    assert resolved[0].result == TradeResult.WIN
    assert resolved[0].profit == Decimal("85.0")

    stats = trader.get_statistics()
    assert stats["wins"] == 1
    assert stats["win_rate_percent"] == 100.0
