"""
Unit tests for the shared schema package. Run these first, before
touching docker-compose, to confirm the data contracts are sound.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from trading_schemas import (
    Candle,
    PositionSize,
    RiskAssessment,
    RiskCategory,
    RiskDistribution,
    Signal,
    SignalReasoning,
    TradeDecision,
    TradingMode,
)


def make_candle(**overrides):
    base = dict(
        symbol="RELIANCE.NS",
        timeframe="1d",
        timestamp=datetime.now(timezone.utc),
        open=2900.0,
        high=2950.0,
        low=2890.0,
        close=2930.0,
        volume=1_500_000,
    )
    base.update(overrides)
    return Candle(**base)


def test_valid_candle_accepted():
    c = make_candle()
    assert c.high >= c.low
    assert c.volume > 0


@pytest.mark.parametrize(
    "overrides",
    [
        dict(high=2800.0),          # high below low
        dict(close=3000.0),         # close above high
        dict(open=2800.0, high=2850, low=2890, close=2930),  # low above open
        dict(volume=-100),          # negative volume
    ],
)
def test_invalid_candle_rejected(overrides):
    with pytest.raises(ValidationError):
        make_candle(**overrides)


def test_risk_assessment_round_trip():
    ra = RiskAssessment(
        symbol="TCS.NS",
        entry_price=3800.0,
        stop_loss=3750.0,
        targets=[3900.0, 3980.0],
        risk_per_share=50.0,
        reward_to_risk_ratio=2.0,
        expected_value_r=0.6,
        risk_category=RiskCategory.MODERATE,
        risk_distribution=RiskDistribution(
            prob_plus_1r=0.55, prob_plus_2r=0.35, prob_plus_3r=0.15, prob_minus_1r=0.40
        ),
        approved=True,
    )
    # Round-trip through JSON to confirm serialization is stable --
    # every service will pass these objects over HTTP/MCP as JSON.
    restored = RiskAssessment.model_validate_json(ra.model_dump_json())
    assert restored == ra


def test_risk_distribution_bounds_enforced():
    with pytest.raises(ValidationError):
        RiskDistribution(
            prob_plus_1r=1.5,  # out of [0, 1] range
            prob_plus_2r=0.3,
            prob_plus_3r=0.1,
            prob_minus_1r=0.4,
        )


def test_position_size_defaults():
    ps = PositionSize(
        symbol="INFY.NS",
        max_risk_amount=1000.0,
        quantity=10,
        capital_deployed=15000.0,
        portfolio_exposure_after_pct=12.5,
        sector_exposure_after_pct=30.0,
        within_portfolio_constraints=True,
    )
    assert ps.constraint_violations == []


def test_signal_records_untaken_by_default():
    s = Signal(
        signal_id="sig-001",
        symbol="HDFCBANK.NS",
        mode=TradingMode.SWING,
        generated_at=datetime.now(timezone.utc),
        decision=TradeDecision.BUY,
        reasoning=SignalReasoning(technical_factors=["Price above EMA20"]),
    )
    # Per "Learning From Both Taken and Untaken Signals" -- default must
    # be False so a signal is never silently assumed to have been acted on.
    assert s.taken_by_user is False
