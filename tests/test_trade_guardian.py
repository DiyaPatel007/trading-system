"""
Tests for the (pure, I/O-free) Trade Guardian assessment logic.
Run: python -m pytest tests/test_trade_guardian.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _helpers import use_service  # noqa: E402

use_service("trade-guardian")
from app.guardian import AlertLevel, evaluate_open_trade  # noqa: E402

from trading_schemas import MarketRegime, RiskCategory  # noqa: E402


ENTRY, STOP = 100.0, 90.0  # total_risk_distance = 10


def test_no_change_when_price_near_entry_and_regime_unchanged():
    result = evaluate_open_trade(
        entry_price=ENTRY, stop_loss=STOP, current_price=101.0,
        original_risk_category=RiskCategory.MODERATE,
        regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BULLISH,
        regime_confidence_now=0.7, rsi_now=60.0,
    )
    assert result.alert_level == AlertLevel.NONE
    assert result.updated_risk_category == RiskCategory.MODERATE
    assert "No changes" in result.alerts[0]


def test_hand_verified_adverse_excursion_calculation():
    """
    entry=100, stop=90 -> total_risk_distance=10.
    current_price=95 -> distance_traveled = 100-95 = 5 -> adverse_pct = 50%.
    """
    result = evaluate_open_trade(
        entry_price=100.0, stop_loss=90.0, current_price=95.0,
        original_risk_category=RiskCategory.MODERATE,
        regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BULLISH,
        regime_confidence_now=0.7, rsi_now=60.0,
    )
    assert result.adverse_excursion_pct == pytest.approx(50.0)
    assert result.alert_level == AlertLevel.WATCH  # 50% >= 40% WATCH threshold, < 70% ELEVATED


def test_severe_adverse_excursion_is_critical_and_escalates_risk_category():
    """current_price=92 -> distance_traveled=8 -> adverse_pct=80%, above the 70% ELEVATED threshold."""
    result = evaluate_open_trade(
        entry_price=100.0, stop_loss=90.0, current_price=92.0,
        original_risk_category=RiskCategory.MODERATE,
        regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BULLISH,
        regime_confidence_now=0.7, rsi_now=60.0,
    )
    assert result.adverse_excursion_pct == pytest.approx(80.0)
    assert result.alert_level == AlertLevel.CRITICAL
    assert result.updated_risk_category == RiskCategory.HIGH  # escalated one step from MODERATE


def test_favorable_price_move_gives_negative_adverse_pct_and_no_alert():
    """Price moved favorably (above entry) -- adverse_pct should be negative, no excursion alert."""
    result = evaluate_open_trade(
        entry_price=100.0, stop_loss=90.0, current_price=105.0,
        original_risk_category=RiskCategory.MODERATE,
        regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BULLISH,
        regime_confidence_now=0.7, rsi_now=60.0,
    )
    assert result.adverse_excursion_pct < 0
    assert result.alert_level == AlertLevel.NONE


def test_regime_deterioration_bullish_to_bearish_escalates():
    result = evaluate_open_trade(
        entry_price=ENTRY, stop_loss=STOP, current_price=99.0,
        original_risk_category=RiskCategory.LOW,
        regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BEARISH,
        regime_confidence_now=0.8, rsi_now=55.0,
    )
    assert any("regime shifted" in a for a in result.alerts)
    assert result.updated_risk_category == RiskCategory.MODERATE  # escalated from LOW
    assert result.alert_level == AlertLevel.ELEVATED


def test_regime_deterioration_to_high_volatility_is_critical():
    result = evaluate_open_trade(
        entry_price=ENTRY, stop_loss=STOP, current_price=99.0,
        original_risk_category=RiskCategory.LOW,
        regime_at_open=MarketRegime.SIDEWAYS, regime_now=MarketRegime.HIGH_VOLATILITY,
        regime_confidence_now=0.85, rsi_now=55.0,
    )
    assert result.alert_level == AlertLevel.CRITICAL


def test_regime_staying_benign_does_not_trigger_deterioration_alert():
    """Sideways -> low_volatility is a regime CHANGE but not a DETERIORATION --
    must not trigger the regime alert."""
    result = evaluate_open_trade(
        entry_price=ENTRY, stop_loss=STOP, current_price=99.0,
        original_risk_category=RiskCategory.LOW,
        regime_at_open=MarketRegime.SIDEWAYS, regime_now=MarketRegime.LOW_VOLATILITY,
        regime_confidence_now=0.7, rsi_now=55.0,
    )
    assert not any("regime shifted" in a for a in result.alerts)


def test_regime_already_bearish_at_open_does_not_re_trigger():
    """If the trade was opened DURING a bearish regime (unusual but possible),
    staying bearish isn't a NEW deterioration -- must not alert."""
    result = evaluate_open_trade(
        entry_price=ENTRY, stop_loss=STOP, current_price=99.0,
        original_risk_category=RiskCategory.LOW,
        regime_at_open=MarketRegime.BEARISH, regime_now=MarketRegime.BEARISH,
        regime_confidence_now=0.7, rsi_now=55.0,
    )
    assert not any("regime shifted" in a for a in result.alerts)


def test_weakening_momentum_triggers_watch_alert():
    result = evaluate_open_trade(
        entry_price=ENTRY, stop_loss=STOP, current_price=99.0,
        original_risk_category=RiskCategory.LOW,
        regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BULLISH,
        regime_confidence_now=0.7, rsi_now=38.0,
    )
    assert any("Momentum weakening" in a for a in result.alerts)
    assert result.alert_level == AlertLevel.WATCH


def test_rsi_none_is_handled_gracefully():
    """If RSI data isn't available for some reason, must not crash."""
    result = evaluate_open_trade(
        entry_price=ENTRY, stop_loss=STOP, current_price=99.0,
        original_risk_category=RiskCategory.LOW,
        regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BULLISH,
        regime_confidence_now=0.7, rsi_now=None,
    )
    assert not any("Momentum" in a for a in result.alerts)


def test_multiple_simultaneous_factors_take_the_most_severe_level():
    """Adverse excursion (WATCH) + regime deterioration (ELEVATED) + weak
    momentum (WATCH) together must report the WORST level (ELEVATED),
    not just the first factor checked."""
    result = evaluate_open_trade(
        entry_price=100.0, stop_loss=90.0, current_price=95.0,  # 50% adverse -> WATCH
        original_risk_category=RiskCategory.LOW,
        regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BEARISH,  # -> ELEVATED
        regime_confidence_now=0.75, rsi_now=35.0,  # -> WATCH
    )
    assert result.alert_level == AlertLevel.ELEVATED
    assert len(result.alerts) == 3


def test_risk_category_escalation_caps_at_very_high():
    """A trade already at VERY_HIGH can't escalate further -- must stay
    VERY_HIGH, not error or wrap around."""
    result = evaluate_open_trade(
        entry_price=100.0, stop_loss=90.0, current_price=92.0,  # severe excursion
        original_risk_category=RiskCategory.VERY_HIGH,
        regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BEARISH,  # also deteriorated
        regime_confidence_now=0.8, rsi_now=30.0,
    )
    assert result.updated_risk_category == RiskCategory.VERY_HIGH


def test_stop_above_entry_raises():
    with pytest.raises(ValueError, match="stop_loss must be below entry_price"):
        evaluate_open_trade(
            entry_price=100.0, stop_loss=105.0, current_price=99.0,
            original_risk_category=RiskCategory.LOW,
            regime_at_open=MarketRegime.BULLISH, regime_now=MarketRegime.BULLISH,
            regime_confidence_now=0.7, rsi_now=50.0,
        )