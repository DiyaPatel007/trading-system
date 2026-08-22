"""
MCP server exposing the trading system's existing services as tools an
LLM can call. Every tool is a THIN ADAPTER -- it validates input, then
either runs a direct read-only query against a table Modules 2-7
already populate, or calls the risk engine's exact same calculation
logic. No tool re-implements or approximates any calculation; the LLM
never does the numerical work itself, per the original architecture
principle.

Run standalone (stdio transport, for Claude Desktop/Code):
    python -m app.server
"""

import logging
from datetime import datetime, timezone

import psycopg
from mcp.server.fastmcp import FastMCP
from psycopg.rows import dict_row

from app.config import settings
from app.risk_engine import calculate_risk as _calculate_risk
from app.risk_engine import size_position as _size_position

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcp-server")

mcp = FastMCP("trading-system")


def _connect() -> psycopg.Connection:
    return psycopg.connect(settings.postgres_dsn, row_factory=dict_row)


@mcp.tool()
def get_market_regime() -> dict:
    """
    Returns the most recently computed market regime (bullish, bearish,
    sideways, high_volatility, low_volatility, or transitional), along
    with its confidence and the underlying trend/volatility/breadth
    numbers that produced it. Always check this before interpreting any
    individual stock signal -- per the system's design, the same setup
    can mean different things in different regimes.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT ts, regime, confidence, trend_score, volatility_score, "
            "breadth_pct_above_ema20, contributing_factors "
            "FROM market_regime ORDER BY ts DESC LIMIT 1;"
        )
        row = cur.fetchone()
    if row is None:
        return {"error": "No regime data available -- has Module 3's compute_regime been run?"}
    row["ts"] = row["ts"].isoformat()
    return row


@mcp.tool()
def get_scanner_results(mode: str = "swing", top_n: int = 5) -> dict:
    """
    Returns the latest ranked trading opportunities for the given mode
    (swing, intraday, or long_term), as computed by Module 5's scanner.
    Only returns candidates that PASSED the risk engine's approval gate
    -- rejected candidates never appear in the ranked list, by design.
    Does NOT run a new scan; reads the most recent one already computed.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, rank, composite_score, entry_price, stop_loss, target,
                   reward_to_risk_ratio, expected_value_r, risk_category, regime, reasoning, ts
            FROM scanner_results
            WHERE mode = %s AND rank IS NOT NULL
              AND ts = (SELECT MAX(ts) FROM scanner_results WHERE mode = %s)
            ORDER BY rank LIMIT %s;
            """,
            (mode, mode, top_n),
        )
        rows = cur.fetchall()
    for r in rows:
        r["ts"] = r["ts"].isoformat()
    if not rows:
        return {"error": f"No scanner results for mode={mode} -- has Module 5's run_scan been run?"}
    return {"mode": mode, "opportunities": rows}


@mcp.tool()
def calculate_risk(
    symbol: str, entry_price: float, stop_loss: float, target: float, win_probability: float = 0.5
) -> dict:
    """
    Runs the SAME deterministic risk calculation the Scanner uses, for
    an arbitrary hypothetical trade -- useful for "what if I used a
    tighter stop on X" questions. Returns risk category, reward:risk,
    expected value, and whether the trade would be approved. This tool
    performs the calculation itself (via the shared risk engine module,
    not a re-implementation) -- the LLM must never compute these numbers
    itself; always call this tool instead.
    """
    result = _calculate_risk(
        symbol=symbol, entry_price=entry_price, stop_loss=stop_loss,
        targets=[target], win_probability=win_probability,
    )
    return {
        "symbol": result.symbol,
        "risk_per_share": result.risk_per_share,
        "reward_to_risk_ratio": result.reward_to_risk_ratio,
        "expected_value_r": result.expected_value_r,
        "risk_category": result.risk_category.value,
        "approved": result.approved,
        "rejection_reasons": result.rejection_reasons,
    }


@mcp.tool()
def size_position(
    symbol: str, capital: float, entry_price: float, stop_loss: float,
    max_risk_pct_per_trade: float = 0.5, existing_portfolio_value: float = 0.0,
) -> dict:
    """
    Calculates position size given capital and risk rules, using the
    same deterministic sizing logic as the rest of the system. Returns
    quantity, capital deployed, and whether portfolio constraints are
    satisfied.
    """
    result = _size_position(
        symbol=symbol, capital=capital, max_risk_pct_per_trade=max_risk_pct_per_trade,
        entry_price=entry_price, stop_loss=stop_loss, existing_portfolio_value=existing_portfolio_value,
    )
    return {
        "quantity": result.quantity,
        "capital_deployed": result.capital_deployed,
        "portfolio_exposure_after_pct": result.portfolio_exposure_after_pct,
        "within_portfolio_constraints": result.within_portfolio_constraints,
        "constraint_violations": result.constraint_violations,
    }


@mcp.tool()
def get_open_paper_trades() -> dict:
    """Returns all currently open (not yet resolved) paper trades."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT trade_id, symbol, mode, predicted_entry, actual_entry, "
            "stop_loss, target, quantity, opened_at FROM paper_trades "
            "WHERE status = 'open' ORDER BY opened_at DESC;"
        )
        rows = cur.fetchall()
    for r in rows:
        r["opened_at"] = r["opened_at"].isoformat()
    return {"open_trades": rows}


@mcp.tool()
def get_paper_trading_performance() -> dict:
    """
    Returns aggregate performance metrics (win rate, profit factor,
    expected value, max drawdown) computed from all CLOSED paper trades
    so far, using the exact same calculation as Module 7's
    summarize_performance script.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT net_pnl FROM paper_trades "
            "WHERE status IN ('closed_target', 'closed_stop', 'closed_time');"
        )
        rows = cur.fetchall()

    if not rows:
        return {"total_trades": 0, "message": "No closed paper trades yet."}

    pnls = [r["net_pnl"] for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    return {
        "total_trades": len(pnls),
        "win_rate": round(len(wins) / len(pnls), 4),
        "average_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "average_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else None,
        "expected_value_per_trade": round(sum(pnls) / len(pnls), 2),
    }


@mcp.tool()
def get_model_registry(mode: str = "swing") -> dict:
    """
    Returns recently trained models for the given mode, with their
    walk-forward test metrics (accuracy, AUC, Brier score, win rate) and
    promotion stage (experimental/candidate/production). Use this to
    check whether a model has shown any real, validated edge before
    trusting its predictions.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT model_id, trained_at, n_training_rows, n_test_rows, "
            "train_win_rate, test_win_rate, test_accuracy, test_auc, "
            "test_brier_score, stage FROM models WHERE mode = %s "
            "ORDER BY trained_at DESC LIMIT 5;",
            (mode,),
        )
        rows = cur.fetchall()
    for r in rows:
        r["trained_at"] = r["trained_at"].isoformat()
    return {"mode": mode, "models": rows}


@mcp.tool()
def get_recent_candles(symbol: str, limit: int = 30, timeframe: str = "1d") -> dict:
    """Returns the most recent OHLCV candles for a symbol, most recent last."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT ts, open, high, low, close, volume FROM candles "
            "WHERE symbol = %s AND timeframe = %s ORDER BY ts DESC LIMIT %s;",
            (symbol, timeframe, limit),
        )
        rows = cur.fetchall()
    rows.reverse()
    for r in rows:
        r["ts"] = r["ts"].isoformat()
    if not rows:
        return {"error": f"No candle data for {symbol} -- check the symbol is in the universe and Module 2 has run"}
    return {"symbol": symbol, "candles": rows}


if __name__ == "__main__":
    mcp.run()