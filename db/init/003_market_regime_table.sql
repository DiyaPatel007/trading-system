-- Module 3: market regime storage.
-- One row per trading day, derived from breadth/trend/volatility across
-- the whole NIFTY 50 universe. Downstream services (scanner, risk
-- engine, backtests) join against this by date rather than recomputing
-- regime themselves.

CREATE TABLE IF NOT EXISTS market_regime (
    ts                      TIMESTAMPTZ NOT NULL,
    regime                  TEXT        NOT NULL,
    confidence              DOUBLE PRECISION NOT NULL,
    trend_score             DOUBLE PRECISION NOT NULL,
    volatility_score        DOUBLE PRECISION NOT NULL,
    breadth_pct_above_ema20 DOUBLE PRECISION NOT NULL,
    contributing_factors    JSONB       NOT NULL,
    PRIMARY KEY (ts)
);

SELECT create_hypertable('market_regime', 'ts', if_not_exists => TRUE);