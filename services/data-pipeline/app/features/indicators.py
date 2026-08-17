"""
Computes technical indicators from raw OHLCV candles.

This module is pure computation -- given a DataFrame of candles for ONE
symbol, sorted by time, it returns a DataFrame of indicator columns. No
database or network access here, which makes it trivially unit-testable
with synthetic data (see tests/test_indicators.py) and reusable both by
the batch feature pipeline (this module) and, later, by the live
incremental feature calculator in the Market Data Service.

FEATURE_SET_VERSION must be bumped any time a feature is added, removed,
or its calculation changes -- this is what lets later backtests pin
themselves to an exact, reproducible feature definition.
"""

import pandas as pd
import pandas_ta as ta

FEATURE_SET_VERSION = "v1"


def compute_indicators(candles_df: pd.DataFrame) -> pd.DataFrame:
    """
    candles_df must have columns: timestamp, open, high, low, close, volume,
    sorted ascending by timestamp, for a single symbol/timeframe.

    Returns a DataFrame indexed the same way, with one column per feature.
    Early rows that don't yet have enough history for a given indicator
    (e.g. first 19 rows for a 20-period EMA) will have NaN for that
    feature -- callers should decide whether to drop or keep those rows.
    """
    df = candles_df.copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    out = pd.DataFrame(index=df.index)
    out["timestamp"] = df["timestamp"]

    # --- Trend ---
    out["ema_20"] = ta.ema(df["close"], length=20)
    out["ema_50"] = ta.ema(df["close"], length=50)
    out["sma_200"] = ta.sma(df["close"], length=200)

    # --- Momentum ---
    out["rsi_14"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None:
        out["macd"] = macd["MACD_12_26_9"]
        out["macd_signal"] = macd["MACDs_12_26_9"]
        out["macd_hist"] = macd["MACDh_12_26_9"]

    # --- Volatility ---
    out["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)

    # --- Volume ---
    out["volume_sma_20"] = ta.sma(df["volume"], length=20)
    out["volume_ratio"] = df["volume"] / out["volume_sma_20"]

    # --- Price-derived ---
    out["daily_return_pct"] = df["close"].pct_change() * 100
    out["distance_from_ema20_pct"] = (df["close"] - out["ema_20"]) / out["ema_20"] * 100

    return out


def indicators_to_feature_rows(
    symbol: str, timeframe: str, indicators_df: pd.DataFrame
) -> list[dict]:
    """
    Converts the wide indicators DataFrame into the row shape the
    `features` table expects: one row per timestamp, indicators packed
    into a single JSONB dict. Rows where EVERY indicator is still NaN
    (i.e. pure warm-up period, not enough history yet) are dropped --
    a fully-empty feature row would be misleading, not useful.
    """
    feature_cols = [c for c in indicators_df.columns if c != "timestamp"]
    rows = []
    for _, row in indicators_df.iterrows():
        feature_values = {
            col: (None if pd.isna(row[col]) else float(row[col])) for col in feature_cols
        }
        if all(v is None for v in feature_values.values()):
            continue
        rows.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "ts": row["timestamp"],
                "feature_set_version": FEATURE_SET_VERSION,
                "features": feature_values,
            }
        )
    return rows
