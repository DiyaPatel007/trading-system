"""
Schemas for raw and derived market data. These are produced by the
Market Data Service (Module 2) and consumed by nearly every other service.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import DataFreshness, MarketRegime


class Candle(BaseModel):
    """One OHLCV bar for a symbol at a given timeframe."""

    symbol: str = Field(..., description="Exchange symbol, e.g. 'RELIANCE.NS'")
    timeframe: str = Field(..., description="'1m', '5m', '15m', '1d', etc.")
    timestamp: datetime = Field(..., description="Bar open time, UTC")
    open: float
    high: float
    low: float
    close: float
    volume: int
    freshness: DataFreshness = DataFreshness.HISTORICAL

    @field_validator("volume")
    @classmethod
    def volume_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("volume cannot be negative")
        return v

    @model_validator(mode="after")
    def ohlc_consistency(self) -> "Candle":
        # Runs after all fields are populated, so field order no longer matters.
        if self.high < self.low:
            raise ValueError("high cannot be less than low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be >= open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be <= open and close")
        return self


class MarketContext(BaseModel):
    """
    Broader market conditions attached to every stock-level analysis, so
    signals are never interpreted in isolation from the index/sector.
    """

    as_of: datetime
    nifty_change_pct: float
    banknifty_change_pct: float
    market_breadth_advance_decline_ratio: float
    regime: MarketRegime
    regime_confidence: float = Field(..., ge=0.0, le=1.0)
    sector_strength: dict[str, float] = Field(
        default_factory=dict,
        description="Sector name -> relative strength score",
    )


class FeatureVector(BaseModel):
    """
    Computed features for one symbol at one timestamp, mode-specific.
    This is what gets fed into ML inference (Module 6).
    """

    symbol: str
    timeframe: str
    timestamp: datetime
    feature_set_version: str
    features: dict[str, Optional[float]] = Field(
        default_factory=dict,
        description="Feature name -> value; None allowed for missing fundamentals etc.",
    )
