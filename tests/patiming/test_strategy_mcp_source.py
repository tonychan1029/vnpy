import asyncio

from fastmcp import Client

from conftest import ManualClock, make_engine
from vnpy_patiming.mcp_service import build_service


def test_strategy_token_writes_active_strategy_source(tmp_path, monkeypatch):
    monkeypatch.setenv("PATIMING_MCP_TOKEN", "main-token")
    monkeypatch.setenv("PATIMING_STRATEGY_MCP_TOKEN", "strategy-token")
    clock = ManualClock()
    engine = make_engine(tmp_path, clock, require_approval=True)
    mcp = build_service(engine)

    async def runner():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "strategy_selection_upsert",
                {
                    "token": "strategy-token",
                    "payload": {
                        "instruction_id": "SEL-1",
                        "producer_revision": 1,
                        "symbol": "rb0.SHFE",
                        "selection_timeframe": "60m",
                        "exec_timeframe": "60m",
                        "reason_code": "TREND_FOLLOW",
                        "reason_note": "strategy source",
                    },
                },
            )
            assert result.data["ok"] is True
            assert result.data["status"] == "ACTIVE"

            query = await client.call_tool(
                "strategy_selection_query",
                {"token": "strategy-token", "instruction_id": "SEL-1"},
            )
            assert query.data["instruction"]["source"] == "strategy:hourly-selection"

    asyncio.run(runner())


def test_llm_token_cannot_write_strategy_source(tmp_path, monkeypatch):
    monkeypatch.setenv("PATIMING_MCP_TOKEN", "main-token")
    monkeypatch.setenv("PATIMING_STRATEGY_MCP_TOKEN", "strategy-token")
    clock = ManualClock()
    engine = make_engine(tmp_path, clock, require_approval=True)
    mcp = build_service(engine)

    async def runner():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "strategy_selection_upsert",
                {
                    "token": "main-token",
                    "payload": {
                        "instruction_id": "SPOOF",
                        "producer_revision": 1,
                        "symbol": "rb0.SHFE",
                        "selection_timeframe": "60m",
                        "exec_timeframe": "60m",
                        "reason_code": "TREND_FOLLOW",
                        "reason_note": "spoof attempt",
                    },
                },
            )
            assert result.data["ok"] is False
            assert result.data["error"] == "unauthorized"

        assert engine.db.fetch_instruction(
            "strategy:hourly-selection", "SPOOF"
        ) is None

    asyncio.run(runner())
