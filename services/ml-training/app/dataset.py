"""
Builds the labeled training dataset from real candles + features.

For each (symbol, date) with usable features, generates an ATR-based
swing setup (same STOP_ATR_MULTIPLE/TARGET_R_MULTIPLE approach as
Module 5's setup_generation.py, kept independent here rather than
imported, since ML labeling needing to change independently of the
live scanner's setup logic is a reasonable future possibility) and
labels it using ONLY strictly-future bars.

LEAKAGE DISCIPLINE: the future-bars slice for date at index i is
candles[i+1 : i+1+max_holding_days] -- note i+1, never i. The signal
day's own bar is never part of its own outcome evaluation. This is the
single most important line in this file; the accompanying test
(test_dataset.py) checks this explicitly with a synthetic case.
"""

import logging

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from app.config import settings
from app.labeling import FutureBar, label_trade

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dataset")

STOP_ATR_MULTIPLE = 1.5
TARGET_R_MULTIPLE = 2.0
MAX_HOLDING_DAYS = 10

FEATURE_COLUMNS = [
    "ema_20", "ema_50", "sma_200", "rsi_14", "macd", "macd_signal", "macd_hist",
    "atr_14", "volume_sma_20", "volume_ratio", "daily_return_pct", "distance_from_ema20_pct",
]


def load_joined_data(conn: psycopg.Connection, timeframe: str) -> pd.DataFrame:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                c.symbol, c.ts, c.high, c.low, c.close,
                f.features
            FROM candles c
            JOIN features f
              ON f.symbol = c.symbol AND f.timeframe = c.timeframe AND f.ts = c.ts
            WHERE c.timeframe = %s
            ORDER BY c.symbol, c.ts;
            """,
            (timeframe,),
        )
        rows = cur.fetchall()
    return pd.DataFrame(rows)


def build_labeled_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    df: output of load_joined_data (or an equivalent synthetic frame in
    tests), with columns: symbol, ts, high, low, close, features (dict).

    Returns a DataFrame with one row per (symbol, ts) that produced a
    resolved (non-None) label, containing: symbol, ts, entry_price,
    stop_loss, target, label, and one column per FEATURE_COLUMNS entry.
    """
    df = df.sort_values(["symbol", "ts"]).reset_index(drop=True)
    records = []

    for symbol, group in df.groupby("symbol"):
        group = group.reset_index(drop=True)
        for i in range(len(group)):
            row = group.iloc[i]
            atr = row["features"].get("atr_14")
            if atr is None or atr <= 0:
                continue

            entry = row["close"]
            stop = entry - STOP_ATR_MULTIPLE * atr
            target = entry + TARGET_R_MULTIPLE * STOP_ATR_MULTIPLE * atr

            # Strictly future bars: i+1 onward, NEVER including i itself.
            future_slice = group.iloc[i + 1: i + 1 + MAX_HOLDING_DAYS]
            future_bars = [FutureBar(high=r["high"], low=r["low"]) for _, r in future_slice.iterrows()]

            label = label_trade(future_bars, entry, stop, target, MAX_HOLDING_DAYS)
            if label is None:
                continue

            feature_values = {col: row["features"].get(col) for col in FEATURE_COLUMNS}
            if any(v is None for v in feature_values.values()):
                continue  # skip rows with incomplete features (warm-up period etc.)

            records.append(
                {
                    "symbol": symbol,
                    "ts": row["ts"],
                    "entry_price": entry,
                    "stop_loss": stop,
                    "target": target,
                    "label": label,
                    **feature_values,
                }
            )

    return pd.DataFrame(records)


def run(timeframe: str = "1d") -> pd.DataFrame:
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as conn:
        logger.info("Loading joined candles+features...")
        df = load_joined_data(conn, timeframe)
        logger.info("Loaded %d rows across %d symbols", len(df), df["symbol"].nunique() if not df.empty else 0)

    dataset = build_labeled_dataset(df)
    logger.info(
        "Built labeled dataset: %d rows (win rate %.1f%%)",
        len(dataset),
        100 * dataset["label"].mean() if len(dataset) else 0.0,
    )
    return dataset


if __name__ == "__main__":
    dataset = run()
    print(dataset.head(10))
    print(f"\nTotal labeled rows: {len(dataset)}")
    if len(dataset):
        print(f"Win rate: {dataset['label'].mean():.3f}")