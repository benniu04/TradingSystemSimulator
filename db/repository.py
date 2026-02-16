import pathlib
from uuid import UUID

import asyncpg
import structlog

from config import Settings
from models import Fill, OrderRequest, PortfolioSnapshot, Position


class Repository:
    def __init__(self, settings: Settings) -> None:
        self._dsn = settings.db_dsn
        self._pool: asyncpg.Pool | None = None
        self._logger = structlog.get_logger(__name__)

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            dsn=self._dsn, min_size=2, max_size=10
        )
        self._logger.info("db_connected")

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._logger.info("db_disconnected")

    async def run_migrations(self) -> None:
        migrations_dir = pathlib.Path(__file__).parent / "migrations"
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            for sql_file in sorted(migrations_dir.glob("*.sql")):
                sql = sql_file.read_text()
                await conn.execute(sql)
                self._logger.info("migration_applied", file=sql_file.name)

    async def insert_order(self, order: OrderRequest) -> None:
        assert self._pool is not None
        await self._pool.execute(
            """INSERT INTO orders (id, symbol, side, quantity, order_type, limit_price, strategy_id, status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            order.id,
            order.symbol,
            order.side.value,
            order.quantity,
            order.order_type.value,
            order.limit_price,
            order.strategy_id,
            "pending",
        )

    async def insert_fill(self, fill: Fill) -> None:
        assert self._pool is not None
        await self._pool.execute(
            """INSERT INTO fills (order_id, symbol, side, quantity, price, filled_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            fill.order_id,
            fill.symbol,
            fill.side.value,
            fill.quantity,
            fill.price,
            fill.timestamp,
        )

    async def update_order_status(self, order_id: UUID, status: str) -> None:
        assert self._pool is not None
        await self._pool.execute(
            "UPDATE orders SET status = $1 WHERE id = $2", status, order_id
        )

    async def upsert_position(self, position: Position) -> None:
        assert self._pool is not None
        await self._pool.execute(
            """INSERT INTO positions (symbol, quantity, avg_entry_price, realized_pnl)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (symbol) DO UPDATE SET
                   quantity = EXCLUDED.quantity,
                   avg_entry_price = EXCLUDED.avg_entry_price,
                   realized_pnl = EXCLUDED.realized_pnl,
                   updated_at = NOW()""",
            position.symbol,
            position.quantity,
            position.avg_entry_price,
            position.realized_pnl,
        )

    async def insert_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        assert self._pool is not None
        await self._pool.execute(
            """INSERT INTO portfolio_snapshots (total_equity, total_unrealized_pnl, total_realized_pnl, snapshot_at)
               VALUES ($1, $2, $3, $4)""",
            snapshot.total_equity,
            snapshot.total_unrealized_pnl,
            snapshot.total_realized_pnl,
            snapshot.timestamp,
        )

    async def get_all_orders(self) -> list[dict]:
        assert self._pool is not None
        rows = await self._pool.fetch(
            "SELECT * FROM orders ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]

    async def get_fills_for_order(self, order_id: UUID) -> list[dict]:
        assert self._pool is not None
        rows = await self._pool.fetch(
            "SELECT * FROM fills WHERE order_id = $1 ORDER BY filled_at",
            order_id,
        )
        return [dict(r) for r in rows]

    async def get_all_positions(self) -> list[dict]:
        assert self._pool is not None
        rows = await self._pool.fetch("SELECT * FROM positions")
        return [dict(r) for r in rows]

    async def get_snapshots(self, limit: int = 100) -> list[dict]:
        assert self._pool is not None
        rows = await self._pool.fetch(
            "SELECT * FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT $1",
            limit,
        )
        return [dict(r) for r in rows]
