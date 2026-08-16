-- Module 1: foundational schema.
-- Later modules (2: market data, 4: risk, 6: ML registry, 7: paper trading,
-- 9: journal) will each add their own migration files here, numbered
-- sequentially (002_, 003_, ...). Keep every migration idempotent.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Raw OHLCV candles, one hypertable partitioned by time. This is the
-- table the Market Data Service (Module 2) will write into.
CREATE TABLE IF NOT EXISTS candles (
    symbol      TEXT        NOT NULL,
    timeframe   TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      BIGINT      NOT NULL,
    freshness   TEXT        NOT NULL DEFAULT 'historical',
    PRIMARY KEY (symbol, timeframe, ts)
);

-- Convert to a hypertable if not already done (safe to re-run).
SELECT create_hypertable('candles', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf
    ON candles (symbol, timeframe, ts DESC);

-- A minimal system_health table lets core-api prove writes work too,
-- not just SELECT 1 -- used by the verification steps below.
CREATE TABLE IF NOT EXISTS system_health_checks (
    id          SERIAL PRIMARY KEY,
    checked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    note        TEXT
);
