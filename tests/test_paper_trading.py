"""
Tests for the (pure, I/O-free) paper trading logic: execution
simulation, exit evaluation, and performance metrics.
Run: python -m pytest tests/test_paper_trading.py -v
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _helpers import use_service  # noqa: E402

use_service("paper-trading")
from app.execution import (  # noqa: E402
    ROUND_TRIP_COST_PCT,
    SLIPPAGE_BPS,
    calculate_round_trip_costs,
    simulate_entry_fill,
    simulate_exit_fill,
    simulate_trade_execution,
)
from app.exit_evaluation import FutureBar, evaluate_open_trade  # noqa: E402
from app.performance import ClosedTrade, compute_performance_metrics  # noqa: E402


# ---------- execution.py ----------

def test_entry_fill_is_worse_than_signal_price():
    """Long entry must fill HIGHER than the signal price (slippage against the trader)."""
    fill = simulate_entry_fill(100.0, slippage_bps=5.0)
    assert fill > 100.0
    assert fill == pytest.approx(100.05, abs=0.001)  # 100 * (1 + 5/10000)


def test_exit_fill_is_worse_than_signal_price():
    """Long exit (sell) must fill LOWER than the signal price."""
    fill = simulate_exit_fill(110.0, slippage_bps=5.0)
    assert fill < 110.0
    assert fill == pytest.approx(109.945, abs=0.001)  # 110 * (1 - 5/10000)


def test_hand_verified_full_trade_execution():
    """
    Entry signal 100, exit signal 110, qty 100, slippage 5bps, cost 0.1%/side.
    actual_entry = 100 * 1.0005 = 100.05
    actual_exit  = 110 * 0.9995 = 109.945
    gross_pnl = (109.945 - 100.05) * 100 = 989.5
    entry_value = 10005, exit_value = 10994.5
    costs = (10005 + 10994.5) * 0.001 = 20.9995 -> 21.00
    net_pnl = 989.5 - 21.00 = 968.50
    """
    result = simulate_trade_execution(
        signal_entry_price=100.0, signal_exit_price=110.0, quantity=100,
    )
    assert result.actual_entry_price == pytest.approx(100.05, abs=0.001)
    assert result.actual_exit_price == pytest.approx(109.945, abs=0.001)
    assert result.gross_pnl == pytest.approx(989.5, abs=0.01)
    assert result.total_costs == pytest.approx(21.00, abs=0.01)
    assert result.net_pnl == pytest.approx(968.50, abs=0.01)


def test_costs_are_always_positive():
    costs = calculate_round_trip_costs(entry_value=10_000, exit_value=9_500)
    assert costs > 0


def test_zero_or_negative_quantity_raises():
    with pytest.raises(ValueError, match="quantity must be positive"):
        simulate_trade_execution(100.0, 110.0, quantity=0)


def test_negative_price_raises():
    with pytest.raises(ValueError, match="signal_price must be positive"):
        simulate_entry_fill(-10.0)


def test_realistic_losing_trade_costs_reduce_pnl_further():
    """A losing trade's net_pnl should be WORSE than gross_pnl (costs add
    to the loss, never subtract from it)."""
    result = simulate_trade_execution(signal_entry_price=100.0, signal_exit_price=95.0, quantity=50)
    assert result.gross_pnl < 0
    assert result.net_pnl < result.gross_pnl  # costs make the loss even bigger


# ---------- exit_evaluation.py ----------

ENTRY, STOP, TARGET = 100.0, 95.0, 110.0


def _bar(day: int, high: float, low: float, close: float) -> FutureBar:
    return FutureBar(ts=datetime(2024, 1, day, tzinfo=timezone.utc), high=high, low=low, close=close)


def test_target_hit_returns_correct_exit_price_and_reason():
    bars = [_bar(2, 111, 99, 105)]
    result = evaluate_open_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5)
    assert result.exit_reason == "target"
    assert result.exit_price == TARGET
    assert result.exit_ts == bars[0].ts


def test_stop_hit_returns_correct_exit_price_and_reason():
    bars = [_bar(2, 101, 94, 96)]
    result = evaluate_open_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5)
    assert result.exit_reason == "stop"
    assert result.exit_price == STOP


def test_time_exit_when_window_fully_elapses_unresolved():
    bars = [_bar(d, 102, 98, 100) for d in range(2, 7)]  # 5 quiet days, window=5
    result = evaluate_open_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5)
    assert result.exit_reason == "time"
    assert result.exit_price == 100  # last bar's close
    assert result.exit_ts == bars[-1].ts


def test_still_open_when_not_enough_future_data_yet():
    """Fewer bars than max_holding_days AND none resolved -- must be
    'still_open', distinct from 'time' (which means the window fully
    elapsed). This distinction matters for monitor_trades.py deciding
    whether to close a trade or leave it open."""
    bars = [_bar(2, 102, 98, 100), _bar(3, 103, 97, 100)]  # only 2 of 5 days available
    result = evaluate_open_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5)
    assert result.exit_reason == "still_open"
    assert result.exit_price is None
    assert result.exit_ts is None


def test_mfe_mae_tracked_even_on_eventual_stop_out():
    """A trade that ran up nicely (MFE) before reversing and hitting
    stop should still report the MFE it achieved along the way."""
    bars = [
        _bar(2, 108, 99, 107),   # ran up to +8 favorable, didn't hit target(110)
        _bar(3, 103, 94, 95),    # then reversed and hit stop
    ]
    result = evaluate_open_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5)
    assert result.exit_reason == "stop"
    assert result.max_favorable_excursion == pytest.approx(8.0)  # 108 - 100
    assert result.max_adverse_excursion == pytest.approx(6.0)    # 100 - 94


def test_same_day_both_touched_is_conservative_stop():
    bars = [_bar(2, 112, 93, 100)]  # spans both stop=95 and target=110
    result = evaluate_open_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5)
    assert result.exit_reason == "stop"


def test_earlier_bar_resolves_before_later_bar_would():
    """Ordering discipline, mirroring Module 6's labeling test: stop hit
    on day 1 must close the trade even if day 3 would have hit target."""
    bars = [
        _bar(2, 101, 94, 96),     # stop hit here
        _bar(3, 102, 98, 100),
        _bar(4, 112, 100, 111),   # target WOULD hit here, but too late
    ]
    result = evaluate_open_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5)
    assert result.exit_reason == "stop"
    assert result.exit_ts == bars[0].ts


# ---------- performance.py ----------

def test_hand_verified_performance_metrics():
    """
    Trades: +100 (win), +200 (win), -50 (loss), -30 (loss), +150 (win).
    total=5, wins=3, losses=2, win_rate=0.6
    avg_win = (100+200+150)/3 = 150
    avg_loss = (-50-30)/2 = -40
    gross_profit=450, gross_loss=80, profit_factor=450/80=5.625
    expected_value = (100+200-50-30+150)/5 = 370/5 = 74
    """
    trades = [
        ClosedTrade(100, True), ClosedTrade(200, True), ClosedTrade(-50, False),
        ClosedTrade(-30, False), ClosedTrade(150, True),
    ]
    m = compute_performance_metrics(trades)
    assert m.total_trades == 5
    assert m.winning_trades == 3
    assert m.win_rate == pytest.approx(0.6)
    assert m.average_win == pytest.approx(150.0)
    assert m.average_loss == pytest.approx(-40.0)
    assert m.profit_factor == pytest.approx(5.625)
    assert m.expected_value_per_trade == pytest.approx(74.0)


def test_empty_trade_list_returns_zeroed_metrics_not_error():
    m = compute_performance_metrics([])
    assert m.total_trades == 0
    assert m.win_rate == 0.0
    assert m.profit_factor is None


def test_no_losses_gives_none_profit_factor_not_divide_by_zero():
    trades = [ClosedTrade(100, True), ClosedTrade(50, True)]
    m = compute_performance_metrics(trades)
    assert m.profit_factor is None
    assert m.losing_trades == 0


def test_max_drawdown_hand_verified():
    """
    Cumulative P&L walk: +100 -> 100 (peak=100)
                          -150 -> -50 (drawdown = -50-100 = -150)
                          +80  -> 30  (drawdown = 30-100 = -70)
    Max drawdown should be -150 (the worst point).
    """
    trades = [ClosedTrade(100, True), ClosedTrade(-150, False), ClosedTrade(80, True)]
    m = compute_performance_metrics(trades)
    assert m.max_drawdown == pytest.approx(-150.0)


def test_max_drawdown_zero_when_always_winning():
    trades = [ClosedTrade(10, True), ClosedTrade(20, True), ClosedTrade(5, True)]
    m = compute_performance_metrics(trades)
    assert m.max_drawdown == 0.0