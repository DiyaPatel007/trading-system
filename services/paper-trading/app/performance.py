"""
Performance metrics for closed paper trades -- pure computation, no I/O.

Matches the metrics named in the problem statement's "Performance and
Trade Journal" section: win rate, average win/loss, profit factor,
maximum drawdown, expected value.
"""

from dataclasses import dataclass


@dataclass
class ClosedTrade:
    net_pnl: float
    is_win: bool


@dataclass
class PerformanceMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    average_win: float
    average_loss: float
    profit_factor: float | None
    expected_value_per_trade: float
    max_drawdown: float


def compute_performance_metrics(trades: list[ClosedTrade]) -> PerformanceMetrics:
    if not trades:
        return PerformanceMetrics(
            total_trades=0, winning_trades=0, losing_trades=0, win_rate=0.0,
            average_win=0.0, average_loss=0.0, profit_factor=None,
            expected_value_per_trade=0.0, max_drawdown=0.0,
        )

    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]

    total = len(trades)
    win_rate = len(wins) / total

    average_win = sum(t.net_pnl for t in wins) / len(wins) if wins else 0.0
    average_loss = sum(t.net_pnl for t in losses) / len(losses) if losses else 0.0

    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    expected_value = sum(t.net_pnl for t in trades) / total

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        cumulative += t.net_pnl
        peak = max(peak, cumulative)
        drawdown = cumulative - peak
        max_dd = min(max_dd, drawdown)

    return PerformanceMetrics(
        total_trades=total,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=round(win_rate, 4),
        average_win=round(average_win, 2),
        average_loss=round(average_loss, 2),
        profit_factor=round(profit_factor, 4) if profit_factor is not None else None,
        expected_value_per_trade=round(expected_value, 2),
        max_drawdown=round(max_dd, 2),
    )