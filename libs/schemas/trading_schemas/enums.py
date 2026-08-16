"""
Shared enumerations used across every service in the trading system.

Keeping these in one place means the Market Regime Engine, Risk Engine,
ML services, Paper Trading Engine, and frontend all agree on the exact
same set of allowed values. Never redefine these locally in a service --
always import from here.
"""

from enum import Enum


class TradingMode(str, Enum):
    """The three trading horizons defined in the problem statement."""

    LONG_TERM = "long_term"
    SWING = "swing"
    INTRADAY = "intraday"


class MarketRegime(str, Enum):
    """Output categories of the Market Regime Engine (Module 3)."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    TRANSITIONAL = "transitional"


class RiskCategory(str, Enum):
    """Risk classification produced by the Risk Engine (Module 4)."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class TradeDecision(str, Enum):
    """
    The final decision surfaced to the user. Deliberately not a binary
    BUY/SELL -- see "Dynamic Trade Decision System" in the problem statement.
    """

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WAIT = "wait"
    AVOID = "avoid"
    SELL = "sell"
    NO_TRADE = "no_trade"  # used when the Market Regime Engine vetoes trading entirely


class TradeStatus(str, Enum):
    """Lifecycle state of a single trade (paper or, later, live)."""

    SIGNAL_ONLY = "signal_only"     # generated but not acted on (untaken signal)
    OPEN = "open"
    CLOSED_TARGET = "closed_target"
    CLOSED_STOP = "closed_stop"
    CLOSED_MANUAL = "closed_manual"
    CLOSED_TIME = "closed_time"     # exited due to max holding period


class ModelStage(str, Enum):
    """Model promotion states -- see Module 6 (ML training pipeline)."""

    EXPERIMENTAL = "experimental"
    CANDIDATE = "candidate"
    PRODUCTION = "production"
    REJECTED = "rejected"


class DataFreshness(str, Enum):
    """
    Every price/analysis payload must declare this, per the requirement
    that the user always knows whether they're looking at live, delayed,
    or historical data.
    """

    LIVE = "live"
    DELAYED = "delayed"
    HISTORICAL = "historical"
    PAPER_SIMULATED = "paper_simulated"
