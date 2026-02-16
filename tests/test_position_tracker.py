from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from core.event_bus import EventBus
from models import Event, EventType, Fill, Side, Tick
from risk.position_tracker import PositionTracker


def _make_fill(symbol: str, side: Side, quantity: int, price: float) -> Event:
    fill = Fill(
        order_id=uuid4(),
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=Decimal(str(price)),
    )
    return Event(type=EventType.FILL, payload=fill)


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


@pytest.mark.asyncio
async def test_buy_creates_position():
    bus = EventBus()
    tracker = PositionTracker(bus)
    await tracker.start()

    await bus.publish(_make_fill("AAPL", Side.BUY, 100, 150.0))

    pos = tracker.get_position("AAPL")
    assert pos is not None
    assert pos.quantity == 100
    assert pos.avg_entry_price == Decimal("150.0000")
    await tracker.stop()


@pytest.mark.asyncio
async def test_sell_creates_short():
    bus = EventBus()
    tracker = PositionTracker(bus)
    await tracker.start()

    await bus.publish(_make_fill("AAPL", Side.SELL, 50, 150.0))

    pos = tracker.get_position("AAPL")
    assert pos is not None
    assert pos.quantity == -50
    await tracker.stop()


@pytest.mark.asyncio
async def test_buy_then_sell_realized_pnl():
    bus = EventBus()
    tracker = PositionTracker(bus)
    await tracker.start()

    await bus.publish(_make_fill("AAPL", Side.BUY, 100, 10.0))
    await bus.publish(_make_fill("AAPL", Side.SELL, 100, 12.0))

    pos = tracker.get_position("AAPL")
    assert pos is not None
    assert pos.realized_pnl == Decimal("200.0")
    assert pos.quantity == 0
    await tracker.stop()


@pytest.mark.asyncio
async def test_tick_updates_unrealized_pnl():
    bus = EventBus()
    tracker = PositionTracker(bus)
    await tracker.start()

    await bus.publish(_make_fill("AAPL", Side.BUY, 100, 150.0))
    await bus.publish(_make_tick("AAPL", 155.0))

    pos = tracker.get_position("AAPL")
    assert pos is not None
    assert pos.current_price == Decimal("155.0")
    assert pos.unrealized_pnl == Decimal("500.0")
    await tracker.stop()


@pytest.mark.asyncio
async def test_portfolio_snapshot_totals():
    bus = EventBus()
    tracker = PositionTracker(bus, initial_cash=Decimal("100000"))
    await tracker.start()

    await bus.publish(_make_fill("AAPL", Side.BUY, 10, 100.0))
    await bus.publish(_make_tick("AAPL", 110.0))

    snapshot = tracker.get_portfolio_snapshot()
    assert snapshot.total_unrealized_pnl == Decimal("100.0")
    assert snapshot.total_equity == Decimal("100000") - Decimal("1000") + Decimal("1100")
    await tracker.stop()


@pytest.mark.asyncio
async def test_cash_decreases_on_buy():
    bus = EventBus()
    tracker = PositionTracker(bus, initial_cash=Decimal("100000"))
    await tracker.start()

    await bus.publish(_make_fill("AAPL", Side.BUY, 10, 100.0))

    assert tracker._cash == Decimal("99000")
    await tracker.stop()
