"""
Tests for the (pure, I/O-free) Market Regime Engine logic.
Run: python -m pytest tests/test_regime.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _helpers import use_service  # noqa: E402

use_service("regime-engine")
from app.regime import MarketRegime, compute_regime  # noqa: E402


def test_strong_uptrend_with_broad_participation_is_bullish():
    r = compute_regime(trend_score=0.30, volatility_score=1.0, breadth_pct_above_ema20=75.0)
    assert r.regime == MarketRegime.BULLISH
    assert r.confidence > 0.5


def test_strong_downtrend_with_weak_breadth_is_bearish():
    r = compute_regime(trend_score=-0.30, volatility_score=1.0, breadth_pct_above_ema20=20.0)
    assert r.regime == MarketRegime.BEARISH
    assert r.confidence > 0.5


def test_high_volatility_overrides_bullish_trend():
    r = compute_regime(trend_score=0.30, volatility_score=1.8, breadth_pct_above_ema20=75.0)
    assert r.regime == MarketRegime.HIGH_VOLATILITY


def test_calm_flat_market_is_low_volatility_not_sideways():
    r = compute_regime(trend_score=0.005, volatility_score=0.5, breadth_pct_above_ema20=50.0)
    assert r.regime == MarketRegime.LOW_VOLATILITY


def test_calm_uptrend_is_still_bullish_not_low_volatility():
    r = compute_regime(trend_score=0.25, volatility_score=0.6, breadth_pct_above_ema20=70.0)
    assert r.regime == MarketRegime.BULLISH


def test_mixed_signals_near_neutral_is_sideways():
    r = compute_regime(trend_score=0.005, volatility_score=1.0, breadth_pct_above_ema20=52.0)
    assert r.regime == MarketRegime.SIDEWAYS


def test_disagreeing_trend_and_breadth_is_transitional():
    r = compute_regime(trend_score=0.10, volatility_score=1.0, breadth_pct_above_ema20=25.0)
    assert r.regime == MarketRegime.TRANSITIONAL


def test_every_regime_enum_value_is_reachable():
    test_cases = [
        (0.30, 1.0, 75.0),    # bullish
        (-0.30, 1.0, 20.0),   # bearish
        (0.005, 1.0, 52.0),   # sideways
        (0.30, 1.8, 75.0),    # high_volatility
        (0.005, 0.5, 50.0),   # low_volatility
        (0.10, 1.0, 25.0),    # transitional
    ]
    seen_regimes = {compute_regime(*args).regime for args in test_cases}
    assert seen_regimes == set(MarketRegime), (
        f"Unreachable regime(s): {set(MarketRegime) - seen_regimes}"
    )


def test_confidence_always_between_0_and_1():
    import random

    rng = random.Random(42)
    for _ in range(200):
        trend = rng.uniform(-1, 1)
        vol = rng.uniform(0, 3)
        breadth = rng.uniform(0, 100)
        r = compute_regime(trend, vol, breadth)
        assert 0.0 <= r.confidence <= 1.0, f"confidence {r.confidence} out of bounds for {r.regime}"


def test_contributing_factors_always_populated():
    import random

    rng = random.Random(7)
    for _ in range(50):
        r = compute_regime(rng.uniform(-1, 1), rng.uniform(0, 3), rng.uniform(0, 100))
        assert len(r.contributing_factors) > 0

def test_near_threshold_trend_with_confirming_breadth_is_not_transitional():
    """
    Regression test for a refinement made after initial calibration:
    trend_score=0.02 is past the 'near bullish' half-threshold (0.0125)
    but hasn't crossed the full bullish threshold (0.025) yet. If breadth
    is ALREADY confirming bullish (>=65), this should NOT be labeled
    TRANSITIONAL ("signals disagree") since breadth agrees with the
    trend's direction -- it should fall through to SIDEWAYS/LOW_VOLATILITY
    instead, whichever the volatility_score indicates.
    """
    r = compute_regime(trend_score=0.02, volatility_score=1.0, breadth_pct_above_ema20=70.0)
    assert r.regime != MarketRegime.TRANSITIONAL