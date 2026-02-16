from datetime import UTC, datetime
from decimal import Decimal

import pytest

from core.event_bus import EventBus
from models import Event, EventType, Tick


def _make_tick_event() -> Event:
    tick = Tick(
        symbol="AAPL",
        price=Decimal("150.00"),
        volume=1000,
        bid=Decimal("149.99"),
        ask=Decimal("150.01"),
        timestamp=datetime.now(UTC),
    )
    return Event(type=EventType.TICK, payload=tick)


def _make_signal_event() -> Event:
    from models import Signal, Side

    signal = Signal(
        strategy_id="test",
        symbol="AAPL",
        side=Side.BUY,
        strength=0.8,
    )
    return Event(type=EventType.SIGNAL, payload=signal)


@pytest.mark.asyncio
async def test_subscribe_and_publish():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.TICK, handler)
    event = _make_tick_event()
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].type == EventType.TICK


@pytest.mark.asyncio
async def test_multiple_subscribers():
    bus = EventBus()
    count = {"a": 0, "b": 0}

    async def handler_a(event: Event) -> None:
        count["a"] += 1

    async def handler_b(event: Event) -> None:
        count["b"] += 1

    bus.subscribe(EventType.TICK, handler_a)
    bus.subscribe(EventType.TICK, handler_b)
    await bus.publish(_make_tick_event())

    assert count["a"] == 1
    assert count["b"] == 1


@pytest.mark.asyncio
async def test_no_cross_delivery():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.TICK, handler)
    await bus.publish(_make_signal_event())

    assert len(received) == 0


@pytest.mark.asyncio
async def test_handler_exception_isolated():
    bus = EventBus()
    received: list[Event] = []

    async def bad_handler(event: Event) -> None:
        raise ValueError("boom")

    async def good_handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.TICK, bad_handler)
    bus.subscribe(EventType.TICK, good_handler)
    await bus.publish(_make_tick_event())

    assert len(received) == 1


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(EventType.TICK, handler)
    bus.unsubscribe(EventType.TICK, handler)
    await bus.publish(_make_tick_event())

    assert len(received) == 0


@pytest.mark.asyncio
async def test_history():
    bus = EventBus()
    for _ in range(5):
        await bus.publish(_make_tick_event())

    assert len(bus.get_history()) == 5
    assert len(bus.get_history(EventType.TICK)) == 5
    assert len(bus.get_history(EventType.SIGNAL)) == 0


@pytest.mark.asyncio
async def test_history_bounded():
    bus = EventBus()
    for _ in range(1500):
        await bus.publish(_make_tick_event())

    assert len(bus.get_history()) == 1000
