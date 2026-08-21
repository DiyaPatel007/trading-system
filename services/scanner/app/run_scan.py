"""
Runs the scanner against real data: loads the latest regime + latest
per-symbol features, generates setups, scores and ranks them, writes
EVERY candidate to scanner_results (not just the top N), and prints the
top N to stdout.

Run standalone (after Modules 2-4 have populated their tables):
    python -m app.run_scan --mode swing --top-n 5

Note on app.risk_engine: this module is NOT tracked in version control
under services/scanner/ -- it's copied in at Docker build time from the
single source of truth at services/risk-engine/app/risk.py (see
services/scanner/Dockerfile). This avoids maintaining two copies of the
same risk logic by hand.
"""

import argparse
import logging

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from trading_schemas import MarketRegime

from app.config import settings
from app.risk_engine import calculate_risk
from app.scoring import (
    ScoredCandidate,
    build_reasoning,
    compute_composite_score,
    compute_liquidity_score,
    compute_momentum_score,
    compute_regime_alignment_score,
    rank_opportunities,
)
from app.setup_generation import generate_swing_setup

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("scanner")


def load_latest_regime(conn: psycopg.Connection) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT ts, regime, confidence FROM market_regime ORDER BY ts DESC LIMIT 1;"
        )
        return cur.fetchone()


def load_latest_symbol_data(conn: psycopg.Connection, timeframe: str) -> list[dict]:
    """One row per symbol: its most recent candle + features, joined."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (c.symbol)
                c.symbol,
                c.ts,
                c.close,
                (f.features->>'atr_14')::double precision AS atr_14,
                (f.features->>'rsi_14')::double precision AS rsi_14,
                (f.features->>'volume_ratio')::double precision AS volume_ratio
            FROM candles c
            JOIN features f
              ON f.symbol = c.symbol AND f.timeframe = c.timeframe AND f.ts = c.ts
            WHERE c.timeframe = %s
            ORDER BY c.symbol, c.ts DESC;
            """,
            (timeframe,),
        )
        return cur.fetchall()


def build_candidates(
    symbol_rows: list[dict], regime: MarketRegime, regime_confidence: float
) -> list[ScoredCandidate]:
    candidates: list[ScoredCandidate] = []
    for row in symbol_rows:
        if row["atr_14"] is None or row["rsi_14"] is None or row["volume_ratio"] is None:
            continue
        try:
            setup = generate_swing_setup(close=row["close"], atr_14=row["atr_14"])
        except ValueError as e:
            logger.warning("Skipping %s -- could not generate setup: %s", row["symbol"], e)
            continue

        risk_assessment = calculate_risk(
            symbol=row["symbol"],
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            targets=[setup.target],
        )

        momentum_score = compute_momentum_score(row["rsi_14"])
        liquidity_score = compute_liquidity_score(row["volume_ratio"])
        regime_alignment_score = compute_regime_alignment_score(regime, regime_confidence)

        composite = compute_composite_score(
            risk_assessment, momentum_score, regime_alignment_score, liquidity_score
        )
        reasoning = build_reasoning(
            risk_assessment, momentum_score, regime, regime_alignment_score, liquidity_score
        )

        candidates.append(
            ScoredCandidate(
                symbol=row["symbol"],
                composite_score=composite,
                risk_assessment=risk_assessment,
                momentum_score=momentum_score,
                regime_alignment_score=regime_alignment_score,
                liquidity_score=liquidity_score,
                reasoning=reasoning,
            )
        )
    return candidates


