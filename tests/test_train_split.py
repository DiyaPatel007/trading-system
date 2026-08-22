"""
Tests for train.py's chronological (walk-forward) train/test split.
Run: python -m pytest tests/test_train_split.py -v
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _helpers import use_service  # noqa: E402

use_service("ml-training")
from app.train import chronological_split  # noqa: E402


def _synthetic_dataset(n_days: int = 50) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    rows = []
    for d in dates:
        rows.append({"ts": d, "symbol": "X", "label": 1})
        rows.append({"ts": d, "symbol": "Y", "label": 0})
    return pd.DataFrame(rows)


def test_no_training_row_is_later_than_any_test_row():
    df = _synthetic_dataset()
    train, test = chronological_split(df, test_fraction=0.2)
    assert train["ts"].max() < test["ts"].min()


def test_split_respects_requested_fraction_approximately():
    df = _synthetic_dataset(n_days=100)
    train, test = chronological_split(df, test_fraction=0.2)
    actual_fraction = len(test) / len(df)
    assert abs(actual_fraction - 0.2) < 0.05


def test_all_rows_are_accounted_for():
    df = _synthetic_dataset()
    train, test = chronological_split(df, test_fraction=0.2)
    assert len(train) + len(test) == len(df)


def test_split_works_with_unsorted_input():
    df = _synthetic_dataset().sample(frac=1, random_state=1).reset_index(drop=True)
    train, test = chronological_split(df, test_fraction=0.2)
    assert train["ts"].max() < test["ts"].min()