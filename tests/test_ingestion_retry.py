"""
Tests for the ingestion retry/backoff logic, using a mocked yfinance
call so no network access is needed and the test runs fast/deterministically.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "data-pipeline"))

import app.ingestion.fetch_historical as fh  # noqa: E402


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    # Don't actually sleep during tests.
    monkeypatch.setattr(fh, "BASE_BACKOFF_SECONDS", 0.01)


def _fake_df():
    idx = pd.date_range("2024-01-01", periods=3, tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [1000, 1100, 1200],
        },
        index=idx,
    )


def test_retries_on_empty_response_then_succeeds():
    call_count = {"n": 0}

    def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            return pd.DataFrame()  # simulate Yahoo blocking / empty response
        return _fake_df()

    with patch("app.ingestion.fetch_historical.yf.download", side_effect=flaky):
        candles = fh.fetch_symbol("TEST.NS", "1y", "1d")

    assert call_count["n"] == 3
    assert len(candles) == 3


def test_gives_up_after_max_retries_and_returns_empty():
    def always_empty(*args, **kwargs):
        return pd.DataFrame()

    with patch("app.ingestion.fetch_historical.yf.download", side_effect=always_empty):
        candles = fh.fetch_symbol("TEST.NS", "1y", "1d")

    assert candles == []


def test_succeeds_immediately_when_no_failure():
    call_count = {"n": 0}

    def always_ok(*args, **kwargs):
        call_count["n"] += 1
        return _fake_df()

    with patch("app.ingestion.fetch_historical.yf.download", side_effect=always_ok):
        candles = fh.fetch_symbol("TEST.NS", "1y", "1d")

    assert call_count["n"] == 1  # no retries needed
    assert len(candles) == 3