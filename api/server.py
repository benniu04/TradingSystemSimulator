import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
import structlog

from core.event_bus import EventBus
from db.repository import Repository
from execution.order_manager import OrderManager
from risk.position_tracker import PositionTracker

logger = structlog.get_logger(__name__)


def create_app(
    event_bus: EventBus,
    position_tracker: PositionTracker,
    order_manager: OrderManager,
    repository: Repository,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("api_starting")
        yield
        logger.info("api_stopping")

    app = FastAPI(
        title="Trading System Simulator",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/portfolio")
    async def get_portfolio():
        snapshot = position_tracker.get_portfolio_snapshot()
        return snapshot.model_dump(mode="json")

    @app.get("/positions")
    async def get_positions():
        snapshot = position_tracker.get_portfolio_snapshot()
        return {
            k: v.model_dump(mode="json")
            for k, v in snapshot.positions.items()
        }

    @app.get("/positions/{symbol}")
    async def get_position(symbol: str):
        pos = position_tracker.get_position(symbol.upper())
        if pos is None:
            raise HTTPException(status_code=404, detail="Position not found")
        return pos.model_dump(mode="json")

    @app.get("/orders")
    async def get_orders():
        return await repository.get_all_orders()

    @app.get("/orders/{order_id}/fills")
    async def get_order_fills(order_id: UUID):
        return await repository.get_fills_for_order(order_id)

    @app.websocket("/ws/portfolio")
    async def ws_portfolio(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                snapshot = position_tracker.get_portfolio_snapshot()
                await websocket.send_json(snapshot.model_dump(mode="json"))
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            logger.info("ws_client_disconnected")

    return app
