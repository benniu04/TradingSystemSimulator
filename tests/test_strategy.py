from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.event_bus import EventBus
from models import Event, EventType, Side, Signal, Tick
from strategies.engine import StrategyEngine
from strategies.mean_reversion import MeanReversionStrategy


def _make_tick(symbol: str, price: float) -> Tick:
    return Tick(
        symbol=symbol,
        price=Decimal(str(price)),
        volume=1000,
        bid=Decimal(str(price - 0.01)),
        ask=Decimal(str(price + 0.01)),
        timestamp=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_mean_reversion_no_signal_insufficient_data():
    strategy = MeanReversionStrategy(window_size=10)
    for i in range(9):
        result = await strategy.on_tick(_make_tick("AAPL", 100.0 + i * 0.01))
        assert result is None


@pytest.mark.asyncio
async def test_mean_reversion_buy_signal():
    strategy = MeanReversionStrategy(window_size=20, entry_z=2.0)
    # Feed stable prices
    for _ in range(19):
        await strategy.on_tick(_make_tick("AAPL", 100.0))
    # Sudden large drop
    signal = await strategy.on_tick(_make_tick("AAPL", 90.0))
    assert signal is not None
    assert signal.side == Side.BUY


@pytest.mark.asyncio
async def test_mean_reversion_sell_signal():
    strategy = MeanReversionStrategy(window_size=20, entry_z=2.0)
    for _ in range(19):
        await strategy.on_tick(_make_tick("AAPL", 100.0))
    # Sudden spike
    signal = await strategy.on_tick(_make_tick("AAPL", 110.0))
    assert signal is not None
    assert signal.side == Side.SELL


@pytest.mark.asyncio
async def test_mean_reversion_no_signal_within_band():
    strategy = MeanReversionStrategy(window_size=20, entry_z=2.0)
    for i in range(20):
        signal = await strategy.on_tick(_make_tick("AAPL", 100.0 + (i % 2) * 0.01))
    assert signal is None


@pytest.mark.asyncio
async def test_mean_reversion_reset():
    strategy = MeanReversionStrategy(window_size=10)
    for _ in range(10):
        await strategy.on_tick(_make_tick("AAPL", 100.0))
    strategy.reset()
    assert len(strategy._price_windows) == 0


@pytest.mark.asyncio
async def test_engine_dispatches_to_strategy():
    bus = EventBus()
    engine = StrategyEngine(bus)
    strategy = MeanReversionStrategy(symbols=["AAPL"], window_size=5)
    engine.register_strategy(strategy)
    await engine.start()

    tick = _make_tick("AAPL", 100.0)
    await bus.publish(Event(type=EventType.TICK, payload=tick))

    assert len(strategy._price_windows.get("AAPL", [])) == 1
    await engine.stop()


@pytest.mark.asyncio
async def test_engine_publishes_signal():
    bus = EventBus()
    engine = StrategyEngine(bus)
    strategy = MeanReversionStrategy(symbols=["AAPL"], window_size=5, entry_z=1.5)
    engine.register_strategy(strategy)
    await engine.start()

    # Feed stable prices then a spike
    for _ in range(4):
        await bus.publish(
            Event(type=EventType.TICK, payload=_make_tick("AAPL", 100.0))
        )
    await bus.publish(
        Event(type=EventType.TICK, payload=_make_tick("AAPL", 115.0))
    )

    signals = bus.get_history(EventType.SIGNAL)
    assert len(signals) >= 1
    payload = signals[0].payload
    assert isinstance(payload, Signal)
    assert payload.side == Side.SELL
    await engine.stop()


@pytest.mark.asyncio
async def test_engine_filters_symbols():
    bus = EventBus()
    engine = StrategyEngine(bus)
    strategy = MeanReversionStrategy(symbols=["AAPL"], window_size=5)
    engine.register_strategy(strategy)
    await engine.start()

    # Send a TSLA tick — should not reach strategy
    await bus.publish(
        Event(type=EventType.TICK, payload=_make_tick("TSLA", 200.0))
    )

    assert "TSLA" not in strategy._price_windows
    await engine.stop()
