"""
Fetches historical daily OHLCV for the trading universe via yfinance
and writes it into the `candles` hypertable.

Every row is validated through our shared Candle schema before being
written -- if yfinance ever returns a malformed bar (has happened with
some providers around corporate actions), we reject it loudly instead
of silently corrupting the training data.

IMPORTANT -- Yahoo Finance rate limiting: Yahoo aggressively blocks/
rate-limits (HTTP 429) requests that look automated. As of yfinance
1.6.0 this is mitigated by (a) impersonating a real browser's TLS
fingerprint via curl_cffi, which yfinance now uses internally, and
(b) us self-throttling with a delay between symbols and retrying with
exponential backoff on failure. Even with this, occasional failures for
a handful of symbols are normal -- the script logs and continues rather
than aborting the whole run.

Run standalone:
    python -m app.ingestion.fetch_historical --period 5y --timeframe 1d

Idempotent: uses an upsert (ON CONFLICT DO UPDATE), so re-running for
an overlapping date range, or re-running to pick up symbols that failed
last time, is always safe.
"""

import argparse
import logging
import random
import sys
import time

import pandas as pd
import psycopg
import yfinance as yf
from curl_cffi import requests as curl_requests
from psycopg.rows import dict_row
from pydantic import ValidationError
from trading_schemas import Candle, DataFreshness

from app.config import settings
from app.universe import NIFTY_50

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("ingestion")

# Impersonate a real Chrome browser's TLS/HTTP fingerprint -- this is
# the current, actively-maintained way to avoid Yahoo's bot detection.
# Session is created once and reused across all requests in this run.
_SESSION = curl_requests.Session(impersonate="chrome")

MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 5
DELAY_BETWEEN_SYMBOLS_SECONDS = 1.5  # self-imposed rate limit


def fetch_symbol(symbol: str, period: str, interval: str) -> list[Candle]:
    """Fetch and validate OHLCV for one symbol, with retry/backoff on failure."""
    df = None
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = yf.download(
                symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
                session=_SESSION,
            )
            if df is not None and not df.empty:
                break
            last_error = RuntimeError("empty response")
        except Exception as e:  # noqa: BLE001 -- Yahoo can raise several error types
            last_error = e

        if attempt < MAX_RETRIES:
            backoff = BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 1)
            logger.warning(
                "  attempt %d/%d failed for %s (%s) -- retrying in %.1fs",
                attempt, MAX_RETRIES, symbol, last_error, backoff,
            )
            time.sleep(backoff)

    if df is None or df.empty:
        logger.error("All %d attempts failed for %s: %s", MAX_RETRIES, symbol, last_error)
        return []

    # yfinance can return a MultiIndex column frame even for a single
    # symbol; flatten it defensively.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    candles: list[Candle] = []
    for ts, row in df.iterrows():
        try:
            candle = Candle(
                symbol=symbol,
                timeframe=interval,
                timestamp=ts.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]),
                freshness=DataFreshness.HISTORICAL,
            )
            candles.append(candle)
        except (ValidationError, ValueError, TypeError) as e:
            # A single malformed bar (e.g. corporate-action artifact)
            # should not kill the whole run -- log and skip it.
            logger.warning("Rejected bad bar for %s at %s: %s", symbol, ts, e)
            continue

    return candles


def write_candles(conn: psycopg.Connection, candles: list[Candle]) -> int:
    if not candles:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume, freshness)
            VALUES (%(symbol)s, %(timeframe)s, %(ts)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(freshness)s)
            ON CONFLICT (symbol, timeframe, ts) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                freshness = EXCLUDED.freshness;
            """,
            [
                {
                    "symbol": c.symbol,
                    "timeframe": c.timeframe,
                    "ts": c.timestamp,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "freshness": c.freshness.value,
                }
                for c in candles
            ],
        )
    conn.commit()
    return len(candles)


def run(period: str, interval: str, symbols: list[str] | None = None) -> None:
    symbols = symbols or NIFTY_50
    total_written = 0
    failures: list[str] = []

    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as conn:
        for i, symbol in enumerate(symbols, start=1):
            logger.info("[%d/%d] Fetching %s (%s, %s)", i, len(symbols), symbol, period, interval)
            try:
                candles = fetch_symbol(symbol, period, interval)
                written = write_candles(conn, candles)
                total_written += written
                logger.info("  -> wrote %d candles for %s", written, symbol)
            except Exception as e:  # noqa: BLE001
                logger.error("  -> FAILED for %s: %s", symbol, e)
                failures.append(symbol)

            if i < len(symbols):
                time.sleep(DELAY_BETWEEN_SYMBOLS_SECONDS)

    logger.info("Done. Total candles written: %d", total_written)
    if failures:
        logger.warning("Symbols that failed entirely: %s", failures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest historical OHLCV into Postgres")
    parser.add_argument("--period", default="5y", help="yfinance period, e.g. 5y, 1y, max")
    parser.add_argument("--interval", default="1d", help="yfinance interval, e.g. 1d, 1h")
    parser.add_argument(
        "--symbols", nargs="*", default=None, help="Optional subset of symbols to fetch"
    )
    args = parser.parse_args()

    run(period=args.period, interval=args.interval, symbols=args.symbols)
    sys.exit(0)