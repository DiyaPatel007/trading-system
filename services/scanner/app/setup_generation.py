"""
Trade setup generation -- pure computation, no I/O.

PLACEHOLDER LOGIC, explicitly: this generates entry/stop/target levels
using a simple ATR-based rule, not ML. It exists so the Scanner has
something concrete to rank before Module 6 (ML) exists. When Module 6
lands, this function's SIGNATURE stays the same (still returns
entry/stop/targets) but the internals can be replaced with a
model-informed target/stop selection -- nothing downstream (risk engine,
scoring) needs to change when that happens.
"""

from dataclasses import dataclass

STOP_ATR_MULTIPLE = 1.5
TARGET_R_MULTIPLE = 2.0


@dataclass
class TradeSetup:
    entry_price: float
    stop_loss: float
    target: float


def generate_swing_setup(close: float, atr_14: float) -> TradeSetup:
    """
    close: current close price (used as the placeholder entry).
    atr_14: 14-period Average True Range for this symbol.

    Long-only for now, matching the risk engine's current long-trade
    assumption (see services/risk-engine/app/risk.py).
    """
    if close <= 0:
        raise ValueError("close must be positive")
    if atr_14 <= 0:
        raise ValueError("atr_14 must be positive")

    risk_per_share = STOP_ATR_MULTIPLE * atr_14
    entry = close
    stop = entry - risk_per_share
    target = entry + (TARGET_R_MULTIPLE * risk_per_share)

    return TradeSetup(entry_price=entry, stop_loss=stop, target=target)