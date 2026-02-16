import asyncio
from decimal import Decimal

import pytest

from core.event_bus import EventBus
from feeds.market_data import AlpacaFeed, SyntheticFeed
from models import EventType, Tick


@pytest.mark.asyncio
async def test_synthetic_feed_publishes_ticks():
    bus = EventBus()
    symbols = ["AAPL", "MSFT"]
    feed = SyntheticFeed(bus, symbols, tick_interval=0.01)
    await feed.connect()

    task = asyncio.create_task(feed.start_streaming())
    await asyncio.sleep(0.15)
    await feed.disconnect()
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    history = bus.get_history(EventType.TICK)
    assert len(history) > 0
    symbols_seen = {e.payload.symbol for e in history}
    assert "AAPL" in symbols_seen
    assert "MSFT" in symbols_seen


@pytest.mark.asyncio
async def test_synthetic_price_stays_positive():
    bus = EventBus()
    feed = SyntheticFeed(
        bus,
        ["TEST"],
        tick_interval=0.001,
        base_prices={"TEST": 1.0},
    )
    await feed.connect()

    task = asyncio.create_task(feed.start_streaming())
    await asyncio.sleep(0.5)
    await feed.disconnect()
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    for event in bus.get_history(EventType.TICK):
        tick = event.payload
        assert isinstance(tick, Tick)
        assert tick.price > 0


@pytest.mark.asyncio
async def test_synthetic_disconnect_stops():
    bus = EventBus()
    feed = SyntheticFeed(bus, ["AAPL"], tick_interval=0.01)
    await feed.connect()

    task = asyncio.create_task(feed.start_streaming())
    await asyncio.sleep(0.05)
    await feed.disconnect()
    await asyncio.sleep(0.05)

    count_after_disconnect = len(bus.get_history())
    await asyncio.sleep(0.1)
    count_later = len(bus.get_history())

    assert count_after_disconnect == count_later
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_alpaca_fallback_on_failure():
    bus = EventBus()
    from config import Settings

    settings = Settings(alpaca_api_key="invalid", alpaca_api_secret="invalid")
    feed = AlpacaFeed(bus, ["AAPL"], settings)
    await feed.connect()

    task = asyncio.create_task(feed.start_streaming())
    await asyncio.sleep(0.3)
    await feed.disconnect()
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    history = bus.get_history(EventType.TICK)
    assert len(history) > 0


@pytest.mark.asyncio
async def test_tick_model_fields():
    bus = EventBus()
    feed = SyntheticFeed(bus, ["AAPL"], tick_interval=0.01)
    await feed.connect()

    task = asyncio.create_task(feed.start_streaming())
    await asyncio.sleep(0.05)
    await feed.disconnect()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    history = bus.get_history(EventType.TICK)
    assert len(history) > 0
    tick = history[0].payload
    assert isinstance(tick, Tick)
    assert isinstance(tick.price, Decimal)
    assert isinstance(tick.volume, int)
    assert isinstance(tick.bid, Decimal)
    assert isinstance(tick.ask, Decimal)
    assert tick.symbol == "AAPL"
