-- Module 7: paper trading storage.
-- One row per paper trade, opened from a Module 5 scanner_results
-- ranked signal and closed by monitor_trades.py once it resolves.

CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id                TEXT PRIMARY KEY,
    symbol                   TEXT NOT NULL,
    mode                      TEXT NOT NULL,
    scanner_ts                TIMESTAMPTZ NOT NULL,
    status                     TEXT NOT NULL DEFAULT 'open',
    predicted_entry            DOUBLE PRECISION NOT NULL,
    actual_entry                DOUBLE PRECISION NOT NULL,
    stop_loss                    DOUBLE PRECISION NOT NULL,
    target                        DOUBLE PRECISION NOT NULL,
    quantity                      INT NOT NULL,
    opened_at                      TIMESTAMPTZ NOT NULL,
    closed_at                       TIMESTAMPTZ,
    exit_signal_price                 DOUBLE PRECISION,
    actual_exit_price                  DOUBLE PRECISION,
    gross_pnl                           DOUBLE PRECISION,
    total_costs                          DOUBLE PRECISION,
    net_pnl                               DOUBLE PRECISION,
    max_favorable_excursion               DOUBLE PRECISION,
    max_adverse_excursion                  DOUBLE PRECISION,
    model_id                                TEXT,
    risk_category                            TEXT,
    reasoning                                 JSONB
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_status ON paper_trades (status);
CREATE INDEX IF NOT EXISTS idx_paper_trades_symbol ON paper_trades (symbol, opened_at DESC);