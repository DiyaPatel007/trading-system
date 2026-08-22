"""
Tests for dataset.py's labeled dataset construction, using synthetic
candle data -- no database required.
Run: python -m pytest tests/test_dataset.py -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _helpers import use_service  # noqa: E402

use_service("ml-training")
from app.dataset import FEATURE_COLUMNS, build_labeled_dataset  # noqa: E402


def _full_features(atr: float, **overrides) -> dict:
    features = {col: (atr if col == "atr_14" else 1.0) for col in FEATURE_COLUMNS}
    features.update(overrides)
    return features


def _make_df(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": "X", "ts": ts, "high": h, "low": l, "close": c, "features": _full_features(atr)}
            for ts, h, l, c, atr in rows
        ]
    )


def test_no_lookahead_bias_signal_day_never_resolves_against_own_bar():
    """
    The single most important correctness property of this module: a
    signal generated on day 0 must NEVER be labeled using day 0's own
    high/low, even though day 0's bar is technically available in the
    data. Day 0 here has a huge high (999) that would trivially "hit
    target" if the code incorrectly included the signal day itself --
    the correct label instead comes from day 3's genuine target hit.
    """
    rows = [
        ("2024-01-01", 999, 1, 100, 2.0),
        ("2024-01-02", 102, 98, 100, 2.0),
        ("2024-01-03", 103, 98, 100, 2.0),
        ("2024-01-04", 112, 100, 105, 2.0),
        ("2024-01-05", 102, 98, 100, 2.0),
    ]
    df = _make_df(rows)
    result = build_labeled_dataset(df)

    day0_label = result[result["ts"] == "2024-01-01"]["label"].iloc[0]
    assert day0_label == 1


def test_rows_with_missing_features_are_dropped():
    """
    Every row here resolves quickly (next day's low breaches stop), so
    a fully-empty result would NOT prove the feature-completeness check
    works -- it could just mean nothing resolved. Only day 0's features
    are corrupted; every other day must still appear in the result.
    """
    rows = [(f"2024-01-{i:02d}", 102, 90, 100, 2.0) for i in range(1, 6)]
    df = _make_df(rows)
    df.at[0, "features"] = {"atr_14": 2.0}

    result = build_labeled_dataset(df)
    assert len(result) > 0, "test setup issue -- expected some rows to resolve"
    assert "2024-01-01" not in result["ts"].values
    assert "2024-01-02" in result["ts"].values


def test_zero_or_missing_atr_rows_are_skipped():
    rows = [(f"2024-01-{i:02d}", 102, 90, 100, 2.0) for i in range(1, 6)]
    df = _make_df(rows)
    df.at[0, "features"] = _full_features(0.0)

    result = build_labeled_dataset(df)
    assert len(result) > 0, "test setup issue -- expected some rows to resolve"
    assert "2024-01-01" not in result["ts"].values
    assert "2024-01-02" in result["ts"].values


def test_unresolved_trades_near_end_of_data_are_dropped():
    rows = [(f"2024-01-{i:02d}", 102, 98, 100, 2.0) for i in range(1, 4)]
    df = _make_df(rows)
    result = build_labeled_dataset(df)
    assert len(result) == 0


def test_multiple_symbols_are_processed_independently():
    rows_x = [
        ("2024-01-01", 102, 98, 100, 2.0),
        ("2024-01-02", 112, 100, 105, 2.0),
    ]
    rows_y = [
        ("2024-01-01", 102, 98, 100, 2.0),
        ("2024-01-02", 103, 94, 100, 2.0),
    ]
    df = pd.concat(
        [
            pd.DataFrame([{"symbol": "X", "ts": t, "high": h, "low": l, "close": c, "features": _full_features(a)} for t, h, l, c, a in rows_x]),
            pd.DataFrame([{"symbol": "Y", "ts": t, "high": h, "low": l, "close": c, "features": _full_features(a)} for t, h, l, c, a in rows_y]),
        ],
        ignore_index=True,
    )
    result = build_labeled_dataset(df)
    x_label = result[(result["symbol"] == "X") & (result["ts"] == "2024-01-01")]["label"]
    y_label = result[(result["symbol"] == "Y") & (result["ts"] == "2024-01-01")]["label"]
    assert len(x_label) == 1 and x_label.iloc[0] == 1
    assert len(y_label) == 1 and y_label.iloc[0] == 0