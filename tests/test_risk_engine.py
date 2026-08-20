"""
Tests for the (pure, I/O-free) Risk Engine logic.
Run: python -m pytest tests/test_risk_engine.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _helpers import use_service  # noqa: E402

use_service("risk-engine")
from app.risk import calculate_risk, size_position  # noqa: E402


# ---------- calculate_risk ----------

def test_hand_verified_good_trade_is_approved():
    """
    Entry 100, stop 98 (risk=2, risk_pct=2%), target 106 (reward=6).
    R:R = 6/2 = 3.0 -- comfortably above the 1.5 minimum, risk_pct=2%
    is under the 3% max -- should be approved, category LOW
    (R:R>=2 and risk_pct<=2).
    """
    r = calculate_risk("TEST.NS", entry_price=100, stop_loss=98, targets=[106])
    assert r.risk_per_share == 2.0
    assert r.reward_to_risk_ratio == 3.0
    assert r.approved is True
    assert r.rejection_reasons == []
    assert r.risk_category.value == "low"


def test_hand_verified_oversized_stop_is_rejected_despite_good_rr():
    """
    Entry 100, stop 95 (risk=5, risk_pct=5%), target 115 (reward=15).
    R:R = 15/5 = 3.0 -- excellent reward:risk, BUT risk_pct=5% exceeds
    the 3% hard cap. Must be rejected regardless of the good R:R --
    this is the core "risk engine can veto regardless of upside" test.
    """
    r = calculate_risk("TEST.NS", entry_price=100, stop_loss=95, targets=[115])
    assert r.reward_to_risk_ratio == 3.0
    assert r.approved is False
    assert any("Risk per share" in reason for reason in r.rejection_reasons)


def test_poor_reward_risk_ratio_is_rejected():
    """Entry 100, stop 99 (risk=1), target 100.5 (reward=0.5) -> R:R=0.5, well below 1.5."""
    r = calculate_risk("TEST.NS", entry_price=100, stop_loss=99, targets=[100.5])
    assert r.approved is False
    assert any("Reward:risk" in reason for reason in r.rejection_reasons)


def test_expected_value_calculation_is_correct():
    """
    R:R=3, win_probability=0.5 (default) ->
    EV = (3 * 0.5) - (1 * 0.5) = 1.5 - 0.5 = 1.0 R
    """
    r = calculate_risk("TEST.NS", entry_price=100, stop_loss=98, targets=[106])
    assert r.expected_value_r == pytest.approx(1.0, abs=0.001)


def test_higher_win_probability_increases_expected_value():
    low_conf = calculate_risk("TEST.NS", 100, 98, [106], win_probability=0.4)
    high_conf = calculate_risk("TEST.NS", 100, 98, [106], win_probability=0.7)
    assert high_conf.expected_value_r > low_conf.expected_value_r


def test_very_low_risk_category_requires_both_good_rr_and_small_risk_pct():
    # R:R=4 (great) but risk_pct=2% (not <=1%) -- should NOT be VERY_LOW
    r = calculate_risk("TEST.NS", entry_price=100, stop_loss=98, targets=[108])
    assert r.risk_category.value != "very_low"

    # R:R=4 AND risk_pct=0.5% -- both conditions met -- should be VERY_LOW
    r2 = calculate_risk("TEST.NS", entry_price=100, stop_loss=99.5, targets=[102])
    assert r2.risk_category.value == "very_low"


def test_stop_above_entry_raises():
    with pytest.raises(ValueError, match="stop_loss must be below entry_price"):
        calculate_risk("TEST.NS", entry_price=100, stop_loss=101, targets=[110])


def test_target_below_entry_raises():
    with pytest.raises(ValueError, match="targets must be above entry_price"):
        calculate_risk("TEST.NS", entry_price=100, stop_loss=95, targets=[99])


def test_risk_distribution_probabilities_are_internally_consistent():
    r = calculate_risk("TEST.NS", 100, 98, [106], win_probability=0.6)
    dist = r.risk_distribution
    # Higher R multiples should never be MORE likely than lower ones
    assert dist.prob_plus_1r >= dist.prob_plus_2r >= dist.prob_plus_3r
    assert dist.prob_plus_1r + dist.prob_minus_1r == pytest.approx(1.0, abs=0.001)


# ---------- size_position ----------

def test_hand_verified_position_size():
    """
    Capital 100,000; max_risk_pct_per_trade 0.5% -> max_risk_amount 500.
    Entry 100, stop 98 -> risk_per_share 2 -> quantity_by_risk = 500/2 = 250.
    Position cap: 10% of 100,000 = 10,000 -> quantity_by_position_cap = 10000/100 = 100.
    The position cap (100) is the binding constraint here, not the risk cap (250).
    """
    ps = size_position(
        "TEST.NS", capital=100_000, max_risk_pct_per_trade=0.5,
        entry_price=100, stop_loss=98,
    )
    assert ps.max_risk_amount == 500.0
    assert ps.quantity == 100  # position-size cap binds, not risk cap
    assert ps.capital_deployed == 10_000.0
    assert ps.within_portfolio_constraints is True


def test_position_size_capped_by_risk_when_risk_is_binding():
    """
    Same capital, but a much wider stop makes the risk-based quantity
    the binding constraint instead of the position-size cap.
    Entry 100, stop 50 -> risk_per_share 50 -> quantity_by_risk = 500/50 = 10.
    Position cap still 100 -> risk cap (10) binds instead.
    """
    ps = size_position(
        "TEST.NS", capital=100_000, max_risk_pct_per_trade=0.5,
        entry_price=100, stop_loss=50,
    )
    assert ps.quantity == 10


def test_portfolio_exposure_violation_detected():
    ps = size_position(
        "TEST.NS", capital=100_000, max_risk_pct_per_trade=0.5,
        entry_price=100, stop_loss=98,
        existing_portfolio_value=75_000,  # already 75% deployed
    )
    # New position would add another 10,000 -> 85% total, above the 80% cap
    assert ps.within_portfolio_constraints is False
    assert any("Portfolio exposure" in v for v in ps.constraint_violations)


def test_sector_exposure_violation_detected():
    ps = size_position(
        "TEST.NS", capital=100_000, max_risk_pct_per_trade=0.5,
        entry_price=100, stop_loss=98,
        sector="Banking", existing_sector_exposure_value=20_000,
    )
    # New position adds 10,000 -> 30% sector exposure, above the 25% cap
    assert ps.within_portfolio_constraints is False
    assert any("Banking" in v for v in ps.constraint_violations)


def test_zero_quantity_when_risk_amount_smaller_than_one_share_risk():
    """A very small capital / tight risk budget can legitimately round to 0 shares."""
    ps = size_position(
        "TEST.NS", capital=1_000, max_risk_pct_per_trade=0.1,
        entry_price=100, stop_loss=50,  # risk_per_share=50, max_risk_amount=1
    )
    assert ps.quantity == 0
    assert ps.within_portfolio_constraints is False
    assert any("rounds to zero" in v for v in ps.constraint_violations)


def test_stop_above_entry_raises_in_sizing_too():
    with pytest.raises(ValueError, match="stop_loss must be below entry_price"):
        size_position("TEST.NS", capital=100_000, max_risk_pct_per_trade=0.5, entry_price=100, stop_loss=105)