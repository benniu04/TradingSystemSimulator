import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from config import Settings
from core.event_bus import EventBus
from execution.order_manager import OrderManager
from models import Event, EventType, Fill, Side, Signal, Tick


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


@pytest.mark.asyncio
async def test_signal_creates_order():
    bus = EventBus()
    settings = Settings()
    om = OrderManager(bus, settings)
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
    settings = Settings()
    om = OrderManager(bus, settings)
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
    settings = Settings()
    om = OrderManager(bus, settings)
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
    settings = Settings()
    om = OrderManager(bus, settings)
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
    settings = Settings()
    om = OrderManager(bus, settings)
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
    settings = Settings()
    om = OrderManager(bus, settings)
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
    settings = Settings()
    om = OrderManager(bus, settings)
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
