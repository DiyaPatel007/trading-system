"""
Walk-forward training for the Swing-mode win-probability model.

Chronological split, NOT random: the test set is strictly later in time
than the training set. This is the walk-forward validation requirement
from the problem statement -- randomly shuffling train/test would let
future information leak into training.

Run standalone (after Modules 2 + dataset.py's data is available):
    python -m app.train --mode swing --test-fraction 0.2
"""

import argparse
import logging
import uuid
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg
import xgboost as xgb
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score

from app.config import settings
from app.dataset import FEATURE_COLUMNS, run as build_dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train")

FEATURE_SET_VERSION = "v1"  # matches Module 2's compute_features.py FEATURE_SET_VERSION


def chronological_split(dataset: pd.DataFrame, test_fraction: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Splits by TIME, not row count per symbol -- the cutoff date is chosen
    so that test_fraction of ROWS (across all symbols) fall after it,
    then every symbol is split at that same date. This keeps the split
    genuinely chronological: no training row is ever later than any
    test row.
    """
    dataset = dataset.sort_values("ts").reset_index(drop=True)
    cutoff_idx = int(len(dataset) * (1 - test_fraction))
    cutoff_date = dataset.iloc[cutoff_idx]["ts"]

    train = dataset[dataset["ts"] < cutoff_date]
    test = dataset[dataset["ts"] >= cutoff_date]
    return train, test


def train_model(train_df: pd.DataFrame) -> xgb.XGBClassifier:
    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["label"]

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(X_train, y_train)
    return model


def evaluate_model(model: xgb.XGBClassifier, test_df: pd.DataFrame) -> dict:
    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df["label"]

    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_proba >= 0.5).astype(int)

    metrics = {
        "test_accuracy": accuracy_score(y_test, y_pred),
        "test_win_rate": float(y_test.mean()),
    }
    if y_test.nunique() > 1:
        metrics["test_auc"] = roc_auc_score(y_test, y_pred_proba)
    else:
        metrics["test_auc"] = None
        logger.warning("Test set has only one class -- AUC undefined, skipping")
    metrics["test_brier_score"] = brier_score_loss(y_test, y_pred_proba)

    return metrics


def register_model(
    conn: psycopg.Connection,
    model_id: str,
    mode: str,
    artifact_path: str,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    metrics: dict,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO models
                (model_id, mode, feature_set_version, training_window_start, training_window_end,
                 test_window_start, test_window_end, artifact_path, n_training_rows, n_test_rows,
                 train_win_rate, test_win_rate, test_accuracy, test_auc, test_brier_score, stage)
            VALUES
                (%(model_id)s, %(mode)s, %(feature_set_version)s, %(train_start)s, %(train_end)s,
                 %(test_start)s, %(test_end)s, %(artifact_path)s, %(n_train)s, %(n_test)s,
                 %(train_win_rate)s, %(test_win_rate)s, %(test_accuracy)s, %(test_auc)s,
                 %(test_brier_score)s, 'experimental');
            """,
            {
                "model_id": model_id,
                "mode": mode,
                "feature_set_version": FEATURE_SET_VERSION,
                "train_start": train_df["ts"].min(),
                "train_end": train_df["ts"].max(),
                "test_start": test_df["ts"].min(),
                "test_end": test_df["ts"].max(),
                "artifact_path": artifact_path,
                "n_train": len(train_df),
                "n_test": len(test_df),
                "train_win_rate": float(train_df["label"].mean()),
                "test_win_rate": metrics["test_win_rate"],
                "test_accuracy": metrics["test_accuracy"],
                "test_auc": metrics["test_auc"],
                "test_brier_score": metrics["test_brier_score"],
            },
        )
    conn.commit()


def run(mode: str, test_fraction: float, timeframe: str = "1d") -> None:
    logger.info("Building labeled dataset...")
    dataset = build_dataset(timeframe=timeframe)

    if len(dataset) < 100:
        logger.error(
            "Only %d labeled rows available -- need at least 100 for a meaningful "
            "train/test split. Run more history through Modules 2-3 first.",
            len(dataset),
        )
        return

    train_df, test_df = chronological_split(dataset, test_fraction)
    logger.info(
        "Train: %d rows (%s to %s), Test: %d rows (%s to %s)",
        len(train_df), train_df["ts"].min(), train_df["ts"].max(),
        len(test_df), test_df["ts"].min(), test_df["ts"].max(),
    )

    if train_df["label"].nunique() < 2:
        logger.error("Training set has only one class present -- cannot train a classifier")
        return

    model = train_model(train_df)
    metrics = evaluate_model(model, test_df)
    logger.info("Test metrics: %s", metrics)

    model_id = f"{mode}-{uuid.uuid4().hex[:8]}"
    artifact_dir = Path(settings.model_artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = str(artifact_dir / f"{model_id}.joblib")
    joblib.dump(model, artifact_path)
    logger.info("Saved model artifact to %s", artifact_path)

    with psycopg.connect(settings.postgres_dsn) as conn:
        register_model(conn, model_id, mode, artifact_path, train_df, test_df, metrics)
    logger.info("Registered model %s in the registry (stage=experimental)", model_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk-forward train a swing win-probability model")
    parser.add_argument("--mode", default="swing")
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--timeframe", default="1d")
    args = parser.parse_args()
    run(mode=args.mode, test_fraction=args.test_fraction, timeframe=args.timeframe)