"""
Paper-trading execution simulation -- pure computation, no I/O.

Simulates realistic fills per the problem statement's "Paper Trading and
Validation" section: "entry availability, bid/ask spread where data
permits, slippage, brokerage and other applicable trading costs." We
don't have real bid/ask data, so slippage is modeled as a fixed
basis-point cost that always works AGAINST the trader (buy fills higher
than signal price, sell fills lower) -- this is the standard
conservative assumption when real spread data isn't available.
"""

from dataclasses import dataclass

SLIPPAGE_BPS = 5.0
ROUND_TRIP_COST_PCT = 0.1


@dataclass
class ExecutionResult:
    signal_price: float
    actual_entry_price: float
    exit_signal_price: float
    actual_exit_price: float
    quantity: int
    gross_pnl: float
    total_costs: float
    net_pnl: float


def simulate_entry_fill(signal_price: float, slippage_bps: float = SLIPPAGE_BPS) -> float:
    if signal_price <= 0:
        raise ValueError("signal_price must be positive")
    return signal_price * (1 + slippage_bps / 10_000)


def simulate_exit_fill(exit_signal_price: float, slippage_bps: float = SLIPPAGE_BPS) -> float:
    if exit_signal_price <= 0:
        raise ValueError("exit_signal_price must be positive")
    return exit_signal_price * (1 - slippage_bps / 10_000)


def calculate_round_trip_costs(
    entry_value: float, exit_value: float, cost_pct_per_side: float = ROUND_TRIP_COST_PCT
) -> float:
    return (entry_value + exit_value) * (cost_pct_per_side / 100)


def simulate_trade_execution(
    signal_entry_price: float,
    signal_exit_price: float,
    quantity: int,
    slippage_bps: float = SLIPPAGE_BPS,
    cost_pct_per_side: float = ROUND_TRIP_COST_PCT,
) -> ExecutionResult:
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    actual_entry = simulate_entry_fill(signal_entry_price, slippage_bps)
    actual_exit = simulate_exit_fill(signal_exit_price, slippage_bps)

    gross_pnl = (actual_exit - actual_entry) * quantity
    entry_value = actual_entry * quantity
    exit_value = actual_exit * quantity
    costs = calculate_round_trip_costs(entry_value, exit_value, cost_pct_per_side)
    net_pnl = gross_pnl - costs

    return ExecutionResult(
        signal_price=signal_entry_price,
        actual_entry_price=round(actual_entry, 4),
        exit_signal_price=signal_exit_price,
        actual_exit_price=round(actual_exit, 4),
        quantity=quantity,
        gross_pnl=round(gross_pnl, 2),
        total_costs=round(costs, 2),
        net_pnl=round(net_pnl, 2),
    )