-- Module 9: Trade Guardian alert history.
-- One row per (trade, check run) -- NOT a mutation of paper_trades.
-- Per the problem statement, hard risk controls (stop-loss, exits) stay
-- independent of this analysis layer; this table only ever grows, it
-- never causes paper_trades to be modified.

CREATE TABLE IF NOT EXISTS trade_guardian_alerts (
    id                       SERIAL PRIMARY KEY,
    trade_id                  TEXT NOT NULL,
    checked_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_price                DOUBLE PRECISION NOT NULL,
    alert_level                    TEXT NOT NULL,
    original_risk_category           TEXT NOT NULL,
    updated_risk_category              TEXT NOT NULL,
    adverse_excursion_pct                DOUBLE PRECISION NOT NULL,
    alerts                                JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_guardian_alerts_trade ON trade_guardian_alerts (trade_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_guardian_alerts_level ON trade_guardian_alerts (alert_level) WHERE alert_level != 'none';