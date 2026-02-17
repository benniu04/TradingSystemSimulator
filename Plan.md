## High Performance Trading System Simulator (Python)

Goal: Build a production style trading backend that ingests market data, executes strategies, and tracks positions and P&L with low latency and high reliability

Tech Stack: Python, Linux, PostgreSQL, asyncio/multiprocessing, REST/WebSocket, APIs, pytest, Git.

What it does:
Simulates real-time market data feeds, runs trading strategies against live price streams, places simulated orders, updates positions and balances, persists trades to a relational database, and computes real-time risk and P&L. Includes logging, basic monitoring and failure recovery

Architecture Overview

     SyntheticFeed/AlpacaFeed
         → TICK → StrategyEngine → SIGNAL → OrderManager → ORDER_REQUEST → RiskManager
                                                          → FILL → PositionTracker → POSITION_UPDATE
                                                                                   → PersistenceService → PostgreSQL
     API Server (FastAPI) reads from PositionTracker, OrderManager, Repository

     All modules communicate via an async EventBus (pub/sub). All data crossing module boundaries uses Pydantic models defined in a shared models.py.

     ---
     Phase 0: Config, Shared Models, Docker, Scaffolding

     New files: models.py, docker-compose.yml, .env.example, __init__.py in all packages

     config.py — Settings via pydantic-settings

     - Settings(BaseSettings) with fields: DB connection (host/port/user/pass/name), API (host/port), Alpaca credentials, risk limits (max_position_size,
     max_order_value, max_drawdown_pct), log_level, use_synthetic_feed flag
     - db_dsn property for connection string
     - Loaded from .env via python-dotenv
     - Note: Add pydantic-settings to pyproject.toml dependencies

     models.py — All shared Pydantic models (prevents circular imports)

     - Enums: Side (buy/sell), OrderType (market/limit), OrderStatus (pending/submitted/filled/partially_filled/cancelled/rejected), EventType
     (tick/signal/order_request/order_update/fill/position_update/risk_breach)
     - Market data: Tick (symbol, price, volume, bid, ask, timestamp), Bar (OHLCV)
     - Orders: OrderRequest (id UUID, symbol, side, quantity, order_type, limit_price, strategy_id), OrderUpdate, Fill
     - Signals: Signal (strategy_id, symbol, side, strength 0-1)
     - Positions: Position (symbol, quantity, avg_entry_price, current_price, unrealized/realized_pnl), PortfolioSnapshot
     - Event envelope: Event (type, payload, timestamp)
     - Risk: RiskBreach (rule, message)

     docker-compose.yml

     - PostgreSQL 16 Alpine, user/pass/db = trader/trader/trading, port 5432, named volume

     Verification

     - python -c "from config import get_settings; print(get_settings())" works
     - python -c "from models import Tick, Event; print('OK')" works
     - docker-compose up -d starts PostgreSQL

     ---
     Phase 1: Event Bus — core/event_bus.py

     Async in-process pub/sub. Subscribers register for specific EventType values.

     Key design:
     - subscribe(event_type, handler), unsubscribe(event_type, handler), async publish(event)
     - asyncio.gather(*handlers, return_exceptions=True) — one bad handler can't block others
     - Bounded history buffer (1000 events) for debugging
     - No thread safety needed (single event loop)

     Tests (tests/test_event_bus.py): subscribe/publish, multiple subscribers, no cross-delivery, handler exception isolation, unsubscribe, history, history bounded at
     1000

     ---
     Phase 2: Market Data — feeds/market_data.py

     Abstract MarketDataFeed base class with two implementations:

     SyntheticFeed

     - Geometric Brownian motion price generation
     - Configurable tick interval, volatility, base prices
     - Publishes Event(TICK, Tick(...)) per symbol per interval

     AlpacaFeed

     - Connects to wss://stream.data.alpaca.markets/v2/iex
     - Authenticates with API key/secret, subscribes to trades
     - Falls back to SyntheticFeed on connection failure or stream error

     Tests (tests/test_market_data.py — new file): synthetic publishes ticks, prices stay positive, disconnect stops streaming, Alpaca falls back on failure

     ---
     Phase 3: Strategies — strategies/base.py, engine.py, mean_reversion.py

     base.py — Abstract Strategy

     - async on_tick(tick) -> Signal | None
     - reset() for backtesting restarts

     mean_reversion.py — MeanReversionStrategy

     - Rolling window of prices (deque, configurable window_size)
     - Computes z-score; generates BUY signal when z < -entry_z, SELL when z > entry_z
     - Signal strength = normalized z-score (0-1)

     engine.py — StrategyEngine

     - Subscribes to TICK events, dispatches to registered strategies
     - Publishes resulting SIGNAL events back onto the bus
     - Filters ticks by strategy's symbol list

     Tests (tests/test_strategy.py): insufficient data returns None, buy/sell signals at extremes, no signal within band, reset clears state, engine dispatches and
     publishes, engine filters by symbol

     ---
     Phase 4: Execution — execution/order_manager.py

     OrderManager

     - Subscribes to SIGNAL and TICK events
     - Converts signals to OrderRequest (quantity = strength * 100)
     - Publishes ORDER_REQUEST (for risk validation)
     - Simulates fill after small delay with slippage (buy fills above market, sell below)
     - Publishes FILL events
     - Maintains order book (dict by UUID)

     Tests (tests/test_order_manager.py): signal creates order, signal produces fill, fill price near market with correct slippage direction, quantity from strength,
     get_order_by_id

     ---
     Phase 5: Risk — risk/position_tracker.py, risk/risk_manager.py

     position_tracker.py — PositionTracker

     - Subscribes to FILL and TICK events
     - Maintains per-symbol positions with avg_entry_price, realized/unrealized P&L
     - Tracks cash balance (starts at $100,000)
     - get_portfolio_snapshot() returns totals
     - Publishes POSITION_UPDATE events on fills

     risk_manager.py — RiskManager

     - Subscribes to ORDER_REQUEST and TICK events
     - Validates against: max order value, max position size, max drawdown
     - On breach: publishes RISK_BREACH + ORDER_UPDATE(REJECTED)

     Tests (tests/test_position_tracker.py): buy creates position, sell creates short, realized P&L on round-trip, tick updates unrealized, portfolio snapshot totals,
     cash tracking

     Tests (tests/test_risk_manager.py — new file): order within limits passes, exceeds max value rejected, position size limit, drawdown limit

     ---
     Phase 6: Database — db/repository.py, db/migrations/, db/persistence.py

     db/migrations/001_initial.sql

     - Tables: orders, fills, positions, portfolio_snapshots
     - Indexes on order_id, symbol, status, snapshot_at

     db/repository.py — Repository

     - asyncpg connection pool (min=2, max=10)
     - run_migrations() — executes SQL files in sorted order
     - CRUD: insert_order, insert_fill, update_order_status, upsert_position, insert_snapshot
     - Queries: get_all_orders, get_fills_for_order, get_all_positions, get_snapshots

     db/persistence.py — PersistenceService (new file)

     - Subscribes to ORDER_REQUEST, FILL, POSITION_UPDATE events
     - Persists each to DB via Repository

     Tests (tests/test_repository.py — new file): connect/migrate, insert/get order, insert fill, upsert position, insert snapshot. Requires running PostgreSQL.

     ---
     Phase 7: API — api/server.py

     FastAPI app factory pattern: create_app(event_bus, position_tracker, order_manager, repository).

     REST Endpoints:
     - GET /health — status + uptime
     - GET /portfolio — full portfolio snapshot
     - GET /positions — all positions
     - GET /positions/{symbol} — single position (404 if not found)
     - GET /orders — all orders from DB
     - GET /orders/{order_id}/fills — fills for an order

     WebSocket:
     - WS /ws/portfolio — pushes portfolio snapshot every 1 second

     Tests (tests/test_api.py — new file): health endpoint, portfolio, positions, 404 for unknown symbol, orders list, WebSocket receives data

     ---
     Phase 8: Main — main.py

     Wire everything together:
     1. Load settings, configure structlog
     2. Connect to DB, run migrations
     3. Construct: EventBus → PositionTracker → RiskManager → OrderManager → PersistenceService → StrategyEngine → MarketDataFeed
     4. Start all services
     5. Run feed streaming + API server + periodic snapshot loop concurrently
     6. Handle SIGINT/SIGTERM for graceful shutdown (stop services in reverse order)

     Verification: python main.py starts full system; logs show tick flow, signals, fills, position updates. REST API responds. Ctrl+C triggers clean shutdown.

     ---
     Phase 9: Integration Testing & Polish

     Integration tests (tests/test_integration.py — new file)

     - Full pipeline with synthetic feed runs for 5s, produces ticks → signals → fills → positions
     - Risk manager blocks oversized orders
     - Persistence roundtrip (data in DB after run)
     - Graceful shutdown with no exceptions

     Shared fixtures (tests/conftest.py)

     - event_bus, settings fixtures
     - DB fixtures for tests requiring PostgreSQL

     Polish

     - [tool.ruff] config in pyproject.toml
     - [tool.mypy] strict mode with pydantic plugin
     - [tool.pytest.ini_options] asyncio_mode = "auto"
     - ruff check . and mypy . pass clean
     - pytest --cov > 80% coverage
