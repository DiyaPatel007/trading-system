"""
Risk Engine -- pure computation, no I/O.

Operates independently from any ML prediction, per the problem
statement's requirement that risk management be a fundamental component
that can reject a trade "even when the ML model gives it a high
probability." win_probability defaults to a neutral 0.5 placeholder when
not supplied -- Module 6 (ML training) will later pass real calibrated
probabilities through the same parameter; nothing about this function's
contract changes when that happens.
"""

from trading_schemas import PositionSize, RiskAssessment, RiskCategory, RiskDistribution

# --- Hard gate thresholds -- tune deliberately, never silently. ---
MIN_REWARD_RISK_RATIO = 1.5
MAX_RISK_PCT_PER_TRADE = 3.0    # risk-per-share as % of entry price

# --- Position sizing / portfolio constraint thresholds ---
MAX_SINGLE_POSITION_PCT_OF_CAPITAL = 10.0
MAX_PORTFOLIO_EXPOSURE_PCT = 80.0
MAX_SECTOR_EXPOSURE_PCT = 25.0


def calculate_risk(
    symbol: str,
    entry_price: float,
    stop_loss: float,
    targets: list[float],
    win_probability: float = 0.5,
) -> RiskAssessment:
    """
    entry_price, stop_loss, targets: assumes a LONG trade (entry > stop,
    targets > entry). Raises ValueError for nonsensical inputs rather
    than silently producing a misleading risk figure.

    win_probability: probability of reaching the first target before the
    stop. Defaults to a neutral 0.5 when no ML/historical estimate is
    available -- this is a deliberate placeholder, not a prediction.
    """
    if entry_price <= 0 or stop_loss <= 0:
        raise ValueError("entry_price and stop_loss must be positive")
    if stop_loss >= entry_price:
        raise ValueError("stop_loss must be below entry_price for a long trade")
    if not targets or any(t <= entry_price for t in targets):
        raise ValueError("all targets must be above entry_price for a long trade")
    if not (0.0 <= win_probability <= 1.0):
        raise ValueError("win_probability must be between 0 and 1")

    risk_per_share = entry_price - stop_loss
    primary_target = targets[0]
    reward_per_share = primary_target - entry_price
    reward_to_risk_ratio = reward_per_share / risk_per_share
    risk_pct = (risk_per_share / entry_price) * 100

    loss_probability = 1.0 - win_probability
    expected_value_r = (reward_to_risk_ratio * win_probability) - (1.0 * loss_probability)

    prob_plus_1r = win_probability
    prob_plus_2r = win_probability * 0.6
    prob_plus_3r = win_probability * 0.6 * 0.6
    prob_minus_1r = loss_probability

    risk_category = _classify_risk_category(reward_to_risk_ratio, risk_pct)

    rejection_reasons: list[str] = []
    if reward_to_risk_ratio < MIN_REWARD_RISK_RATIO:
        rejection_reasons.append(
            f"Reward:risk {reward_to_risk_ratio:.2f} is below the minimum {MIN_REWARD_RISK_RATIO}"
        )
    if risk_pct > MAX_RISK_PCT_PER_TRADE:
        rejection_reasons.append(
            f"Risk per share is {risk_pct:.2f}% of entry price, above the {MAX_RISK_PCT_PER_TRADE}% max"
        )

    return RiskAssessment(
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        targets=targets,
        risk_per_share=round(risk_per_share, 4),
        reward_to_risk_ratio=round(reward_to_risk_ratio, 4),
        expected_value_r=round(expected_value_r, 4),
        risk_category=risk_category,
        risk_distribution=RiskDistribution(
            prob_plus_1r=round(prob_plus_1r, 4),
            prob_plus_2r=round(prob_plus_2r, 4),
            prob_plus_3r=round(prob_plus_3r, 4),
            prob_minus_1r=round(prob_minus_1r, 4),
        ),
        approved=len(rejection_reasons) == 0,
        rejection_reasons=rejection_reasons,
    )


def _classify_risk_category(reward_to_risk_ratio: float, risk_pct: float) -> RiskCategory:
    """Rule-based classification -- thresholds chosen to require BOTH a
    good reward:risk AND a small risk_pct for the safest categories, so a
    high R:R trade with an oversized stop can't masquerade as low-risk."""
    if reward_to_risk_ratio >= 3.0 and risk_pct <= 1.0:
        return RiskCategory.VERY_LOW
    if reward_to_risk_ratio >= 2.0 and risk_pct <= 2.0:
        return RiskCategory.LOW
    if reward_to_risk_ratio >= 1.5 and risk_pct <= 3.0:
        return RiskCategory.MODERATE
    if reward_to_risk_ratio >= 1.0:
        return RiskCategory.HIGH
    return RiskCategory.VERY_HIGH


def size_position(
    symbol: str,
    capital: float,
    max_risk_pct_per_trade: float,
    entry_price: float,
    stop_loss: float,
    existing_portfolio_value: float = 0.0,
    existing_sector_exposure_value: float = 0.0,
    sector: str | None = None,
) -> PositionSize:
    """
    capital: total account capital.
    max_risk_pct_per_trade: user-configured max loss per trade, as a %
        of capital (e.g. 0.5 for "never risk more than 0.5% per trade").
    existing_portfolio_value / existing_sector_exposure_value: capital
        already deployed across all open positions / this sector,
        BEFORE this new position. Used to check portfolio-level limits,
        not just this trade in isolation.
    """
    if capital <= 0:
        raise ValueError("capital must be positive")
    if entry_price <= 0 or stop_loss <= 0:
        raise ValueError("entry_price and stop_loss must be positive")
    if stop_loss >= entry_price:
        raise ValueError("stop_loss must be below entry_price for a long trade")

    risk_per_share = entry_price - stop_loss
    max_risk_amount = capital * (max_risk_pct_per_trade / 100)

    quantity_by_risk = int(max_risk_amount // risk_per_share)

    max_position_value = capital * (MAX_SINGLE_POSITION_PCT_OF_CAPITAL / 100)
    quantity_by_position_cap = int(max_position_value // entry_price)

    quantity = max(0, min(quantity_by_risk, quantity_by_position_cap))
    capital_deployed = quantity * entry_price

    portfolio_exposure_after_pct = ((existing_portfolio_value + capital_deployed) / capital) * 100
    sector_exposure_after_pct = (
        ((existing_sector_exposure_value + capital_deployed) / capital) * 100
        if sector is not None
        else 0.0
    )

    violations: list[str] = []
    if quantity <= 0:
        violations.append(
            "Position size rounds to zero shares -- risk parameters too tight for available capital"
        )
    if portfolio_exposure_after_pct > MAX_PORTFOLIO_EXPOSURE_PCT:
        violations.append(
            f"Portfolio exposure would reach {portfolio_exposure_after_pct:.1f}%, "
            f"above the {MAX_PORTFOLIO_EXPOSURE_PCT}% max"
        )
    if sector is not None and sector_exposure_after_pct > MAX_SECTOR_EXPOSURE_PCT:
        violations.append(
            f"Sector ({sector}) exposure would reach {sector_exposure_after_pct:.1f}%, "
            f"above the {MAX_SECTOR_EXPOSURE_PCT}% max"
        )

    return PositionSize(
        symbol=symbol,
        max_risk_amount=round(max_risk_amount, 2),
        quantity=quantity,
        capital_deployed=round(capital_deployed, 2),
        portfolio_exposure_after_pct=round(portfolio_exposure_after_pct, 2),
        sector_exposure_after_pct=round(sector_exposure_after_pct, 2),
        within_portfolio_constraints=len(violations) == 0,
        constraint_violations=violations,
    )