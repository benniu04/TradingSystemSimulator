# Trading System Simulator

A production-style trading backend that ingests market data, executes strategies, manages orders, tracks positions, and computes real-time P&L.

## What It Does

- Streams real-time market data (synthetic or via Alpaca API)
- Runs trading strategies against live price feeds
- Places and fills simulated orders with realistic slippage
- Tracks positions, cash balance, and portfolio value
- Enforces risk limits (max order size, position size, drawdown)
- Persists all trades and positions to PostgreSQL
- Exposes a REST API and WebSocket for live portfolio monitoring

## Tech Stack

Python 3.13+ | FastAPI | PostgreSQL | asyncio | Pydantic

## Quick Start

### 1. Install dependencies

```bash
poetry install
```

### 2. Start the database

```bash
docker compose up -d
```

### 3. Run the system

```bash
poetry run python main.py
```

The system will start streaming synthetic market data, running strategies, and serving the API on `http://localhost:8000`.

### 4. Check it out

```bash
curl http://localhost:8000/health
curl http://localhost:8000/portfolio
curl http://localhost:8000/positions
```

## Configuration

Copy `.env.example` to `.env` to customize settings. Key options:

- `USE_SYNTHETIC_FEED` - set to `false` to use real Alpaca market data (requires API keys)
- `MAX_ORDER_VALUE` / `MAX_POSITION_SIZE` / `MAX_DRAWDOWN_PCT` - risk limits

## Running Tests

```bash
poetry run pytest
```

## Project Structure

```
core/           Event bus (pub/sub messaging between modules)
feeds/          Market data streaming (synthetic + Alpaca)
strategies/     Trading strategies (mean reversion included)
execution/      Order management and simulated fills
risk/           Position tracking, P&L, and risk limits
db/             PostgreSQL persistence and migrations
api/            REST API and WebSocket server
```
