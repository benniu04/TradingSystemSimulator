import asyncio
from decimal import Decimal
from uuid import UUID

import structlog

from config import Settings
from core.event_bus import EventBus
from models import (
    Event,
    EventType,
    Fill,
    OrderRequest,
    OrderType,
    Side,
    Signal,
    Tick,
)


class OrderManager:
    def __init__(self, event_bus: EventBus, settings: Settings) -> None:
        self._event_bus = event_bus
        self._settings = settings
        self._orders: dict[UUID, OrderRequest] = {}
        self._latest_prices: dict[str, Decimal] = {}
        self._logger = structlog.get_logger(__name__)

    async def start(self) -> None:
        self._event_bus.subscribe(EventType.SIGNAL, self._handle_signal)
        self._event_bus.subscribe(EventType.TICK, self._update_price)
        self._logger.info("order_manager_started")

    async def stop(self) -> None:
        self._event_bus.unsubscribe(EventType.SIGNAL, self._handle_signal)
        self._event_bus.unsubscribe(EventType.TICK, self._update_price)

    async def _update_price(self, event: Event) -> None:
        tick = event.payload
        assert isinstance(tick, Tick)
        self._latest_prices[tick.symbol] = tick.price

    async def _handle_signal(self, event: Event) -> None:
        signal = event.payload
        assert isinstance(signal, Signal)

        quantity = max(1, int(signal.strength * 100))

        order = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            strategy_id=signal.strategy_id,
        )
        self._orders[order.id] = order
        self._logger.info(
            "order_created",
            order_id=str(order.id),
            symbol=order.symbol,
            side=order.side.value,
            qty=order.quantity,
        )

        await self._event_bus.publish(
            Event(type=EventType.ORDER_REQUEST, payload=order)
        )

        await self._simulate_fill(order)

    async def _simulate_fill(self, order: OrderRequest) -> None:
        await asyncio.sleep(0.01)

        fill_price = self._latest_prices.get(
            order.symbol,
            order.limit_price or Decimal("100.00"),
        )
        slippage = fill_price * Decimal("0.0001")
        if order.side == Side.BUY:
            fill_price = fill_price + slippage
        else:
            fill_price = fill_price - slippage

        fill = Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price.quantize(Decimal("0.0001")),
        )

        self._logger.info(
            "order_filled",
            order_id=str(order.id),
            price=str(fill.price),
        )

        await self._event_bus.publish(Event(type=EventType.FILL, payload=fill))

    def get_order(self, order_id: UUID) -> OrderRequest | None:
        return self._orders.get(order_id)

    def get_all_orders(self) -> list[OrderRequest]:
        return list(self._orders.values())
