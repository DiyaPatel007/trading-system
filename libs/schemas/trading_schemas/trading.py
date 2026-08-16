"""
Schemas for signals and trades -- the objects that flow through the
Scanner (Module 5), Paper Trading Engine (Module 7), and Journal (Module 9).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .enums import ModelStage, TradeDecision, TradeStatus, TradingMode
from .risk import PositionSize, RiskAssessment


class SignalReasoning(BaseModel):
    """
    Structured explanation for a decision. The LLM/orchestration layer
    (Module 8, MCP) turns this into natural language -- it does NOT
    invent these reasons itself.
    """

    technical_factors: list[str] = Field(default_factory=list)
    fundamental_factors: list[str] = Field(default_factory=list)
    sentiment_factors: list[str] = Field(default_factory=list)
    market_factors: list[str] = Field(default_factory=list)
    ml_factors: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    invalidation_factors: list[str] = Field(
        default_factory=list,
        description="What would invalidate this trade thesis",
    )


class Signal(BaseModel):
    """
    A single generated recommendation. Every signal is recorded, whether
    or not the user acts on it -- see "Learning From Both Taken and
    Untaken Signals" in the problem statement.
    """

    signal_id: str
    symbol: str
    mode: TradingMode
    generated_at: datetime
    decision: TradeDecision
    ml_probability: Optional[float] = Field(None, ge=0.0, le=1.0)
    model_version: Optional[str] = None
    model_stage: Optional[ModelStage] = None
    risk_assessment: Optional[RiskAssessment] = None
    position_size: Optional[PositionSize] = None
    reasoning: SignalReasoning = Field(default_factory=SignalReasoning)
    taken_by_user: bool = False


class Trade(BaseModel):
    """Full lifecycle record of a trade, paper or live."""

    trade_id: str
    signal_id: str
    symbol: str
    mode: TradingMode
    status: TradeStatus
    predicted_entry: float
    actual_entry: Optional[float] = None
    stop_loss: float
    targets: list[float]
    quantity: int
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    max_favorable_excursion: Optional[float] = None
    max_adverse_excursion: Optional[float] = None
    model_version: Optional[str] = None
    is_paper: bool = True
