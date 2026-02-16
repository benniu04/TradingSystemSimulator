from __future__ import annotations

import enum
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────


class Side(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class EventType(str, enum.Enum):
    TICK = "tick"
    SIGNAL = "signal"
    ORDER_REQUEST = "order_request"
    ORDER_UPDATE = "order_update"
    FILL = "fill"
    POSITION_UPDATE = "position_update"
    RISK_BREACH = "risk_breach"


# ── Market Data ────────────────────────────────────────


class Tick(BaseModel):
    symbol: str
    price: Decimal
    volume: int
    bid: Decimal
    ask: Decimal
    timestamp: datetime


class Bar(BaseModel):
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    timestamp: datetime


# ── Orders ─────────────────────────────────────────────


class OrderRequest(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: Decimal | None = None
    strategy_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrderUpdate(BaseModel):
    order_id: UUID
    status: OrderStatus
    filled_quantity: int = 0
    filled_price: Decimal | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str = ""


class Fill(BaseModel):
    order_id: UUID
    symbol: str
    side: Side
    quantity: int
    price: Decimal
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Signals ────────────────────────────────────────────


class Signal(BaseModel):
    strategy_id: str
    symbol: str
    side: Side
    strength: float  # 0.0 to 1.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Positions / P&L ───────────────────────────────────


class Position(BaseModel):
    symbol: str
    quantity: int = 0
    avg_entry_price: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")


class PortfolioSnapshot(BaseModel):
    timestamp: datetime
    positions: dict[str, Position]
    total_equity: Decimal
    total_unrealized_pnl: Decimal
    total_realized_pnl: Decimal


# ── Risk ───────────────────────────────────────────────


class RiskBreach(BaseModel):
    rule: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Event Bus Envelope ─────────────────────────────────

EventPayload = Annotated[
    Union[Tick, Signal, OrderRequest, OrderUpdate, Fill, Position, RiskBreach],
    Field(discriminator=None),
]


class Event(BaseModel):
    type: EventType
    payload: EventPayload
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
