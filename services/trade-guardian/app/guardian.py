"""
Trade Guardian -- pure computation, no I/O.

Re-assesses an OPEN trade's risk as conditions change, per the problem
statement's "Trade Guardian and Dynamic Risk Monitoring" section:
"If the market regime changes, sector momentum weakens, volatility
increases, volume disappears, or the ML probability deteriorates
significantly, the system should update the trade's risk assessment."

CRITICAL DESIGN CONSTRAINT: this module NEVER modifies a stop-loss,
target, or closes a trade. It only produces alerts and an updated risk
read -- "hard risk controls should remain independent of the AI model."
Nothing in this file writes to paper_trades; the DB wrapper
(monitor_open_trades.py) only ever INSERTs into a separate
trade_guardian_alerts table.
"""

from dataclasses import dataclass, field
from enum import Enum

from trading_schemas import MarketRegime, RiskCategory

ADVERSE_EXCURSION_WATCH_PCT = 40.0
ADVERSE_EXCURSION_ELEVATED_PCT = 70.0
RSI_WEAKENING_THRESHOLD = 45.0

_DETERIORATED_REGIMES = {MarketRegime.BEARISH, MarketRegime.HIGH_VOLATILITY}
_BENIGN_REGIMES = {
    MarketRegime.BULLISH, MarketRegime.SIDEWAYS,
    MarketRegime.LOW_VOLATILITY, MarketRegime.TRANSITIONAL,
}


class AlertLevel(str, Enum):
    NONE = "none"
    WATCH = "watch"
    ELEVATED = "elevated"
    CRITICAL = "critical"


_ALERT_LEVEL_SEVERITY = {
    AlertLevel.NONE: 0, AlertLevel.WATCH: 1, AlertLevel.ELEVATED: 2, AlertLevel.CRITICAL: 3,
}


def _more_severe(a: AlertLevel, b: AlertLevel) -> AlertLevel:
    return a if _ALERT_LEVEL_SEVERITY[a] >= _ALERT_LEVEL_SEVERITY[b] else b


_RISK_ESCALATION_ORDER = [
    RiskCategory.VERY_LOW, RiskCategory.LOW, RiskCategory.MODERATE,
    RiskCategory.HIGH, RiskCategory.VERY_HIGH,
]


@dataclass
class GuardianAssessment:
    alert_level: AlertLevel
    updated_risk_category: RiskCategory
    adverse_excursion_pct: float
    alerts: list[str] = field(default_factory=list)


def _escalate_risk_category(original: RiskCategory, steps: int = 1) -> RiskCategory:
    idx = _RISK_ESCALATION_ORDER.index(original)
    new_idx = min(idx + steps, len(_RISK_ESCALATION_ORDER) - 1)
    return _RISK_ESCALATION_ORDER[new_idx]


def evaluate_open_trade(
    entry_price: float,
    stop_loss: float,
    current_price: float,
    original_risk_category: RiskCategory,
    regime_at_open: MarketRegime,
    regime_now: MarketRegime,
    regime_confidence_now: float,
    rsi_now: float | None,
) -> GuardianAssessment:
    """
    entry_price/stop_loss are fixed (from when the trade opened) --
    NEVER modified here. current_price is today's latest close.
    """
    if stop_loss >= entry_price:
        raise ValueError("stop_loss must be below entry_price (long-only)")

    alerts: list[str] = []
    escalation_steps = 0
    max_level = AlertLevel.NONE

    total_risk_distance = entry_price - stop_loss
    distance_traveled = entry_price - current_price
    adverse_pct = (distance_traveled / total_risk_distance) * 100

    if adverse_pct >= ADVERSE_EXCURSION_ELEVATED_PCT:
        alerts.append(
            f"Price has moved {adverse_pct:.0f}% of the way from entry toward the stop -- "
            "thesis under significant pressure"
        )
        escalation_steps += 1
        max_level = AlertLevel.CRITICAL
    elif adverse_pct >= ADVERSE_EXCURSION_WATCH_PCT:
        alerts.append(
            f"Price has moved {adverse_pct:.0f}% of the way from entry toward the stop -- watching closely"
        )
        max_level = _more_severe(max_level, AlertLevel.WATCH)

    regime_deteriorated = regime_at_open in _BENIGN_REGIMES and regime_now in _DETERIORATED_REGIMES
    if regime_deteriorated:
        alerts.append(
            f"Market regime shifted from {regime_at_open.value} to {regime_now.value} "
            f"(confidence {regime_confidence_now:.2f}) since this trade was opened"
        )
        escalation_steps += 1
        if regime_now == MarketRegime.HIGH_VOLATILITY:
            max_level = AlertLevel.CRITICAL
        else:
            max_level = _more_severe(max_level, AlertLevel.ELEVATED)

    if rsi_now is not None and rsi_now < RSI_WEAKENING_THRESHOLD:
        alerts.append(f"Momentum weakening -- RSI now {rsi_now:.1f}, below the {RSI_WEAKENING_THRESHOLD} threshold")
        max_level = _more_severe(max_level, AlertLevel.WATCH)

    updated_category = (
        _escalate_risk_category(original_risk_category, escalation_steps)
        if escalation_steps > 0 else original_risk_category
    )

    if not alerts:
        alerts.append("No changes -- trade thesis still holds as originally assessed")

    return GuardianAssessment(
        alert_level=max_level,
        updated_risk_category=updated_category,
        adverse_excursion_pct=round(adverse_pct, 2),
        alerts=alerts,
    )