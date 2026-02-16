import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from config import Settings
from core.event_bus import EventBus
from execution.order_manager import OrderManager
from models import Event, EventType, Fill, Side, Signal, Tick
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


def _make_signal(symbol: str, side: Side, strength: float) -> Event:
    signal = Signal(
        strategy_id="test",
        symbol=symbol,
        side=side,
        strength=strength,
    )
    return Event(type=EventType.SIGNAL, payload=signal)


def _make_om(bus: EventBus, **settings_kwargs):
    """Create an OrderManager with risk manager wired up."""
    defaults = {"max_order_value": 100000, "max_position_size": 100000}
    defaults.update(settings_kwargs)
    settings = Settings(**defaults)
    tracker = PositionTracker(bus)
    rm = RiskManager(bus, tracker, settings)
    om = OrderManager(bus, settings, rm)
    return om, tracker, rm


@pytest.mark.asyncio
async def test_signal_creates_order():
    bus = EventBus()
    om, tracker, rm = _make_om(bus)
    await tracker.start()
    await rm.start()
    await om.start()

    await bus.publish(_make_tick("AAPL", 150.0))
    await bus.publish(_make_signal("AAPL", Side.BUY, 0.5))
    await asyncio.sleep(0.05)

    order_requests = bus.get_history(EventType.ORDER_REQUEST)
    assert len(order_requests) >= 1
    await om.stop()


@pytest.mark.asyncio
async def test_signal_produces_fill():
    bus = EventBus()
    om, tracker, rm = _make_om(bus)
    await tracker.start()
    await rm.start()
    await om.start()

    await bus.publish(_make_tick("AAPL", 150.0))
    await bus.publish(_make_signal("AAPL", Side.BUY, 0.5))
    await asyncio.sleep(0.05)

    fills = bus.get_history(EventType.FILL)
    assert len(fills) >= 1
    fill = fills[0].payload
    assert isinstance(fill, Fill)
    assert fill.symbol == "AAPL"
    await om.stop()


@pytest.mark.asyncio
async def test_fill_price_near_market():
    bus = EventBus()
    om, tracker, rm = _make_om(bus)
    await tracker.start()
    await rm.start()
    await om.start()

    market_price = Decimal("150.0000")
    await bus.publish(_make_tick("AAPL", 150.0))
    await bus.publish(_make_signal("AAPL", Side.BUY, 0.5))
    await asyncio.sleep(0.05)

    fills = bus.get_history(EventType.FILL)
    fill = fills[0].payload
    assert isinstance(fill, Fill)
    assert abs(fill.price - market_price) < Decimal("0.1")
    await om.stop()


@pytest.mark.asyncio
async def test_quantity_from_strength():
    bus = EventBus()
    om, tracker, rm = _make_om(
        bus, max_order_value=500000, max_position_size=500000, max_drawdown_pct=0.99
    )
    await tracker.start()
    await rm.start()
    await om.start()

    await bus.publish(_make_tick("AAPL", 150.0))
    await bus.publish(_make_signal("AAPL", Side.BUY, 0.5))
    await asyncio.sleep(0.05)

    fills = bus.get_history(EventType.FILL)
    fill = fills[0].payload
    assert isinstance(fill, Fill)
    assert fill.quantity == 50

    await bus.publish(_make_signal("AAPL", Side.BUY, 1.0))
    await asyncio.sleep(0.05)

    fills = bus.get_history(EventType.FILL)
    fill = fills[-1].payload
    assert isinstance(fill, Fill)
    assert fill.quantity == 100
    await om.stop()


@pytest.mark.asyncio
async def test_buy_slippage_positive():
    bus = EventBus()
    om, tracker, rm = _make_om(bus)
    await tracker.start()
    await rm.start()
    await om.start()

    await bus.publish(_make_tick("AAPL", 150.0))
    await bus.publish(_make_signal("AAPL", Side.BUY, 0.5))
    await asyncio.sleep(0.05)

    fills = bus.get_history(EventType.FILL)
    fill = fills[0].payload
    assert isinstance(fill, Fill)
    assert fill.price >= Decimal("150.0")
    await om.stop()


@pytest.mark.asyncio
async def test_sell_slippage_negative():
    bus = EventBus()
    om, tracker, rm = _make_om(bus)
    await tracker.start()
    await rm.start()
    await om.start()

    await bus.publish(_make_tick("AAPL", 150.0))
    await bus.publish(_make_signal("AAPL", Side.SELL, 0.5))
    await asyncio.sleep(0.05)

    fills = bus.get_history(EventType.FILL)
    fill = fills[0].payload
    assert isinstance(fill, Fill)
    assert fill.price <= Decimal("150.0")
    await om.stop()


@pytest.mark.asyncio
async def test_get_order_by_id():
    bus = EventBus()
    om, tracker, rm = _make_om(bus)
    await tracker.start()
    await rm.start()
    await om.start()

    await bus.publish(_make_tick("AAPL", 150.0))
    await bus.publish(_make_signal("AAPL", Side.BUY, 0.5))
    await asyncio.sleep(0.05)

    orders = om.get_all_orders()
    assert len(orders) >= 1
    order = orders[0]
    assert om.get_order(order.id) is not None
    assert om.get_order(order.id).symbol == "AAPL"
    await om.stop()


@pytest.mark.asyncio
async def test_risk_manager_blocks_order():
    """Order exceeding max_order_value should be rejected, not filled."""
    bus = EventBus()
    om, tracker, rm = _make_om(bus, max_order_value=100)
    await tracker.start()
    await rm.start()
    await om.start()

    # 50 shares * $150 = $7500, exceeds max_order_value=100
    await bus.publish(_make_tick("AAPL", 150.0))
    await bus.publish(_make_signal("AAPL", Side.BUY, 0.5))
    await asyncio.sleep(0.05)

    fills = bus.get_history(EventType.FILL)
    assert len(fills) == 0, "Order should have been blocked, not filled"

    breaches = bus.get_history(EventType.RISK_BREACH)
    assert len(breaches) >= 1
    await om.stop()


@pytest.mark.asyncio
async def test_position_size_limit_blocks_accumulation():
    """Position size limit should prevent unlimited accumulation."""
    bus = EventBus()
    # Max position = $2000, price = $150, so max ~13 shares
    om, tracker, rm = _make_om(bus, max_order_value=100000, max_position_size=2000)
    await tracker.start()
    await rm.start()
    await om.start()

    await bus.publish(_make_tick("AAPL", 150.0))

    # First order: 10 shares * $150 = $1500 position — should pass
    await bus.publish(_make_signal("AAPL", Side.BUY, 0.1))
    await asyncio.sleep(0.05)
    fills_after_first = len(bus.get_history(EventType.FILL))
    assert fills_after_first == 1

    # Second order: 10 more shares would make $3000 position — should be blocked
    await bus.publish(_make_signal("AAPL", Side.BUY, 0.1))
    await asyncio.sleep(0.05)
    fills_after_second = len(bus.get_history(EventType.FILL))
    assert fills_after_second == 1, "Second order should have been blocked"

    await om.stop()
