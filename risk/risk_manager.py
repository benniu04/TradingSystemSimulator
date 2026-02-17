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
    Side,
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
        self._event_bus.subscribe(EventType.TICK, self._update_price)
        self._logger.info("risk_manager_started")

    async def stop(self) -> None:
        self._event_bus.unsubscribe(EventType.TICK, self._update_price)

    async def _update_price(self, event: Event) -> None:
        tick = event.payload
        assert isinstance(tick, Tick)
        self._latest_prices[tick.symbol] = tick.price

    def check_order(self, order: OrderRequest) -> tuple[bool, str]:
        """Check if an order passes all risk limits.

        Returns (approved, reason). If approved is False, reason explains why.
        """
        price = self._latest_prices.get(order.symbol, Decimal("100"))
        order_value = price * order.quantity

        # Check max order value
        max_order = Decimal(str(self._settings.max_order_value))
        if order_value > max_order:
            return False, f"Order value {order_value} exceeds limit {max_order}"

        # Check max position size (account for buy vs sell direction)
        pos = self._positions.get_position(order.symbol)
        current_qty = pos.quantity if pos else 0
        if order.side == Side.BUY:
            projected_qty = current_qty + order.quantity
        else:
            projected_qty = current_qty - order.quantity
        projected_value = price * abs(projected_qty)
        max_pos = Decimal(str(self._settings.max_position_size))
        if projected_value > max_pos:
            return False, f"Projected position {projected_value} exceeds limit {max_pos}"

        # Check max drawdown
        snapshot = self._positions.get_portfolio_snapshot()
        if self._positions._initial_cash > 0:
            drawdown = (
                self._positions._initial_cash - snapshot.total_equity
            ) / self._positions._initial_cash
            max_dd = Decimal(str(self._settings.max_drawdown_pct))
            if drawdown > max_dd:
                return False, f"Portfolio drawdown {drawdown:.4f} exceeds limit {max_dd}"

        return True, ""

    async def reject_order(self, order: OrderRequest, reason: str) -> None:
        """Publish rejection events for a blocked order."""
        self._logger.warning("risk_breach", order_id=str(order.id), reason=reason)
        await self._event_bus.publish(
            Event(
                type=EventType.RISK_BREACH,
                payload=RiskBreach(rule="order_rejected", message=reason),
            )
        )
        await self._event_bus.publish(
            Event(
                type=EventType.ORDER_UPDATE,
                payload=OrderUpdate(
                    order_id=order.id,
                    status=OrderStatus.REJECTED,
                    reason=reason,
                ),
            )
        )