def write_results(
    conn: psycopg.Connection,
    ts,
    mode: str,
    regime: MarketRegime,
    all_candidates: list[ScoredCandidate],
    ranked: list[ScoredCandidate],
) -> int:
    ranked_symbols = {c.symbol: i + 1 for i, c in enumerate(ranked)}
    rows = []
    for c in all_candidates:
        setup_entry = c.risk_assessment.entry_price
        rows.append(
            {
                "ts": ts,
                "symbol": c.symbol,
                "mode": mode,
                "rank": ranked_symbols.get(c.symbol),
                "composite_score": c.composite_score,
                "entry_price": setup_entry,
                "stop_loss": c.risk_assessment.stop_loss,
                "target": c.risk_assessment.targets[0],
                "reward_to_risk_ratio": c.risk_assessment.reward_to_risk_ratio,
                "expected_value_r": c.risk_assessment.expected_value_r,
                "risk_category": c.risk_assessment.risk_category.value,
                "approved": c.risk_assessment.approved,
                "regime": regime.value,
                "reasoning": Json(c.reasoning),
            }
        )

    if not rows:
        return 0

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO scanner_results
                (ts, symbol, mode, rank, composite_score, entry_price, stop_loss, target,
                 reward_to_risk_ratio, expected_value_r, risk_category, approved, regime, reasoning)
            VALUES
                (%(ts)s, %(symbol)s, %(mode)s, %(rank)s, %(composite_score)s, %(entry_price)s,
                 %(stop_loss)s, %(target)s, %(reward_to_risk_ratio)s, %(expected_value_r)s,
                 %(risk_category)s, %(approved)s, %(regime)s, %(reasoning)s)
            ON CONFLICT (ts, symbol, mode) DO UPDATE SET
                rank = EXCLUDED.rank,
                composite_score = EXCLUDED.composite_score,
                entry_price = EXCLUDED.entry_price,
                stop_loss = EXCLUDED.stop_loss,
                target = EXCLUDED.target,
                reward_to_risk_ratio = EXCLUDED.reward_to_risk_ratio,
                expected_value_r = EXCLUDED.expected_value_r,
                risk_category = EXCLUDED.risk_category,
                approved = EXCLUDED.approved,
                regime = EXCLUDED.regime,
                reasoning = EXCLUDED.reasoning;
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def run(mode: str, top_n: int, timeframe: str = "1d") -> None:
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as conn:
        regime_row = load_latest_regime(conn)
        if regime_row is None:
            logger.error("No regime data found -- run Module 3's compute_regime first")
            return
        regime = MarketRegime(regime_row["regime"])
        regime_confidence = regime_row["confidence"]
        logger.info(
            "Latest regime: %s (confidence %.2f) as of %s",
            regime.value, regime_confidence, regime_row["ts"],
        )

        symbol_rows = load_latest_symbol_data(conn, timeframe)
        logger.info("Loaded latest data for %d symbols", len(symbol_rows))

        candidates = build_candidates(symbol_rows, regime, regime_confidence)
        logger.info("Built %d scoreable candidates", len(candidates))

        ranked = rank_opportunities(candidates, top_n=top_n)

        latest_ts = symbol_rows[0]["ts"] if symbol_rows else regime_row["ts"]
        written = write_results(conn, latest_ts, mode, regime, candidates, ranked)
        logger.info("Wrote %d scanner_results rows (all candidates, ranked + unranked)", written)

        print(f"\nTop {len(ranked)} {mode} opportunities (regime: {regime.value}):\n")
        for i, c in enumerate(ranked, start=1):
            print(
                f"{i}. {c.symbol} -- score={c.composite_score:.3f}, "
                f"entry={c.risk_assessment.entry_price:.2f}, "
                f"stop={c.risk_assessment.stop_loss:.2f}, "
                f"target={c.risk_assessment.targets[0]:.2f}, "
                f"R:R={c.risk_assessment.reward_to_risk_ratio:.2f}, "
                f"risk={c.risk_assessment.risk_category.value}"
            )
            for reason in c.reasoning:
                print(f"     - {reason}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the opportunity scanner")
    parser.add_argument("--mode", default="swing")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--timeframe", default="1d")
    args = parser.parse_args()
    run(mode=args.mode, top_n=args.top_n, timeframe=args.timeframe)