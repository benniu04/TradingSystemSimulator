from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from core.event_bus import EventBus
from models import Event, EventType, Fill, Side, Signal, Tick
from risk.position_tracker import PositionTracker
from risk.stop_loss import StopLossManager


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


async def _setup(stop_loss_pct: float = 0.02):
    bus = EventBus()
    tracker = PositionTracker(bus)
    slm = StopLossManager(bus, tracker, stop_loss_pct)
    await tracker.start()
    await slm.start()
    return bus, tracker, slm


@pytest.mark.asyncio
async def test_long_position_triggers_stop_on_price_drop():
    """Long position triggers stop when price drops below threshold."""
    bus, tracker, slm = await _setup(stop_loss_pct=0.02)

    signals: list[Event] = []
    bus.subscribe(EventType.SIGNAL, lambda e: signals.append(e))

    # Open long position: buy 100 shares at $100
    await bus.publish(_make_fill("AAPL", Side.BUY, 100, 100.0))

    # Price drops to $97.99 (> 2% loss) — should trigger
    await bus.publish(_make_tick("AAPL", 97.99))

    assert len(signals) == 1
    sig = signals[0].payload
    assert isinstance(sig, Signal)
    assert sig.strategy_id == "stop_loss"
    assert sig.symbol == "AAPL"
    assert sig.side == Side.SELL
    assert sig.strength == 1.0

    await slm.stop()
    await tracker.stop()


@pytest.mark.asyncio
async def test_short_position_triggers_stop_on_price_rise():
    """Short position triggers stop when price rises above threshold."""
    bus, tracker, slm = await _setup(stop_loss_pct=0.02)

    signals: list[Event] = []
    bus.subscribe(EventType.SIGNAL, lambda e: signals.append(e))

    # Open short position: sell 50 shares at $200
    await bus.publish(_make_fill("GOOGL", Side.SELL, 50, 200.0))

    # Price rises to $204.01 (> 2% loss) — should trigger
    await bus.publish(_make_tick("GOOGL", 204.01))

    assert len(signals) == 1
    sig = signals[0].payload
    assert isinstance(sig, Signal)
    assert sig.strategy_id == "stop_loss"
    assert sig.symbol == "GOOGL"
    assert sig.side == Side.BUY
    assert sig.strength == 1.0

    await slm.stop()
    await tracker.stop()


@pytest.mark.asyncio
async def test_no_trigger_when_price_within_bounds():
    """No stop triggered when price stays within the threshold."""
    bus, tracker, slm = await _setup(stop_loss_pct=0.02)

    signals: list[Event] = []
    bus.subscribe(EventType.SIGNAL, lambda e: signals.append(e))

    # Open long at $100
    await bus.publish(_make_fill("AAPL", Side.BUY, 100, 100.0))

    # Price drops to $98.50 (1.5% loss, within 2% threshold)
    await bus.publish(_make_tick("AAPL", 98.50))

    assert len(signals) == 0

    await slm.stop()
    await tracker.stop()


@pytest.mark.asyncio
async def test_stop_removed_when_position_goes_flat():
    """Stop is removed when position is closed (quantity goes to 0)."""
    bus, tracker, slm = await _setup(stop_loss_pct=0.02)

    signals: list[Event] = []
    bus.subscribe(EventType.SIGNAL, lambda e: signals.append(e))

    # Open long at $100
    await bus.publish(_make_fill("AAPL", Side.BUY, 100, 100.0))
    assert "AAPL" in slm._stops

    # Close position: sell 100 shares
    await bus.publish(_make_fill("AAPL", Side.SELL, 100, 99.0))
    assert "AAPL" not in slm._stops

    # Price drops below old stop — should NOT trigger since position is flat
    await bus.publish(_make_tick("AAPL", 95.0))
    assert len(signals) == 0

    await slm.stop()
    await tracker.stop()


@pytest.mark.asyncio
async def test_retrigger_prevented_until_position_closes():
    """Once a stop fires, it does not re-fire until the position actually closes."""
    bus, tracker, slm = await _setup(stop_loss_pct=0.02)

    signals: list[Event] = []
    bus.subscribe(EventType.SIGNAL, lambda e: signals.append(e))

    # Open long at $100
    await bus.publish(_make_fill("AAPL", Side.BUY, 100, 100.0))

    # Trigger stop
    await bus.publish(_make_tick("AAPL", 97.0))
    assert len(signals) == 1

    # Another tick below stop — should NOT trigger again
    await bus.publish(_make_tick("AAPL", 96.0))
    assert len(signals) == 1

    # Close the position
    await bus.publish(_make_fill("AAPL", Side.SELL, 100, 96.0))

    # Open a new long at $96
    await bus.publish(_make_fill("AAPL", Side.BUY, 50, 96.0))

    # New stop can trigger now
    await bus.publish(_make_tick("AAPL", 93.0))
    assert len(signals) == 2

    await slm.stop()
    await tracker.stop()
