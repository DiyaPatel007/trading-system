"""
Tests for the (pure, I/O-free) trade outcome labeling logic.
Run: python -m pytest tests/test_labeling.py -v

Correctness here matters more than almost anywhere else in the system --
a labeling bug silently corrupts every model trained on top of it.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _helpers import use_service  # noqa: E402

use_service("ml-training")
from app.labeling import FutureBar, label_trade  # noqa: E402


ENTRY = 100.0
STOP = 95.0
TARGET = 110.0


def test_target_hit_on_first_day_labels_win():
    bars = [FutureBar(high=111, low=99)]
    assert label_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5) == 1


def test_stop_hit_on_first_day_labels_loss():
    bars = [FutureBar(high=101, low=94)]
    assert label_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5) == 0


def test_neither_hit_within_window_returns_none():
    bars = [FutureBar(high=102, low=98) for _ in range(5)]
    assert label_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5) is None


def test_target_hit_on_later_day_after_quiet_days_labels_win():
    bars = [
        FutureBar(high=102, low=98),
        FutureBar(high=103, low=97),
        FutureBar(high=111, low=100),
    ]
    assert label_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5) == 1


def test_stop_hit_on_later_day_after_quiet_days_labels_loss():
    bars = [
        FutureBar(high=102, low=98),
        FutureBar(high=103, low=97),
        FutureBar(high=104, low=94),
    ]
    assert label_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5) == 0


def test_earlier_hit_wins_even_if_opposite_would_hit_later():
    """
    Critical ordering test: stop is hit on day 1, target would ALSO have
    been hit on day 3 if the trade were still open -- but it isn't,
    because the stop closed it first. Must label 0, not 1.
    """
    bars = [
        FutureBar(high=101, low=94),
        FutureBar(high=102, low=98),
        FutureBar(high=112, low=100),
    ]
    assert label_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5) == 0


def test_same_day_both_touched_is_conservative_loss():
    bars = [FutureBar(high=112, low=93)]
    assert label_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5) == 0


def test_only_bars_within_max_holding_days_are_considered():
    bars = [FutureBar(high=102, low=98) for _ in range(5)] + [
        FutureBar(high=111, low=100)
    ]
    assert label_trade(bars, ENTRY, STOP, TARGET, max_holding_days=5) is None


def test_fewer_bars_than_max_holding_days_still_works():
    bars = [FutureBar(high=102, low=98), FutureBar(high=103, low=97)]
    assert label_trade(bars, ENTRY, STOP, TARGET, max_holding_days=10) is None


def test_empty_future_bars_returns_none():
    assert label_trade([], ENTRY, STOP, TARGET, max_holding_days=5) is None


def test_invalid_stop_above_entry_raises():
    with pytest.raises(ValueError, match="stop_loss must be below entry_price"):
        label_trade([FutureBar(101, 99)], entry_price=100, stop_loss=105, target=110, max_holding_days=5)


def test_invalid_target_below_entry_raises():
    with pytest.raises(ValueError, match="target must be above entry_price"):
        label_trade([FutureBar(101, 99)], entry_price=100, stop_loss=95, target=99, max_holding_days=5)


def test_invalid_max_holding_days_raises():
    with pytest.raises(ValueError, match="max_holding_days must be positive"):
        label_trade([FutureBar(101, 99)], entry_price=100, stop_loss=95, target=110, max_holding_days=0)