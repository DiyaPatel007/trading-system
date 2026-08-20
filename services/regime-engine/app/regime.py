"""
Market Regime Engine -- pure computation, no I/O.

Classifies market conditions from an aggregate of the whole tracked
universe's price/volatility behavior, since we don't (yet) ingest the
literal NIFTY index level as its own instrument. Given per-symbol
candles across the universe for one date, and each symbol's trailing
indicators, this produces one RegimeResult for that date.

Deliberately rule-based (not ML) -- see Module 3 architecture notes.

THRESHOLDS BELOW ARE CALIBRATED AGAINST REAL DATA (NIFTY 50, ~5 years,
Aug 2026), not guessed synthetically. The first version of this file
used thresholds (trend +/-0.15, volatility 1.4/0.7) that were far
outside the real observed range of these metrics (real 10th-90th
percentile trend_score is only -0.030 to +0.046) -- that version
classified 99% of days as "sideways", which is not a usable
classification. These values are the 10th/25th/50th/75th/90th
percentiles of the actual computed inputs across 1,190 real trading
days -- re-run this calibration if the universe or feature set changes
materially, or once Module 6's ML feedback loop can tell us which
thresholds actually separate good and bad trading conditions.
"""

from dataclasses import dataclass, field
from enum import Enum


class MarketRegime(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    TRANSITIONAL = "transitional"


@dataclass
class RegimeResult:
    regime: MarketRegime
    confidence: float
    trend_score: float
    volatility_score: float
    breadth_pct_above_ema20: float
    contributing_factors: list[str] = field(default_factory=list)


# Thresholds -- calibrated against real percentiles (see module docstring).
# trend_score real range: p10=-0.030, p25=-0.008, p50=+0.013, p75=+0.033, p90=+0.046
TREND_BULLISH_THRESHOLD = 0.025   # roughly p70 -- clearly above-median trend
TREND_BEARISH_THRESHOLD = -0.015  # roughly p20 -- clearly below-median trend
TREND_SCALE_REFERENCE = 0.05      # roughly p90 -- used to normalize confidence contributions

# volatility_score real range: p10=0.887, p50=0.997, p90=1.161
HIGH_VOL_THRESHOLD = 1.15   # roughly p90
LOW_VOL_THRESHOLD = 0.90    # roughly p10

# breadth_pct_above_ema20 real range: p25=40, p50=58, p75=74
BREADTH_STRONG_THRESHOLD = 65.0  # roughly p70
BREADTH_WEAK_THRESHOLD = 45.0    # roughly p30


def compute_regime(
    trend_score: float,
    volatility_score: float,
    breadth_pct_above_ema20: float,
) -> RegimeResult:
    """
    Volatility is checked first and can override trend/breadth -- a
    high-volatility regime changes how ANY trend should be treated,
    per the problem statement's requirement that the regime engine be
    able to override strategy selection regardless of apparent trend.
    """
    result = _compute_regime_unclamped(trend_score, volatility_score, breadth_pct_above_ema20)
    result.confidence = max(0.0, min(1.0, result.confidence))
    return result


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _compute_regime_unclamped(
    trend_score: float,
    volatility_score: float,
    breadth_pct_above_ema20: float,
) -> RegimeResult:
    factors: list[str] = []

    if volatility_score >= HIGH_VOL_THRESHOLD:
        factors.append(
            f"Volatility is {volatility_score:.2f}x trailing average -- elevated"
        )
        confidence = 0.6 + _clamp((volatility_score - HIGH_VOL_THRESHOLD) / HIGH_VOL_THRESHOLD, 0, 0.4)
        return RegimeResult(
            regime=MarketRegime.HIGH_VOLATILITY,
            confidence=round(confidence, 3),
            trend_score=trend_score,
            volatility_score=volatility_score,
            breadth_pct_above_ema20=breadth_pct_above_ema20,
            contributing_factors=factors,
        )

    low_vol_flag = False
    if volatility_score <= LOW_VOL_THRESHOLD:
        factors.append(
            f"Volatility is {volatility_score:.2f}x trailing average -- unusually calm"
        )
        low_vol_flag = True

    if trend_score >= TREND_BULLISH_THRESHOLD and breadth_pct_above_ema20 >= BREADTH_STRONG_THRESHOLD:
        factors.append(f"Trend score {trend_score:+.3f} -- broadly positive")
        factors.append(f"{breadth_pct_above_ema20:.1f}% of universe above EMA20 -- strong breadth")
        confidence = (
            0.5
            + _clamp((trend_score - TREND_BULLISH_THRESHOLD) / TREND_SCALE_REFERENCE, 0, 0.3)
            + _clamp((breadth_pct_above_ema20 - BREADTH_STRONG_THRESHOLD) / 100, 0, 0.2)
        )
        return RegimeResult(
            regime=MarketRegime.BULLISH,
            confidence=round(confidence, 3),
            trend_score=trend_score,
            volatility_score=volatility_score,
            breadth_pct_above_ema20=breadth_pct_above_ema20,
            contributing_factors=factors,
        )

    if trend_score <= TREND_BEARISH_THRESHOLD and breadth_pct_above_ema20 <= BREADTH_WEAK_THRESHOLD:
        factors.append(f"Trend score {trend_score:+.3f} -- broadly negative")
        factors.append(f"Only {breadth_pct_above_ema20:.1f}% of universe above EMA20 -- weak breadth")
        confidence = (
            0.5
            + _clamp((TREND_BEARISH_THRESHOLD - trend_score) / TREND_SCALE_REFERENCE, 0, 0.3)
            + _clamp((BREADTH_WEAK_THRESHOLD - breadth_pct_above_ema20) / 100, 0, 0.2)
        )
        return RegimeResult(
            regime=MarketRegime.BEARISH,
            confidence=round(confidence, 3),
            trend_score=trend_score,
            volatility_score=volatility_score,
            breadth_pct_above_ema20=breadth_pct_above_ema20,
            contributing_factors=factors,
        )

    near_bullish = trend_score >= TREND_BULLISH_THRESHOLD * 0.5
    near_bearish = trend_score <= TREND_BEARISH_THRESHOLD * 0.5

    bullish_transition = (
        near_bullish
        and breadth_pct_above_ema20 < BREADTH_STRONG_THRESHOLD
    )

    bearish_transition = (
        near_bearish
        and breadth_pct_above_ema20 > BREADTH_WEAK_THRESHOLD
    )

    if bullish_transition or bearish_transition:
        factors.append(
            "Trend and breadth signals disagree -- possible regime change in progress"
        )
        return RegimeResult(
            regime=MarketRegime.TRANSITIONAL,
            confidence=0.4,
            trend_score=trend_score,
            volatility_score=volatility_score,
            breadth_pct_above_ema20=breadth_pct_above_ema20,
            contributing_factors=factors,
        )

    if low_vol_flag:
        confidence = 0.5 + _clamp((LOW_VOL_THRESHOLD - volatility_score) / LOW_VOL_THRESHOLD, 0, 0.4)
        return RegimeResult(
            regime=MarketRegime.LOW_VOLATILITY,
            confidence=round(confidence, 3),
            trend_score=trend_score,
            volatility_score=volatility_score,
            breadth_pct_above_ema20=breadth_pct_above_ema20,
            contributing_factors=factors,
        )

    factors.append(f"Trend score {trend_score:+.3f} and breadth {breadth_pct_above_ema20:.1f}% both near neutral")
    confidence = 0.5 + _clamp((1 - abs(trend_score) / TREND_SCALE_REFERENCE), 0, 0.3)
    return RegimeResult(
        regime=MarketRegime.SIDEWAYS,
        confidence=round(confidence, 3),
        trend_score=trend_score,
        volatility_score=volatility_score,
        breadth_pct_above_ema20=breadth_pct_above_ema20,
        contributing_factors=factors,
    )