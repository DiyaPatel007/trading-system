-- Module 6: model registry.
-- One row per trained model. Artifacts themselves are saved to disk
-- (see app/config.py's MODEL_ARTIFACT_DIR); this table tracks metadata
-- and the promotion workflow (experimental -> candidate -> production)
-- described in the problem statement's "Model Approval and Promotion
-- Framework" section.

CREATE TABLE IF NOT EXISTS models (
    model_id                TEXT PRIMARY KEY,
    mode                    TEXT NOT NULL,
    trained_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    feature_set_version     TEXT NOT NULL,
    training_window_start   TIMESTAMPTZ NOT NULL,
    training_window_end     TIMESTAMPTZ NOT NULL,
    test_window_start       TIMESTAMPTZ NOT NULL,
    test_window_end         TIMESTAMPTZ NOT NULL,
    artifact_path           TEXT NOT NULL,
    n_training_rows         INT NOT NULL,
    n_test_rows             INT NOT NULL,
    train_win_rate          DOUBLE PRECISION NOT NULL,
    test_win_rate           DOUBLE PRECISION NOT NULL,
    test_accuracy           DOUBLE PRECISION NOT NULL,
    test_auc                DOUBLE PRECISION,
    test_brier_score        DOUBLE PRECISION,
    stage                   TEXT NOT NULL DEFAULT 'experimental',
    notes                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_models_mode_stage ON models (mode, stage);