-- Module 5: scanner results storage.
-- Records EVERY scanned candidate, not just the top N shown to the user
-- -- this is the foundation for later comparing "what the scanner said"
-- against "what actually happened" (Module 7+ journal), and for
-- tracking untaken signals per the original problem statement.

CREATE TABLE IF NOT EXISTS scanner_results (
    ts                     TIMESTAMPTZ NOT NULL,
    symbol                 TEXT        NOT NULL,
    mode                   TEXT        NOT NULL DEFAULT 'swing',
    rank                   INT,                    -- NULL if not in the top N that day
    composite_score        DOUBLE PRECISION NOT NULL,
    entry_price            DOUBLE PRECISION NOT NULL,
    stop_loss              DOUBLE PRECISION NOT NULL,
    target                 DOUBLE PRECISION NOT NULL,
    reward_to_risk_ratio   DOUBLE PRECISION NOT NULL,
    expected_value_r       DOUBLE PRECISION NOT NULL,
    risk_category          TEXT        NOT NULL,
    approved               BOOLEAN     NOT NULL,
    regime                 TEXT        NOT NULL,
    reasoning              JSONB       NOT NULL,
    PRIMARY KEY (ts, symbol, mode)
);

SELECT create_hypertable('scanner_results', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_scanner_results_ts_rank
    ON scanner_results (ts, rank) WHERE rank IS NOT NULL;