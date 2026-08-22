"""
Runs the Trade Guardian against every currently OPEN paper trade: pulls
the trade's original context (entry, stop, risk category, and the
regime that was active when it was opened, via a join back to
scanner_results), compares it to the latest available price/regime/RSI,
and writes an alert row -- never modifying paper_trades itself.

Run standalone (run this periodically, e.g. after each day's
ingestion+regime+scan cycle):
    python -m app.monitor_open_trades
"""

import argparse
import logging

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from trading_schemas import MarketRegime, RiskCategory

from app.config import settings
from app.guardian import evaluate_open_trade

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("trade-guardian")


def load_open_trades_with_context(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT pt.trade_id, pt.symbol, pt.actual_entry, pt.stop_loss, pt.risk_category,
                   sr.regime AS regime_at_open
            FROM paper_trades pt
            JOIN scanner_results sr
              ON sr.symbol = pt.symbol AND sr.ts = pt.scanner_ts AND sr.mode = pt.mode
            WHERE pt.status = 'open';
            """
        )
        return cur.fetchall()


def load_latest_regime(conn: psycopg.Connection) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT regime, confidence FROM market_regime ORDER BY ts DESC LIMIT 1;")
        return cur.fetchone()


def load_latest_symbol_snapshot(conn: psycopg.Connection, symbol: str, timeframe: str = "1d") -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT c.close, (f.features->>'rsi_14')::double precision AS rsi_14
            FROM candles c
            JOIN features f ON f.symbol = c.symbol AND f.timeframe = c.timeframe AND f.ts = c.ts
            WHERE c.symbol = %s AND c.timeframe = %s
            ORDER BY c.ts DESC LIMIT 1;
            """,
            (symbol, timeframe),
        )
        return cur.fetchone()


def write_alert(conn: psycopg.Connection, trade_id: str, current_price: float, original_category: str, assessment) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trade_guardian_alerts
                (trade_id, current_price, alert_level, original_risk_category,
                 updated_risk_category, adverse_excursion_pct, alerts)
            VALUES
                (%(trade_id)s, %(current_price)s, %(alert_level)s, %(original_category)s,
                 %(updated_category)s, %(adverse_pct)s, %(alerts)s);
            """,
            {
                "trade_id": trade_id,
                "current_price": current_price,
                "alert_level": assessment.alert_level.value,
                "original_category": original_category,
                "updated_category": assessment.updated_risk_category.value,
                "adverse_pct": assessment.adverse_excursion_pct,
                "alerts": Json(assessment.alerts),
            },
        )
    conn.commit()


def run(timeframe: str = "1d") -> None:
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as conn:
        trades = load_open_trades_with_context(conn)
        if not trades:
            logger.info("No open trades to check")
            return

        regime_row = load_latest_regime(conn)
        if regime_row is None:
            logger.error("No regime data available -- run Module 3 first")
            return
        regime_now = MarketRegime(regime_row["regime"])
        regime_confidence_now = regime_row["confidence"]

        logger.info("Checking %d open trades against regime=%s", len(trades), regime_now.value)

        for trade in trades:
            snapshot = load_latest_symbol_snapshot(conn, trade["symbol"], timeframe)
            if snapshot is None:
                logger.warning("No recent candle/feature data for %s -- skipping", trade["symbol"])
                continue

            assessment = evaluate_open_trade(
                entry_price=trade["actual_entry"],
                stop_loss=trade["stop_loss"],
                current_price=snapshot["close"],
                original_risk_category=RiskCategory(trade["risk_category"]),
                regime_at_open=MarketRegime(trade["regime_at_open"]),
                regime_now=regime_now,
                regime_confidence_now=regime_confidence_now,
                rsi_now=snapshot["rsi_14"],
            )

            write_alert(conn, trade["trade_id"], snapshot["close"], trade["risk_category"], assessment)

            logger.info(
                "%s [%s]: %s",
                trade["symbol"], assessment.alert_level.value.upper(), "; ".join(assessment.alerts),
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Trade Guardian checks on open paper trades")
    parser.add_argument("--timeframe", default="1d")
    args = parser.parse_args()
    run(timeframe=args.timeframe)