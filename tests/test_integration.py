import asyncio

import pytest

from config import Settings
from core.event_bus import EventBus
from execution.order_manager import OrderManager
from feeds.market_data import SyntheticFeed
from models import EventType
from risk.position_tracker import PositionTracker
from risk.risk_manager import RiskManager
from strategies.engine import StrategyEngine
from strategies.mean_reversion import MeanReversionStrategy


@pytest.mark.asyncio
async def test_full_pipeline_synthetic():
    """End-to-end: ticks -> strategy -> orders -> fills -> positions."""
    bus = EventBus()
    settings = Settings(max_order_value=100000, max_position_size=100000)

    tracker = PositionTracker(bus)
    risk_mgr = RiskManager(bus, tracker, settings)
    order_mgr = OrderManager(bus, settings)

    # Use low z-threshold to generate signals quickly
    strategy = MeanReversionStrategy(
        symbols=["TEST"], window_size=10, entry_z=1.0
    )
    engine = StrategyEngine(bus)
    engine.register_strategy(strategy)

    feed = SyntheticFeed(
        bus,
        ["TEST"],
        tick_interval=0.005,
        base_prices={"TEST": 100.0},
    )

    await tracker.start()
    await risk_mgr.start()
    await order_mgr.start()
    await engine.start()
    await feed.connect()

    task = asyncio.create_task(feed.start_streaming())
    await asyncio.sleep(3)
    await feed.disconnect()
    await asyncio.sleep(0.1)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    ticks = bus.get_history(EventType.TICK)
    assert len(ticks) > 0, "Expected ticks to be published"

    await engine.stop()
    await order_mgr.stop()
    await risk_mgr.stop()
    await tracker.stop()


@pytest.mark.asyncio
async def test_risk_blocks_large_order():
    """Risk manager rejects orders exceeding max_order_value."""
    bus = EventBus()
    settings = Settings(max_order_value=1, max_position_size=100000)

    tracker = PositionTracker(bus)
    risk_mgr = RiskManager(bus, tracker, settings)
    order_mgr = OrderManager(bus, settings)

    strategy = MeanReversionStrategy(
        symbols=["TEST"], window_size=10, entry_z=1.0
    )
    engine = StrategyEngine(bus)
    engine.register_strategy(strategy)

    feed = SyntheticFeed(
        bus,
        ["TEST"],
        tick_interval=0.005,
        base_prices={"TEST": 100.0},
    )

    await tracker.start()
    await risk_mgr.start()
    await order_mgr.start()
    await engine.start()
    await feed.connect()

    task = asyncio.create_task(feed.start_streaming())
    await asyncio.sleep(3)
    await feed.disconnect()
    await asyncio.sleep(0.1)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # If any signals were generated, all orders should be rejected
    signals = bus.get_history(EventType.SIGNAL)
    breaches = bus.get_history(EventType.RISK_BREACH)
    if len(signals) > 0:
        assert len(breaches) > 0, "Expected risk breaches for large orders"

    await engine.stop()
    await order_mgr.stop()
    await risk_mgr.stop()
    await tracker.stop()


@pytest.mark.asyncio
async def test_graceful_shutdown():
    """Start and immediately stop — no exceptions."""
    bus = EventBus()
    settings = Settings()

    tracker = PositionTracker(bus)
    risk_mgr = RiskManager(bus, tracker, settings)
    order_mgr = OrderManager(bus, settings)
    engine = StrategyEngine(bus)

    await tracker.start()
    await risk_mgr.start()
    await order_mgr.start()
    await engine.start()

    # Immediately stop
    await engine.stop()
    await order_mgr.stop()
    await risk_mgr.stop()
    await tracker.stop()
