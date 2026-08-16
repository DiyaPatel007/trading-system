"""
Schemas produced by the Risk Engine (Module 4). Deliberately separate
from the ML/prediction schemas -- the risk engine's output must be
computable even for a trade the ML model never scored.
"""

from pydantic import BaseModel, Field

from .enums import RiskCategory


class RiskDistribution(BaseModel):
    """
    Probability of reaching +1R/+2R/+3R before -1R. See "Multi-Level Risk
    Analysis" in the problem statement -- this is the "risk distribution
    rather than only one risk number."
    """

    prob_plus_1r: float = Field(..., ge=0.0, le=1.0)
    prob_plus_2r: float = Field(..., ge=0.0, le=1.0)
    prob_plus_3r: float = Field(..., ge=0.0, le=1.0)
    prob_minus_1r: float = Field(..., ge=0.0, le=1.0)


class RiskAssessment(BaseModel):
    """Full risk picture for one candidate trade."""

    symbol: str
    entry_price: float
    stop_loss: float
    targets: list[float]
    risk_per_share: float
    reward_to_risk_ratio: float
    expected_value_r: float = Field(
        ..., description="Expected value expressed in R multiples"
    )
    risk_category: RiskCategory
    risk_distribution: RiskDistribution
    approved: bool = Field(
        ..., description="Hard gate -- false means the risk engine vetoes this trade"
    )
    rejection_reasons: list[str] = Field(default_factory=list)


class PositionSize(BaseModel):
    """Output of position sizing given account capital and risk rules."""

    symbol: str
    max_risk_amount: float
    quantity: int
    capital_deployed: float
    portfolio_exposure_after_pct: float
    sector_exposure_after_pct: float
    within_portfolio_constraints: bool
    constraint_violations: list[str] = Field(default_factory=list)
