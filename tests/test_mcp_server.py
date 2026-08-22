"""
Tests for the MCP server -- confirms tools register correctly and that
the risk-engine-wrapping tools produce results consistent with Module
4's own hand-verified tests (i.e. the MCP layer is a thin, faithful
adapter, not a re-implementation).

Run: python -m pytest tests/test_mcp_server.py -v

Requires mcp==1.29.0 (pinned <2, see services/mcp-server/README note on
the SDK's own v2 stability guidance).
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _helpers import use_service, SERVICES_DIR  # noqa: E402

_risk_engine_src = SERVICES_DIR / "risk-engine" / "app" / "risk.py"
_risk_engine_dst = SERVICES_DIR / "mcp-server" / "app" / "risk_engine.py"
shutil.copy(_risk_engine_src, _risk_engine_dst)

use_service("mcp-server")
import asyncio  # noqa: E402

from app.server import calculate_risk, mcp, size_position  # noqa: E402


def test_server_starts_and_registers_all_expected_tools():
    async def list_tool_names():
        tools = await mcp.list_tools()
        return {t.name for t in tools}

    tool_names = asyncio.run(list_tool_names())
    expected = {
        "get_market_regime", "get_scanner_results", "calculate_risk", "size_position",
        "get_open_paper_trades", "get_paper_trading_performance", "get_model_registry",
        "get_recent_candles",
    }
    assert expected.issubset(tool_names)


def test_calculate_risk_tool_matches_module4_hand_verified_case():
    result = calculate_risk("TEST.NS", entry_price=100, stop_loss=98, target=106)
    assert result["reward_to_risk_ratio"] == 3.0
    assert result["approved"] is True
    assert result["risk_category"] == "low"


def test_calculate_risk_tool_rejects_oversized_stop_same_as_module4():
    result = calculate_risk("TEST.NS", entry_price=100, stop_loss=95, target=115)
    assert result["reward_to_risk_ratio"] == 3.0
    assert result["approved"] is False
    assert any("Risk per share" in r for r in result["rejection_reasons"])


def test_size_position_tool_matches_module4_hand_verified_case():
    result = size_position("TEST.NS", capital=100_000, entry_price=100, stop_loss=98)
    assert result["quantity"] == 100
    assert result["capital_deployed"] == 10_000.0
    assert result["within_portfolio_constraints"] is True


def test_size_position_tool_detects_portfolio_exposure_violation():
    result = size_position(
        "TEST.NS", capital=100_000, entry_price=100, stop_loss=98,
        existing_portfolio_value=75_000,
    )
    assert result["within_portfolio_constraints"] is False
    assert any("Portfolio exposure" in v for v in result["constraint_violations"])