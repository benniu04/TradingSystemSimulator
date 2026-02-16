import asyncio
import signal

import structlog
import uvicorn

from api.server import create_app
from config import get_settings
from core.event_bus import EventBus
from db.persistence import PersistenceService
from db.repository import Repository
from execution.order_manager import OrderManager
from feeds.market_data import AlpacaFeed, SyntheticFeed
from risk.position_tracker import PositionTracker
from risk.risk_manager import RiskManager
from strategies.engine import StrategyEngine
from strategies.mean_reversion import MeanReversionStrategy

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
)

logger = structlog.get_logger("main")


async def main() -> None:
    settings = get_settings()
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    # ── Construct components ────────────────────
    event_bus = EventBus()

    # Database
    repo = Repository(settings)
    await repo.connect()
    await repo.run_migrations()

    # Core services
    position_tracker = PositionTracker(event_bus)
    risk_manager = RiskManager(event_bus, position_tracker, settings)
    order_manager = OrderManager(event_bus, settings, risk_manager)
    persistence = PersistenceService(event_bus, repo)

    # Strategy
    symbols = ["AAPL", "MSFT", "GOOGL"]
    strategy = MeanReversionStrategy(symbols=symbols)
    engine = StrategyEngine(event_bus)
    engine.register_strategy(strategy)

    # Market data feed
    if settings.use_synthetic_feed:
        feed = SyntheticFeed(event_bus, symbols, tick_interval=0.5)
    else:
        feed = AlpacaFeed(event_bus, symbols, settings)

    # API server
    app = create_app(event_bus, position_tracker, order_manager, repo)

    # ── Start everything ────────────────────────
    await position_tracker.start()
    await risk_manager.start()
    await order_manager.start()
    await persistence.start()
    await engine.start()
    await feed.connect()

    logger.info("all_services_started")

    # Run feed + API concurrently
    api_config = uvicorn.Config(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )
    api_server = uvicorn.Server(api_config)

    feed_task = asyncio.create_task(feed.start_streaming())
    asyncio.create_task(api_server.serve())

    # Periodic snapshot persistence
    async def snapshot_loop() -> None:
        while not shutdown_event.is_set():
            await asyncio.sleep(60)
            snapshot = position_tracker.get_portfolio_snapshot()
            await repo.insert_snapshot(snapshot)
            logger.info("snapshot_persisted")

    snapshot_task = asyncio.create_task(snapshot_loop())

    # Wait for shutdown signal
    await shutdown_event.wait()
    logger.info("shutdown_initiated")

    # ── Graceful shutdown ───────────────────────
    await feed.disconnect()
    await engine.stop()
    await order_manager.stop()
    await risk_manager.stop()
    await position_tracker.stop()
    await persistence.stop()
    api_server.should_exit = True
    await repo.disconnect()

    feed_task.cancel()
    snapshot_task.cancel()
    try:
        await feed_task
    except asyncio.CancelledError:
        pass
    try:
        await snapshot_task
    except asyncio.CancelledError:
        pass

    logger.info("shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
