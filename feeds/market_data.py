import abc
import asyncio
import random
from datetime import UTC, datetime
from decimal import Decimal

import aiohttp
import structlog

from config import Settings
from core.event_bus import EventBus
from models import Event, EventType, Tick


class MarketDataFeed(abc.ABC):
    def __init__(self, event_bus: EventBus, symbols: list[str]) -> None:
        self._event_bus = event_bus
        self._symbols = symbols
        self._running = False
        self._logger = structlog.get_logger(self.__class__.__name__)

    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def disconnect(self) -> None: ...

    @abc.abstractmethod
    async def start_streaming(self) -> None: ...

    async def _publish_tick(self, tick: Tick) -> None:
        event = Event(type=EventType.TICK, payload=tick)
        await self._event_bus.publish(event)


class SyntheticFeed(MarketDataFeed):
    """Generates geometric-Brownian-motion ticks at configurable frequency."""

    def __init__(
        self,
        event_bus: EventBus,
        symbols: list[str],
        tick_interval: float = 0.1,
        base_prices: dict[str, float] | None = None,
    ) -> None:
        super().__init__(event_bus, symbols)
        self._tick_interval = tick_interval
        self._prices: dict[str, float] = base_prices or {
            s: random.uniform(100, 500) for s in symbols
        }
        self._volatility = 0.001

    async def connect(self) -> None:
        self._logger.info("synthetic_feed_connected", symbols=self._symbols)

    async def disconnect(self) -> None:
        self._running = False
        self._logger.info("synthetic_feed_disconnected")

    async def start_streaming(self) -> None:
        self._running = True
        self._logger.info("synthetic_feed_streaming")
        while self._running:
            for symbol in self._symbols:
                price = self._prices[symbol]
                change = price * random.gauss(0, self._volatility)
                price = max(price + change, 0.01)
                self._prices[symbol] = price

                spread = price * 0.0005
                tick = Tick(
                    symbol=symbol,
                    price=Decimal(str(round(price, 4))),
                    volume=random.randint(100, 10000),
                    bid=Decimal(str(round(price - spread, 4))),
                    ask=Decimal(str(round(price + spread, 4))),
                    timestamp=datetime.now(UTC),
                )
                await self._publish_tick(tick)
            await asyncio.sleep(self._tick_interval)


class AlpacaFeed(MarketDataFeed):
    """Connects to Alpaca WebSocket; falls back to SyntheticFeed."""

    def __init__(
        self,
        event_bus: EventBus,
        symbols: list[str],
        settings: Settings,
    ) -> None:
        super().__init__(event_bus, symbols)
        self._settings = settings
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._fallback = SyntheticFeed(event_bus, symbols)

    async def connect(self) -> None:
        try:
            self._session = aiohttp.ClientSession()
            ws_url = "wss://stream.data.alpaca.markets/v2/iex"
            self._ws = await self._session.ws_connect(ws_url)
            await self._ws.send_json(
                {
                    "action": "auth",
                    "key": self._settings.alpaca_api_key,
                    "secret": self._settings.alpaca_api_secret,
                }
            )
            await self._ws.receive_json()
            await self._ws.send_json(
                {
                    "action": "subscribe",
                    "trades": self._symbols,
                }
            )
            self._logger.info("alpaca_connected", symbols=self._symbols)
        except Exception as exc:
            self._logger.warning("alpaca_connect_failed", error=str(exc))
            await self._cleanup_session()
            await self._fallback.connect()

    async def disconnect(self) -> None:
        self._running = False
        await self._cleanup_session()
        await self._fallback.disconnect()
        self._logger.info("alpaca_disconnected")

    async def _cleanup_session(self) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        self._ws = None

    async def start_streaming(self) -> None:
        if self._ws is None or self._ws.closed:
            self._logger.info("falling_back_to_synthetic")
            await self._fallback.start_streaming()
            return

        self._running = True
        try:
            async for msg in self._ws:
                if not self._running:
                    break
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = msg.json()
                    for item in data:
                        if item.get("T") == "t":
                            tick = Tick(
                                symbol=item["S"],
                                price=Decimal(str(item["p"])),
                                volume=item["s"],
                                bid=Decimal(str(item["p"])),
                                ask=Decimal(str(item["p"])),
                                timestamp=datetime.fromisoformat(item["t"]),
                            )
                            await self._publish_tick(tick)
        except Exception as exc:
            self._logger.error("alpaca_stream_error", error=str(exc))
            self._logger.info("falling_back_to_synthetic")
            await self._fallback.connect()
            await self._fallback.start_streaming()
