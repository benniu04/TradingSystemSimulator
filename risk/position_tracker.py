from datetime import UTC, datetime
from decimal import Decimal

import structlog

from core.event_bus import EventBus
from models import (
    Event,
    EventType,
    Fill,
    PortfolioSnapshot,
    Position,
    Side,
    Tick,
)


class PositionTracker:
    def __init__(
        self,
        event_bus: EventBus,
        initial_cash: Decimal = Decimal("100000"),
    ) -> None:
        self._event_bus = event_bus
        self._positions: dict[str, Position] = {}
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._logger = structlog.get_logger(__name__)

    async def start(self) -> None:
        self._event_bus.subscribe(EventType.FILL, self._handle_fill)
        self._event_bus.subscribe(EventType.TICK, self._handle_tick)
        self._logger.info("position_tracker_started")

    async def stop(self) -> None:
        self._event_bus.unsubscribe(EventType.FILL, self._handle_fill)
        self._event_bus.unsubscribe(EventType.TICK, self._handle_tick)

    async def _handle_fill(self, event: Event) -> None:
        fill = event.payload
        assert isinstance(fill, Fill)

        pos = self._positions.get(fill.symbol, Position(symbol=fill.symbol))
        cost = fill.price * fill.quantity

        if fill.side == Side.BUY:
            if pos.quantity >= 0:
                # Adding to long or opening long
                total_cost = pos.avg_entry_price * pos.quantity + cost
                new_qty = pos.quantity + fill.quantity
                new_avg = total_cost / new_qty if new_qty > 0 else Decimal("0")
            else:
                # Closing/reducing short
                close_qty = min(fill.quantity, abs(pos.quantity))
                realized = (pos.avg_entry_price - fill.price) * close_qty
                pos = pos.model_copy(
                    update={"realized_pnl": pos.realized_pnl + realized}
                )
                new_qty = pos.quantity + fill.quantity
                new_avg = pos.avg_entry_price if new_qty < 0 else fill.price
            self._cash -= cost
        else:
            if pos.quantity <= 0:
                # Adding to short or opening short
                new_qty = pos.quantity - fill.quantity
                new_avg = fill.price if pos.quantity == 0 else pos.avg_entry_price
            else:
                # Closing/reducing long
                close_qty = min(fill.quantity, pos.quantity)
                realized = (fill.price - pos.avg_entry_price) * close_qty
                pos = pos.model_copy(
                    update={"realized_pnl": pos.realized_pnl + realized}
                )
                new_qty = pos.quantity - fill.quantity
                new_avg = pos.avg_entry_price if new_qty > 0 else Decimal("0")
            self._cash += cost

        pos = pos.model_copy(
            update={
                "quantity": new_qty,
                "avg_entry_price": (
                    new_avg.quantize(Decimal("0.0001"))
                    if isinstance(new_avg, Decimal)
                    else new_avg
                ),
            }
        )
        self._positions[fill.symbol] = pos

        self._logger.info(
            "position_updated",
            symbol=fill.symbol,
            qty=new_qty,
            avg_price=str(pos.avg_entry_price),
        )

        await self._event_bus.publish(
            Event(type=EventType.POSITION_UPDATE, payload=pos)
        )

    async def _handle_tick(self, event: Event) -> None:
        tick = event.payload
        assert isinstance(tick, Tick)
        if tick.symbol in self._positions:
            pos = self._positions[tick.symbol]
            unrealized = (tick.price - pos.avg_entry_price) * pos.quantity
            self._positions[tick.symbol] = pos.model_copy(
                update={
                    "current_price": tick.price,
                    "unrealized_pnl": unrealized,
                }
            )

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        total_unrealized = sum(
            p.unrealized_pnl for p in self._positions.values()
        )
        total_realized = sum(
            p.realized_pnl for p in self._positions.values()
        )
        position_value = sum(
            p.current_price * p.quantity for p in self._positions.values()
        )
        return PortfolioSnapshot(
            timestamp=datetime.now(UTC),
            positions=dict(self._positions),
            total_equity=self._cash + position_value,
            total_unrealized_pnl=total_unrealized,
            total_realized_pnl=total_realized,
        )
