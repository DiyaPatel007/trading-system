"""
Exit evaluation for open paper trades -- pure computation, no I/O.

Distinct from Module 6's labeling.py (which produces a single win/loss
label for training) -- this module needs to know WHEN and AT WHAT PRICE
a trade would have closed, since paper trading needs real P&L, not a
binary outcome. Same no-lookahead discipline applies: the caller must
only pass bars strictly AFTER the trade was opened.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class FutureBar:
    ts: datetime
    high: float
    low: float
    close: float


@dataclass
class ExitResult:
    exit_reason: str
    exit_ts: datetime | None
    exit_price: float | None
    max_favorable_excursion: float
    max_adverse_excursion: float


def evaluate_open_trade(
    future_bars: list[FutureBar],
    entry_price: float,
    stop_loss: float,
    target: float,
    max_holding_days: int,
) -> ExitResult:
    if stop_loss >= entry_price:
        raise ValueError("stop_loss must be below entry_price (long-only)")
    if target <= entry_price:
        raise ValueError("target must be above entry_price (long-only)")
    if max_holding_days <= 0:
        raise ValueError("max_holding_days must be positive")

    mfe = 0.0
    mae = 0.0

    bars_in_window = future_bars[:max_holding_days]

    for bar in bars_in_window:
        mfe = max(mfe, bar.high - entry_price)
        mae = max(mae, entry_price - bar.low)

        stop_hit = bar.low <= stop_loss
        target_hit = bar.high >= target

        if stop_hit and target_hit:
            return ExitResult("stop", bar.ts, stop_loss, mfe, mae)
        if stop_hit:
            return ExitResult("stop", bar.ts, stop_loss, mfe, mae)
        if target_hit:
            return ExitResult("target", bar.ts, target, mfe, mae)

    if len(bars_in_window) < max_holding_days:
        return ExitResult("still_open", None, None, mfe, mae)

    last_bar = bars_in_window[-1]
    return ExitResult("time", last_bar.ts, last_bar.close, mfe, mae)