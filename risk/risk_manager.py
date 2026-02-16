from decimal import Decimal

import structlog

from config import Settings
from core.event_bus import EventBus
from models import (
    Event,
    EventType,
    OrderRequest,
    OrderStatus,
    OrderUpdate,
    RiskBreach,
    Tick,
)
from risk.position_tracker import PositionTracker


class RiskManager:
    def __init__(
        self,
        event_bus: EventBus,
        position_tracker: PositionTracker,
        settings: Settings,
    ) -> None:
        self._event_bus = event_bus
        self._positions = position_tracker
        self._settings = settings
        self._latest_prices: dict[str, Decimal] = {}
        self._logger = structlog.get_logger(__name__)

    async def start(self) -> None:
        self._event_bus.subscribe(EventType.ORDER_REQUEST, self._check_order)
        self._event_bus.subscribe(EventType.TICK, self._update_price)
        self._logger.info("risk_manager_started")

    async def stop(self) -> None:
        self._event_bus.unsubscribe(EventType.ORDER_REQUEST, self._check_order)
        self._event_bus.unsubscribe(EventType.TICK, self._update_price)

    async def _update_price(self, event: Event) -> None:
        tick = event.payload
        assert isinstance(tick, Tick)
        self._latest_prices[tick.symbol] = tick.price

    async def _check_order(self, event: Event) -> None:
        order = event.payload
        assert isinstance(order, OrderRequest)

        price = self._latest_prices.get(order.symbol, Decimal("100"))
        order_value = price * order.quantity

        # Check max order value
        if order_value > Decimal(str(self._settings.max_order_value)):
            await self._reject(
                order,
                "max_order_value_exceeded",
                f"Order value {order_value} exceeds limit {self._settings.max_order_value}",
            )
            return

        # Check max position size
        pos = self._positions.get_position(order.symbol)
        current_qty = pos.quantity if pos else 0
        projected_value = price * abs(current_qty + order.quantity)
        if projected_value > Decimal(str(self._settings.max_position_size)):
            await self._reject(
                order,
                "max_position_size_exceeded",
                f"Projected position {projected_value} exceeds limit {self._settings.max_position_size}",
            )
            return

        # Check max drawdown
        snapshot = self._positions.get_portfolio_snapshot()
        if self._positions._initial_cash > 0:
            drawdown = (
                self._positions._initial_cash - snapshot.total_equity
            ) / self._positions._initial_cash
            if drawdown > Decimal(str(self._settings.max_drawdown_pct)):
                await self._reject(
                    order,
                    "max_drawdown_exceeded",
                    f"Portfolio drawdown {drawdown:.4f} exceeds limit {self._settings.max_drawdown_pct}",
                )
                return

        self._logger.debug("order_approved", order_id=str(order.id))

    async def _reject(
        self, order: OrderRequest, rule: str, message: str
    ) -> None:
        self._logger.warning("risk_breach", rule=rule, message=message)
        await self._event_bus.publish(
            Event(
                type=EventType.RISK_BREACH,
                payload=RiskBreach(rule=rule, message=message),
            )
        )
        await self._event_bus.publish(
            Event(
                type=EventType.ORDER_UPDATE,
                payload=OrderUpdate(
                    order_id=order.id,
                    status=OrderStatus.REJECTED,
                    reason=message,
                ),
            )
        )
