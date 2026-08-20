"""
Reads candles+features from Postgres, aggregates across the whole
universe per trading day, computes the market regime for each day via
the pure logic in regime.py, and writes results to `market_regime`.

Run standalone (after Module 2's ingestion + features have been run):
    python -m app.compute_regime --timeframe 1d
"""

import argparse
import logging

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import settings
from app.regime import compute_regime

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("regime-engine")

# How many trailing days to use as the "normal" volatility baseline for
# each symbol's ATR. Shifted by 1 day (see below) so today's regime
# calculation never uses today's own ATR as part of its own baseline --
# consistent with the no-lookahead-bias standard set in Module 2.
VOLATILITY_BASELINE_WINDOW = 60
MIN_PERIODS_FOR_BASELINE = 20


def load_joined_data(conn: psycopg.Connection, timeframe: str) -> pd.DataFrame:
    """
    Joins candles (for close price) with features (for ema_20, ema_50,
    atr_14) on symbol/timeframe/timestamp. Only the latest feature_set_version
    per row is used implicitly, since compute_features.py only ever writes
    the current FEATURE_SET_VERSION -- if you later keep multiple versions
    around, this query will need a version filter.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                c.symbol,
                c.ts,
                c.close,
                (f.features->>'ema_20')::double precision AS ema_20,
                (f.features->>'ema_50')::double precision AS ema_50,
                (f.features->>'atr_14')::double precision AS atr_14
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


def compute_daily_regime_inputs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given the joined symbol/date-level data, computes per-symbol,
    per-date: trend contribution, ATR-vs-baseline ratio, and above/below
    EMA20 flag -- then aggregates across the universe for each date.

    Returns a DataFrame indexed by date with columns:
    trend_score, volatility_score, breadth_pct_above_ema20
    """
    df = df.copy().sort_values(["symbol", "ts"])

    # Per-symbol trailing ATR baseline, shifted by 1 day to avoid using
    # today's own ATR in its own "normal" baseline.
    df["atr_baseline"] = (
        df.groupby("symbol")["atr_14"]
        .transform(lambda s: s.shift(1).rolling(VOLATILITY_BASELINE_WINDOW, min_periods=MIN_PERIODS_FOR_BASELINE).mean())
    )

    df["trend_contribution"] = (df["close"] - df["ema_50"]) / df["ema_50"]
    df["volatility_ratio"] = df["atr_14"] / df["atr_baseline"]
    df["above_ema20"] = (df["close"] > df["ema_20"]).astype(float)

    # Only rows with enough history for all three inputs are usable for
    # that day's aggregate -- warm-up rows are dropped per-symbol, not
    # per-date, so early dates simply have a smaller (but still valid)
    # universe sample.
    usable = df.dropna(subset=["trend_contribution", "volatility_ratio", "above_ema20"])

    daily = usable.groupby("ts").agg(
        trend_score=("trend_contribution", "mean"),
        volatility_score=("volatility_ratio", "mean"),
        breadth_pct_above_ema20=("above_ema20", lambda s: s.mean() * 100),
        n_symbols=("symbol", "count"),
    )
    return daily


def write_regime_rows(conn: psycopg.Connection, daily: pd.DataFrame) -> int:
    rows = []
    for ts, row in daily.iterrows():
        result = compute_regime(
            trend_score=row["trend_score"],
            volatility_score=row["volatility_score"],
            breadth_pct_above_ema20=row["breadth_pct_above_ema20"],
        )
        rows.append(
            {
                "ts": ts,
                "regime": result.regime.value,
                "confidence": result.confidence,
                "trend_score": result.trend_score,
                "volatility_score": result.volatility_score,
                "breadth_pct_above_ema20": result.breadth_pct_above_ema20,
                "contributing_factors": Json(result.contributing_factors),
            }
        )

    if not rows:
        return 0

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO market_regime
                (ts, regime, confidence, trend_score, volatility_score, breadth_pct_above_ema20, contributing_factors)
            VALUES
                (%(ts)s, %(regime)s, %(confidence)s, %(trend_score)s, %(volatility_score)s, %(breadth_pct_above_ema20)s, %(contributing_factors)s)
            ON CONFLICT (ts) DO UPDATE SET
                regime = EXCLUDED.regime,
                confidence = EXCLUDED.confidence,
                trend_score = EXCLUDED.trend_score,
                volatility_score = EXCLUDED.volatility_score,
                breadth_pct_above_ema20 = EXCLUDED.breadth_pct_above_ema20,
                contributing_factors = EXCLUDED.contributing_factors;
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def run(timeframe: str) -> None:
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as conn:
        logger.info("Loading joined candles+features for timeframe=%s ...", timeframe)
        df = load_joined_data(conn, timeframe)
        if df.empty:
            logger.error("No data found -- run Module 2's ingestion and feature computation first")
            return
        logger.info("Loaded %d rows across %d symbols", len(df), df["symbol"].nunique())

        daily = compute_daily_regime_inputs(df)
        logger.info("Computed regime inputs for %d trading days", len(daily))

        written = write_regime_rows(conn, daily)
        logger.info("Done. Wrote %d regime rows", written)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute market regime from candles+features")
    parser.add_argument("--timeframe", default="1d")
    args = parser.parse_args()
    run(timeframe=args.timeframe)