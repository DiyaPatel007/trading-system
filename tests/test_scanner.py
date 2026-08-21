"""
Tests for the (pure, I/O-free) Scanner logic: setup generation and scoring.
Run: python -m pytest tests/test_scanner.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _helpers import use_service  # noqa: E402

use_service("scanner")
from app.setup_generation import STOP_ATR_MULTIPLE, TARGET_R_MULTIPLE, generate_swing_setup  # noqa: E402
from app.scoring import (  # noqa: E402
    ScoredCandidate,
    WEIGHT_EXPECTED_VALUE,
    WEIGHT_LIQUIDITY,
    WEIGHT_MOMENTUM,
    WEIGHT_REGIME_ALIGNMENT,
    compute_composite_score,
    compute_liquidity_score,
    compute_momentum_score,
    compute_regime_alignment_score,
    rank_opportunities,
)

use_service("risk-engine")
from app.risk import calculate_risk  # noqa: E402

from trading_schemas import MarketRegime  # noqa: E402


def test_hand_verified_swing_setup():
    """
    close=100, atr_14=2. STOP_ATR_MULTIPLE=1.5 -> risk_per_share=3.
    entry=100, stop=97, target = 100 + 2.0*3 = 106.
    """
    setup = generate_swing_setup(close=100, atr_14=2)
    assert setup.entry_price == 100
    assert setup.stop_loss == pytest.approx(97.0)
    assert setup.target == pytest.approx(106.0)


def test_setup_reward_to_risk_matches_target_r_multiple():
    setup = generate_swing_setup(close=250, atr_14=5)
    risk = setup.entry_price - setup.stop_loss
    reward = setup.target - setup.entry_price
    assert reward / risk == pytest.approx(TARGET_R_MULTIPLE)


def test_zero_atr_raises():
    with pytest.raises(ValueError, match="atr_14 must be positive"):
        generate_swing_setup(close=100, atr_14=0)


def test_negative_close_raises():
    with pytest.raises(ValueError, match="close must be positive"):
        generate_swing_setup(close=-10, atr_14=2)


def test_weights_sum_to_one():
    total = WEIGHT_EXPECTED_VALUE + WEIGHT_MOMENTUM + WEIGHT_REGIME_ALIGNMENT + WEIGHT_LIQUIDITY
    assert total == pytest.approx(1.0)


def test_momentum_score_bounds_and_direction():
    assert compute_momentum_score(50) == pytest.approx(0.0)
    assert compute_momentum_score(100) == pytest.approx(1.0)
    assert compute_momentum_score(0) == pytest.approx(-1.0)
    assert compute_momentum_score(75) > compute_momentum_score(60)


def test_liquidity_score_bounds_and_direction():
    assert compute_liquidity_score(1.0) == pytest.approx(0.0)
    assert compute_liquidity_score(2.5) == pytest.approx(1.0)
    assert compute_liquidity_score(0.1) == pytest.approx(-0.9)
    assert compute_liquidity_score(1.5) > compute_liquidity_score(1.1)


def test_regime_alignment_bullish_positive_bearish_negative():
    bullish_score = compute_regime_alignment_score(MarketRegime.BULLISH, regime_confidence=0.8)
    bearish_score = compute_regime_alignment_score(MarketRegime.BEARISH, regime_confidence=0.8)
    assert bullish_score == pytest.approx(0.8)
    assert bearish_score == pytest.approx(-0.8)


def test_regime_alignment_high_volatility_is_penalized_regardless():
    score = compute_regime_alignment_score(MarketRegime.HIGH_VOLATILITY, regime_confidence=0.9)
    assert score < 0


def test_regime_alignment_neutral_regimes_are_zero():
    for regime in (MarketRegime.SIDEWAYS, MarketRegime.LOW_VOLATILITY, MarketRegime.TRANSITIONAL):
        assert compute_regime_alignment_score(regime, regime_confidence=0.9) == 0.0


def test_composite_score_hand_calculation():
    """
    R:R=3, EV=1.0 (win_prob=0.5 default) from a 100/98/106 trade.
    momentum_score=0.4, regime_alignment=0.6, liquidity=0.2.
    composite = 1.0*0.40 + 0.4*0.25 + 0.6*0.20 + 0.2*0.15
              = 0.40 + 0.10 + 0.12 + 0.03 = 0.65
    """
    risk = calculate_risk("TEST.NS", entry_price=100, stop_loss=98, targets=[106])
    composite = compute_composite_score(
        risk_assessment=risk, momentum_score=0.4, regime_alignment_score=0.6, liquidity_score=0.2
    )
    assert composite == pytest.approx(0.65, abs=0.001)


def _make_candidate(symbol: str, composite_score: float, approved: bool = True) -> ScoredCandidate:
    risk = calculate_risk("TEST.NS", entry_price=100, stop_loss=98, targets=[106])
    if not approved:
        risk = calculate_risk("TEST.NS", entry_price=100, stop_loss=99, targets=[100.5])
    return ScoredCandidate(
        symbol=symbol,
        composite_score=composite_score,
        risk_assessment=risk,
        momentum_score=0.0,
        regime_alignment_score=0.0,
        liquidity_score=0.0,
    )


def test_rank_opportunities_sorts_descending():
    candidates = [
        _make_candidate("A", 0.3),
        _make_candidate("B", 0.9),
        _make_candidate("C", 0.5),
    ]
    ranked = rank_opportunities(candidates, top_n=5)
    assert [c.symbol for c in ranked] == ["B", "C", "A"]


def test_rank_opportunities_excludes_unapproved_regardless_of_score():
    """
    Core requirement: an unapproved trade must NEVER appear in the ranked
    output, even if it has the highest composite score of all candidates.
    """
    candidates = [
        _make_candidate("GREAT_SCORE_BUT_REJECTED", 999.0, approved=False),
        _make_candidate("DECENT_AND_APPROVED", 0.4, approved=True),
    ]
    ranked = rank_opportunities(candidates, top_n=5)
    symbols = [c.symbol for c in ranked]
    assert "GREAT_SCORE_BUT_REJECTED" not in symbols
    assert "DECENT_AND_APPROVED" in symbols


def test_rank_opportunities_respects_top_n():
    candidates = [_make_candidate(f"SYM{i}", float(i)) for i in range(10)]
    ranked = rank_opportunities(candidates, top_n=3)
    assert len(ranked) == 3
    assert [c.symbol for c in ranked] == ["SYM9", "SYM8", "SYM7"]