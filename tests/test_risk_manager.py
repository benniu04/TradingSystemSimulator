from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from config import Settings
from core.event_bus import EventBus
from models import (
    Event,
    EventType,
    Fill,
    OrderRequest,
    OrderType,
    Side,
    Tick,
)
from risk.position_tracker import PositionTracker
from risk.risk_manager import RiskManager


def _make_tick(symbol: str, price: float) -> Event:
    tick = Tick(
        symbol=symbol,
        price=Decimal(str(price)),
        volume=1000,
        bid=Decimal(str(price - 0.01)),
        ask=Decimal(str(price + 0.01)),
        timestamp=datetime.now(UTC),
    )
    return Event(type=EventType.TICK, payload=tick)


def _make_order_request(
    symbol: str, side: Side, quantity: int
) -> Event:
    order = OrderRequest(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        strategy_id="test",
    )
    return Event(type=EventType.ORDER_REQUEST, payload=order)


@pytest.mark.asyncio
async def test_order_within_limits_passes():
    bus = EventBus()
    tracker = PositionTracker(bus)
    settings = Settings(max_order_value=50000, max_position_size=100000)
    rm = RiskManager(bus, tracker, settings)
    await tracker.start()
    await rm.start()

    await bus.publish(_make_tick("AAPL", 150.0))
    await bus.publish(_make_order_request("AAPL", Side.BUY, 10))

    breaches = bus.get_history(EventType.RISK_BREACH)
    assert len(breaches) == 0
    await rm.stop()
    await tracker.stop()


@pytest.mark.asyncio
async def test_order_exceeds_max_value_rejected():
    bus = EventBus()
    tracker = PositionTracker(bus)
    settings = Settings(max_order_value=100, max_position_size=100000)
    rm = RiskManager(bus, tracker, settings)
    await tracker.start()
    await rm.start()

    await bus.publish(_make_tick("AAPL", 150.0))
    # 10 shares * $150 = $1500, exceeds max_order_value=100
    await bus.publish(_make_order_request("AAPL", Side.BUY, 10))

    breaches = bus.get_history(EventType.RISK_BREACH)
    assert len(breaches) >= 1

    rejections = bus.get_history(EventType.ORDER_UPDATE)
    assert len(rejections) >= 1
    await rm.stop()
    await tracker.stop()


@pytest.mark.asyncio
async def test_position_size_limit():
    bus = EventBus()
    tracker = PositionTracker(bus)
    settings = Settings(max_order_value=100000, max_position_size=500)
    rm = RiskManager(bus, tracker, settings)
    await tracker.start()
    await rm.start()

    await bus.publish(_make_tick("AAPL", 150.0))
    # 10 shares * $150 = $1500 projected position, exceeds max_position_size=500
    await bus.publish(_make_order_request("AAPL", Side.BUY, 10))

    breaches = bus.get_history(EventType.RISK_BREACH)
    assert len(breaches) >= 1
    await rm.stop()
    await tracker.stop()


@pytest.mark.asyncio
async def test_drawdown_limit():
    bus = EventBus()
    tracker = PositionTracker(bus, initial_cash=Decimal("10000"))
    settings = Settings(
        max_order_value=100000,
        max_position_size=100000,
        max_drawdown_pct=0.01,
    )
    rm = RiskManager(bus, tracker, settings)
    await tracker.start()
    await rm.start()

    # Simulate a loss: buy at 100, price drops to 50
    fill = Fill(
        order_id=uuid4(),
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        price=Decimal("100.0"),
    )
    await bus.publish(Event(type=EventType.FILL, payload=fill))
    await bus.publish(_make_tick("AAPL", 50.0))

    # Now try to place another order — drawdown should be exceeded
    await bus.publish(_make_order_request("AAPL", Side.BUY, 1))

    breaches = bus.get_history(EventType.RISK_BREACH)
    assert len(breaches) >= 1
    await rm.stop()
    await tracker.stop()
