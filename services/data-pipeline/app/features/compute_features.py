"""
Reads raw candles from Postgres, computes indicators, writes to the
`features` table. Run this AFTER fetch_historical.py has populated
`candles`.

Run standalone:
    python -m app.features.compute_features --timeframe 1d
"""

import argparse
import logging

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from app.config import settings
from app.features.indicators import compute_indicators, indicators_to_feature_rows
from app.universe import NIFTY_50

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("features")


def load_candles(conn: psycopg.Connection, symbol: str, timeframe: str) -> pd.DataFrame:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT ts AS timestamp, open, high, low, close, volume
            FROM candles
            WHERE symbol = %s AND timeframe = %s
            ORDER BY ts ASC;
            """,
            (symbol, timeframe),
        )
        rows = cur.fetchall()
    return pd.DataFrame(rows)


def write_features(conn: psycopg.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO features (symbol, timeframe, ts, feature_set_version, features)
            VALUES (%(symbol)s, %(timeframe)s, %(ts)s, %(feature_set_version)s, %(features)s)
            ON CONFLICT (symbol, timeframe, ts, feature_set_version) DO UPDATE SET
                features = EXCLUDED.features;
            """,
            [
                {**r, "features": psycopg.types.json.Json(r["features"])}
                for r in rows
            ],
        )
    conn.commit()
    return len(rows)


def run(timeframe: str, symbols: list[str] | None = None) -> None:
    symbols = symbols or NIFTY_50
    total_written = 0

    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as conn:
        for i, symbol in enumerate(symbols, start=1):
            candles_df = load_candles(conn, symbol, timeframe)
            if candles_df.empty:
                logger.warning("[%d/%d] No candles for %s -- run ingestion first", i, len(symbols), symbol)
                continue

            indicators_df = compute_indicators(candles_df)
            rows = indicators_to_feature_rows(symbol, timeframe, indicators_df)
            written = write_features(conn, rows)
            total_written += written
            logger.info("[%d/%d] %s -> %d feature rows written", i, len(symbols), symbol, written)

    logger.info("Done. Total feature rows written: %d", total_written)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute indicators from stored candles")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--symbols", nargs="*", default=None)
    args = parser.parse_args()

    run(timeframe=args.timeframe, symbols=args.symbols)
