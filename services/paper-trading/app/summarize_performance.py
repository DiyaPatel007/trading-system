"""
Prints performance metrics computed from all CLOSED paper trades so far.

Run standalone:
    python -m app.summarize_performance
"""

import psycopg
from psycopg.rows import dict_row

from app.config import settings
from app.performance import ClosedTrade, compute_performance_metrics


def run() -> None:
    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT net_pnl, status FROM paper_trades "
                "WHERE status IN ('closed_target', 'closed_stop', 'closed_time') "
                "ORDER BY closed_at ASC;"
            )
            rows = cur.fetchall()

    trades = [ClosedTrade(net_pnl=r["net_pnl"], is_win=r["net_pnl"] > 0) for r in rows]
    metrics = compute_performance_metrics(trades)

    print(f"\nPaper trading performance ({metrics.total_trades} closed trades):\n")
    print(f"  Win rate:              {metrics.win_rate:.1%}")
    print(f"  Winning trades:        {metrics.winning_trades}")
    print(f"  Losing trades:         {metrics.losing_trades}")
    print(f"  Average win:           {metrics.average_win:+.2f}")
    print(f"  Average loss:          {metrics.average_loss:+.2f}")
    print(f"  Profit factor:         {metrics.profit_factor if metrics.profit_factor else 'N/A (no losses yet)'}")
    print(f"  Expected value/trade:  {metrics.expected_value_per_trade:+.2f}")
    print(f"  Max drawdown:          {metrics.max_drawdown:.2f}")


if __name__ == "__main__":
    run()