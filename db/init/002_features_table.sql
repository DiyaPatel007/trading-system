-- Module 2: feature storage.
-- Depends on 001_init_timescale.sql having already created the
-- `candles` hypertable -- features are computed FROM candles.

CREATE TABLE IF NOT EXISTS features (
    symbol               TEXT        NOT NULL,
    timeframe            TEXT        NOT NULL,
    ts                   TIMESTAMPTZ NOT NULL,
    feature_set_version  TEXT        NOT NULL,
    features             JSONB       NOT NULL,
    PRIMARY KEY (symbol, timeframe, ts, feature_set_version)
);

SELECT create_hypertable('features', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_features_symbol_tf_version
    ON features (symbol, timeframe, feature_set_version, ts DESC);
