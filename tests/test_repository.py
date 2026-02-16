from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio

from config import Settings
from db.repository import Repository
from models import (
    Fill,
    OrderRequest,
    OrderType,
    PortfolioSnapshot,
    Position,
    Side,
)


def _check_db_available() -> bool:
    import asyncio

    async def _try():
        try:
            settings = Settings()
            repo = Repository(settings)
            await repo.connect()
            await repo.disconnect()
            return True
        except Exception:
            return False

    try:
        return asyncio.run(_try())
    except Exception:
        return False


_db_available = _check_db_available()
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not _db_available, reason="PostgreSQL not available"),
]


@pytest_asyncio.fixture
async def repo():
    settings = Settings()
    r = Repository(settings)
    await r.connect()
    await r.run_migrations()
    yield r
    assert r._pool is not None
    await r._pool.execute("DELETE FROM fills")
    await r._pool.execute("DELETE FROM orders")
    await r._pool.execute("DELETE FROM positions")
    await r._pool.execute("DELETE FROM portfolio_snapshots")
    await r.disconnect()


async def test_connect_and_migrate(repo: Repository):
    assert repo._pool is not None
    rows = await repo._pool.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    table_names = {r["table_name"] for r in rows}
    assert "orders" in table_names
    assert "fills" in table_names
    assert "positions" in table_names
    assert "portfolio_snapshots" in table_names


async def test_insert_and_get_order(repo: Repository):
    order = OrderRequest(
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        strategy_id="test",
    )
    await repo.insert_order(order)

    orders = await repo.get_all_orders()
    assert len(orders) >= 1
    found = [o for o in orders if o["id"] == order.id]
    assert len(found) == 1
    assert found[0]["symbol"] == "AAPL"
    assert found[0]["quantity"] == 100


async def test_insert_fill(repo: Repository):
    order = OrderRequest(
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
    )
    await repo.insert_order(order)

    fill = Fill(
        order_id=order.id,
        symbol="AAPL",
        side=Side.BUY,
        quantity=100,
        price=Decimal("150.0000"),
    )
    await repo.insert_fill(fill)

    fills = await repo.get_fills_for_order(order.id)
    assert len(fills) == 1
    assert fills[0]["price"] == Decimal("150.000000")


async def test_upsert_position(repo: Repository):
    pos = Position(
        symbol="AAPL",
        quantity=100,
        avg_entry_price=Decimal("150.0000"),
        realized_pnl=Decimal("0"),
    )
    await repo.upsert_position(pos)

    pos2 = Position(
        symbol="AAPL",
        quantity=200,
        avg_entry_price=Decimal("155.0000"),
        realized_pnl=Decimal("50"),
    )
    await repo.upsert_position(pos2)

    positions = await repo.get_all_positions()
    aapl = [p for p in positions if p["symbol"] == "AAPL"]
    assert len(aapl) == 1
    assert aapl[0]["quantity"] == 200


async def test_insert_snapshot(repo: Repository):
    snapshot = PortfolioSnapshot(
        timestamp=datetime.now(UTC),
        positions={},
        total_equity=Decimal("100000"),
        total_unrealized_pnl=Decimal("500"),
        total_realized_pnl=Decimal("200"),
    )
    await repo.insert_snapshot(snapshot)

    snapshots = await repo.get_snapshots(limit=10)
    assert len(snapshots) >= 1
    assert snapshots[0]["total_equity"] == Decimal("100000.000000")
