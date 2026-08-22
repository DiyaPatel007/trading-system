"""
Opens paper trades from the latest Module 5 scanner_results ranked
signals. Every top-N ranked signal becomes a paper trade automatically
-- this is a personal validation system, so "paper trading" here means
continuous automatic simulation, not waiting for manual confirmation.

Idempotent: won't open a duplicate trade for a (symbol, scanner_ts)
pair that's already been opened.

Run standalone:
    python -m app.open_trades --mode swing

Note on app.risk_engine: copied in at Docker build time from
services/risk-engine/app/risk.py, same pattern as the Scanner service
(Module 5) -- see the note at the top of that service's run_scan.py.
"""

import argparse
import logging
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from app.config import settings
from app.execution import simulate_entry_fill
from app.risk_engine import size_position

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("open-trades")


def load_unopened_ranked_signals(conn: psycopg.Connection, mode: str) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT sr.ts, sr.symbol, sr.mode, sr.rank, sr.entry_price, sr.stop_loss,
                   sr.target, sr.risk_category, sr.reasoning
            FROM scanner_results sr
            WHERE sr.mode = %s
              AND sr.rank IS NOT NULL
              AND sr.ts = (SELECT MAX(ts) FROM scanner_results WHERE mode = %s)
              AND NOT EXISTS (
                  SELECT 1 FROM paper_trades pt
                  WHERE pt.symbol = sr.symbol AND pt.scanner_ts = sr.ts AND pt.mode = sr.mode
              )
            ORDER BY sr.rank;
            """,
            (mode, mode),
        )
        return cur.fetchall()


def load_open_portfolio_value(conn: psycopg.Connection) -> float:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT COALESCE(SUM(actual_entry * quantity), 0) AS total FROM paper_trades WHERE status = 'open';"
        )
        return cur.fetchone()["total"]


def open_trades(conn: psycopg.Connection, mode: str) -> int:
    signals = load_unopened_ranked_signals(conn, mode)
    if not signals:
        logger.info("No new ranked signals to open for mode=%s", mode)
        return 0

    existing_portfolio_value = load_open_portfolio_value(conn)
    opened_count = 0
    now = datetime.now(timezone.utc)

    for sig in signals:
        position = size_position(
            symbol=sig["symbol"],
            capital=settings.default_capital,
            max_risk_pct_per_trade=settings.max_risk_pct_per_trade,
            entry_price=sig["entry_price"],
            stop_loss=sig["stop_loss"],
            existing_portfolio_value=existing_portfolio_value,
        )
        if not position.within_portfolio_constraints or position.quantity <= 0:
            logger.warning(
                "Skipping %s -- position sizing failed constraints: %s",
                sig["symbol"], position.constraint_violations,
            )
            continue

        actual_entry = simulate_entry_fill(sig["entry_price"])
        trade_id = f"{sig['symbol']}-{uuid.uuid4().hex[:8]}"

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO paper_trades
                    (trade_id, symbol, mode, scanner_ts, status, predicted_entry, actual_entry,
                     stop_loss, target, quantity, opened_at, risk_category, reasoning)
                VALUES
                    (%(trade_id)s, %(symbol)s, %(mode)s, %(scanner_ts)s, 'open', %(predicted_entry)s,
                     %(actual_entry)s, %(stop_loss)s, %(target)s, %(quantity)s, %(opened_at)s,
                     %(risk_category)s, %(reasoning)s);
                """,
                {
                    "trade_id": trade_id,
                    "symbol": sig["symbol"],
                    "mode": mode,
                    "scanner_ts": sig["ts"],
                    "predicted_entry": sig["entry_price"],
                    "actual_entry": round(actual_entry, 4),
                    "stop_loss": sig["stop_loss"],
                    "target": sig["target"],
                    "quantity": position.quantity,
                    "opened_at": now,
                    "risk_category": sig["risk_category"],
                    "reasoning": Json(sig["reasoning"]),
                },
            )
        conn.commit()
        existing_portfolio_value += position.capital_deployed
        opened_count += 1
        logger.info(
            "Opened %s: qty=%d @ actual_entry=%.2f (signal was %.2f)",
            sig["symbol"], position.quantity, actual_entry, sig["entry_price"],
        )

    return opened_count


def run(mode: str) -> None:
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as conn:
        count = open_trades(conn, mode)
    logger.info("Opened %d new paper trades for mode=%s", count, mode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open paper trades from ranked scanner signals")
    parser.add_argument("--mode", default="swing")
    args = parser.parse_args()
    run(mode=args.mode)