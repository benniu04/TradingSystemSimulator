CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL,
    quantity INTEGER NOT NULL,
    order_type VARCHAR(10) NOT NULL,
    limit_price NUMERIC(18, 6),
    strategy_id VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fills (
    id SERIAL PRIMARY KEY,
    order_id UUID REFERENCES orders(id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(4) NOT NULL,
    quantity INTEGER NOT NULL,
    price NUMERIC(18, 6) NOT NULL,
    filled_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS positions (
    symbol VARCHAR(20) PRIMARY KEY,
    quantity INTEGER NOT NULL DEFAULT 0,
    avg_entry_price NUMERIC(18, 6) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18, 6) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    total_equity NUMERIC(18, 6) NOT NULL,
    total_unrealized_pnl NUMERIC(18, 6) NOT NULL,
    total_realized_pnl NUMERIC(18, 6) NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fills_order_id ON fills(order_id);
CREATE INDEX IF NOT EXISTS idx_fills_symbol ON fills(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_at ON portfolio_snapshots(snapshot_at);
