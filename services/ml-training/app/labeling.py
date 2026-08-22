"""
Trade outcome labeling -- pure computation, no I/O.

Given entry/stop/target and a sequence of STRICTLY FUTURE daily bars
(never including the signal day itself), determines whether the target
was reached before the stop within a fixed holding window. This is the
"explicit labels... whether the target was reached before the stop"
mechanism from the problem statement's Historical Training Dataset
section.

LEAKAGE DISCIPLINE: this function only ever looks at bars the caller
passes in. It is the CALLER's responsibility (see dataset.py) to ensure
those bars are strictly after the signal date -- this function has no
way to enforce that itself, so dataset.py's slicing logic is exactly as
important to get right as this file.
"""

from dataclasses import dataclass


@dataclass
class FutureBar:
    high: float
    low: float


def label_trade(
    future_bars: list[FutureBar],
    entry_price: float,
    stop_loss: float,
    target: float,
    max_holding_days: int,
) -> int | None:
    """
    Returns:
        1 if target was reached before stop, within max_holding_days
        0 if stop was reached before target (or both hit same day --
          see same-day handling below), within max_holding_days
        None if NEITHER was reached within max_holding_days -- this
          trade's outcome is ambiguous/incomplete and must be DROPPED
          from the training set, not guessed at.

    Same-day ambiguity: daily OHLC data can't tell us whether a bar
    that touches both stop and target hit stop first or target first
    intraday. We assume the worse case (stop hit first) -- label 0 --
    rather than assuming the better case. This is a deliberate
    conservative bias, not an oversight.
    """
    if stop_loss >= entry_price:
        raise ValueError("stop_loss must be below entry_price (long-only labeling)")
    if target <= entry_price:
        raise ValueError("target must be above entry_price (long-only labeling)")
    if max_holding_days <= 0:
        raise ValueError("max_holding_days must be positive")

    for bar in future_bars[:max_holding_days]:
        stop_hit = bar.low <= stop_loss
        target_hit = bar.high >= target

        if stop_hit and target_hit:
            return 0  # ambiguous same-day touch -- conservative assumption
        if stop_hit:
            return 0
        if target_hit:
            return 1

    return None  # neither hit within the window -- drop this sample