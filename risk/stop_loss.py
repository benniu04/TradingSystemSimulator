from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog

from core.event_bus import EventBus
from models import Event, EventType, Fill, Signal, Side, Tick
from risk.position_tracker import PositionTracker


@dataclass
class StopLevel:
    symbol: str
    stop_price: Decimal
    side_to_close: Side
    quantity: int


class StopLossManager:
    def __init__(
        self,
        event_bus: EventBus,
        position_tracker: PositionTracker,
        stop_loss_pct: float = 0.02,
    ) -> None:
        self._event_bus = event_bus
        self._position_tracker = position_tracker
        self._stop_loss_pct = Decimal(str(stop_loss_pct))
        self._stops: dict[str, StopLevel] = {}
        self._triggered: set[str] = set()
        self._logger = structlog.get_logger(__name__)

    async def start(self) -> None:
        self._event_bus.subscribe(EventType.FILL, self._handle_fill)
        self._event_bus.subscribe(EventType.TICK, self._handle_tick)
        self._logger.info("stop_loss_manager_started", pct=str(self._stop_loss_pct))

    async def stop(self) -> None:
        self._event_bus.unsubscribe(EventType.FILL, self._handle_fill)
        self._event_bus.unsubscribe(EventType.TICK, self._handle_tick)

    async def _handle_fill(self, event: Event) -> None:
        fill = event.payload
        assert isinstance(fill, Fill)

        pos = self._position_tracker.get_position(fill.symbol)
        if pos is None or pos.quantity == 0:
            # Position closed — remove stop and allow re-triggering
            self._stops.pop(fill.symbol, None)
            self._triggered.discard(fill.symbol)
            return

        if pos.quantity > 0:
            # Long position: stop triggers if price drops
            stop_price = pos.avg_entry_price * (1 - self._stop_loss_pct)
            side_to_close = Side.SELL
        else:
            # Short position: stop triggers if price rises
            stop_price = pos.avg_entry_price * (1 + self._stop_loss_pct)
            side_to_close = Side.BUY

        self._stops[fill.symbol] = StopLevel(
            symbol=fill.symbol,
            stop_price=stop_price,
            side_to_close=side_to_close,
            quantity=abs(pos.quantity),
        )
        # New/updated position — allow triggering again
        self._triggered.discard(fill.symbol)

        self._logger.info(
            "stop_level_set",
            symbol=fill.symbol,
            stop_price=str(stop_price),
            side_to_close=side_to_close.value,
            qty=abs(pos.quantity),
        )

    async def _handle_tick(self, event: Event) -> None:
        tick = event.payload
        assert isinstance(tick, Tick)

        stop = self._stops.get(tick.symbol)
        if stop is None:
            return

        if tick.symbol in self._triggered:
            return

        triggered = False
        if stop.side_to_close == Side.SELL:
            # Long position — trigger when price <= stop
            triggered = tick.price <= stop.stop_price
        else:
            # Short position — trigger when price >= stop
            triggered = tick.price >= stop.stop_price

        if triggered:
            self._triggered.add(tick.symbol)
            self._logger.warning(
                "stop_loss_triggered",
                symbol=tick.symbol,
                price=str(tick.price),
                stop_price=str(stop.stop_price),
            )
            signal = Signal(
                strategy_id="stop_loss",
                symbol=tick.symbol,
                side=stop.side_to_close,
                strength=1.0,
            )
            await self._event_bus.publish(
                Event(type=EventType.SIGNAL, payload=signal)
            )
