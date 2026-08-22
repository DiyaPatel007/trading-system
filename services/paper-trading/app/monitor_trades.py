"""
Monitors OPEN paper trades against real candle data since they were
opened, closes any that have resolved (target/stop/time), and computes
realized P&L via the execution simulation.

Run standalone (run this periodically, e.g. once per day after new
candles are ingested):
    python -m app.monitor_trades
"""

import argparse
import logging

import psycopg
from psycopg.rows import dict_row

from app.config import settings
from app.execution import simulate_exit_fill, calculate_round_trip_costs
from app.exit_evaluation import FutureBar, evaluate_open_trade

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("monitor-trades")

MAX_HOLDING_DAYS = 10


def load_open_trades(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT trade_id, symbol, predicted_entry, actual_entry, stop_loss, target, "
            "quantity, opened_at FROM paper_trades WHERE status = 'open';"
        )
        return cur.fetchall()


def load_future_candles(conn: psycopg.Connection, symbol: str, opened_at, timeframe: str = "1d") -> list[FutureBar]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT ts, high, low, close FROM candles
            WHERE symbol = %s AND timeframe = %s AND ts > %s
            ORDER BY ts ASC;
            """,
            (symbol, timeframe, opened_at),
        )
        rows = cur.fetchall()
    return [FutureBar(ts=r["ts"], high=r["high"], low=r["low"], close=r["close"]) for r in rows]


def close_trade(conn: psycopg.Connection, trade: dict, exit_result, exit_signal_price: float) -> None:
    actual_exit = simulate_exit_fill(exit_signal_price)
    entry_value = trade["actual_entry"] * trade["quantity"]
    exit_value = actual_exit * trade["quantity"]
    costs = calculate_round_trip_costs(entry_value, exit_value)
    gross_pnl = (actual_exit - trade["actual_entry"]) * trade["quantity"]
    net_pnl = gross_pnl - costs

    status_map = {"target": "closed_target", "stop": "closed_stop", "time": "closed_time"}

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE paper_trades SET
                status = %(status)s,
                closed_at = %(closed_at)s,
                exit_signal_price = %(exit_signal_price)s,
                actual_exit_price = %(actual_exit_price)s,
                gross_pnl = %(gross_pnl)s,
                total_costs = %(total_costs)s,
                net_pnl = %(net_pnl)s,
                max_favorable_excursion = %(mfe)s,
                max_adverse_excursion = %(mae)s
            WHERE trade_id = %(trade_id)s;
            """,
            {
                "status": status_map[exit_result.exit_reason],
                "closed_at": exit_result.exit_ts,
                "exit_signal_price": exit_signal_price,
                "actual_exit_price": round(actual_exit, 4),
                "gross_pnl": round(gross_pnl, 2),
                "total_costs": round(costs, 2),
                "net_pnl": round(net_pnl, 2),
                "mfe": round(exit_result.max_favorable_excursion, 4),
                "mae": round(exit_result.max_adverse_excursion, 4),
                "trade_id": trade["trade_id"],
            },
        )
    conn.commit()


def run(timeframe: str = "1d") -> None:
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as conn:
        open_trades = load_open_trades(conn)
        logger.info("Checking %d open trades", len(open_trades))

        closed_count = 0
        for trade in open_trades:
            future_bars = load_future_candles(conn, trade["symbol"], trade["opened_at"], timeframe)
            result = evaluate_open_trade(
                future_bars, trade["actual_entry"], trade["stop_loss"], trade["target"],
                max_holding_days=MAX_HOLDING_DAYS,
            )

            if result.exit_reason == "still_open":
                logger.info("%s: still open (not enough new candle data yet)", trade["symbol"])
                continue

            close_trade(conn, trade, result, result.exit_price)
            closed_count += 1
            logger.info(
                "Closed %s: reason=%s exit_price=%.2f", trade["symbol"], result.exit_reason, result.exit_price
            )

    logger.info("Closed %d of %d open trades this run", closed_count, len(open_trades))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor and close resolved open paper trades")
    parser.add_argument("--timeframe", default="1d")
    args = parser.parse_args()
    run(timeframe=args.timeframe)