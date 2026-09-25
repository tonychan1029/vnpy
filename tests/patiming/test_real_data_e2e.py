"""真实数据 + MCP 协议层端到端：指令写入 -> 预热 -> 真实突破 -> 触发 -> 对账。"""

import asyncio
import os

import pytest

from conftest import ManualClock, make_engine
from vnpy_patiming.adapters import AkshareOneMinuteFeed
from vnpy_patiming.audit import build_audit_report, render_markdown
from vnpy_patiming.mcp_service import build_service


VT = "rb0.SHFE"


def _real_breakout_setup(bars, lookback=20, horizon=30, buffer=0.4):
    """在真实K线里找一个真实的突破+触发事件（不构造任何价格）。"""
    for i in range(lookback + 1, len(bars) - horizon):
        level = max(b.high_price for b in bars[i - lookback : i])
        bar = bars[i]
        body = abs(bar.close_price - bar.open_price)
        rng = bar.high_price - bar.low_price
        if rng <= 0 or body < 0.605 * rng:
            continue  # 镜像 S1 的 body_ratio>=0.6 检测条件（留浮点余量）
        if bar.close_price <= bar.open_price:
            continue
        trs = []
        for a, b in zip(bars[i - 14 : i], bars[i - 13 : i + 1]):
            trs.append(max(b.high_price - b.low_price,
                           abs(b.high_price - a.close_price),
                           abs(b.low_price - a.close_price)))
        atr_est = sum(trs) / len(trs) if trs else 0.0
        if atr_est <= 0 or bar.close_price - level < 0.1 * atr_est:
            continue
        if rng > 3 * atr_est:
            continue
        trigger = bar.high_price + buffer
        for j in range(i + 1, i + 1 + horizon):
            if j < len(bars) and bars[j].close_price >= trigger:
                return i, level, j
    pytest.fail("真实数据窗口内未找到突破+触发事件，请更换品种/扩大窗口")


def test_real_mcp_e2e_breakout_to_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("PATIMING_MCP_TOKEN", "e2e-token")
    bars = AkshareOneMinuteFeed().fetch_1m("RB0", "SHFE")
    assert len(bars) >= 90, f"真实1m不足: {len(bars)}"
    arm_idx, level, trig_idx = _real_breakout_setup(bars)

    clock = ManualClock(bars[0].datetime)
    eng = make_engine(tmp_path, clock, data_mode="akshare_poll",
                      expire_bars_exec=30)
    mcp = build_service(eng)
    collector: list[dict] = []
    eng.register_delivery_handler(collector.append)

    async def call(tool: str, args: dict):
        from fastmcp import Client

        async with Client(mcp) as client:
            return await client.call_tool(tool, args)

    def tool(name: str, args: dict) -> dict:
        result = asyncio.run(call(name, args))
        data = getattr(result, "data", None)
        if data is None and getattr(result, "content", None):
            data = json_ok(result.content[0].text)
        return data

    def json_ok(text: str):
        import json

        return json.loads(text)

    base = {"symbol": VT, "selection_timeframe": "1m", "exec_timeframe": "1m"}
    bad = tool("timing_instruction_upsert", {
        "token": "wrong", "session_id": "e2e",
        "payload": {**base, "instruction_id": "X", "producer_revision": 1,
                    "reason_code": "BREAKOUT_WATCH", "reason_note": "x"}})
    assert bad["ok"] is False and bad["error"] == "unauthorized"

    r1 = tool("timing_instruction_upsert", {
        "token": "e2e-token", "session_id": "e2e",
        "payload": {**base, "instruction_id": "E2E-NATIVE",
                    "producer_revision": 1, "context_tag": "breakout",
                    "signal_categories": ["breakout"],
                    "key_levels": {"prior_high": round(level, 2)},
                    "reason_code": "BREAKOUT_WATCH", "reason_note": "e2e native"}})
    r2 = tool("timing_instruction_upsert", {
        "token": "e2e-token", "session_id": "e2e",
        "payload": {**base, "instruction_id": "E2E-SEL",
                    "producer_revision": 1, "context_tag": "breakout",
                    "signal_categories": ["breakout"],
                    "key_levels": {"support": round(level - 1.0, 2),
                                   "resistance": round(level, 2)},
                    "reason_code": "BREAKOUT_WATCH", "reason_note": "e2e selection"}})
    assert r1["ok"] and r1["status"] == "ACTIVE"
    assert r2["ok"] and r2["status"] == "ACTIVE"
    eng.reconcile()

    for bar in bars[: arm_idx + 2]:  # 多喂一根让突破K线收盘（下一根收盘规则）
        eng.on_1m_bar(bar)
    task = eng.tasks[(VT, "1m")]
    armed = [a for a in task.alerts.values()
             if a.signal_id == "BREAKOUT_KEY_LEVEL" and a.lifecycle == "ARMED"]
    assert armed, "真实突破未触发 BREAKOUT 预警"
    merged = armed[0]
    assert sorted(merged.instruction_keys) == ["llm:e2e|E2E-NATIVE", "llm:e2e|E2E-SEL"]
    assert merged.data_mode == "akshare_poll"

    for k in range(arm_idx + 1, trig_idx + 1):
        eng.on_1m_bar(bars[k])
    assert merged.lifecycle == "TRIGGERED"
    eng.deliver_pending()
    types = [e["event_type"] for e in eng.db.query(
        "SELECT event_type FROM timing_alert_event WHERE alert_id=? ORDER BY id",
        (merged.alert_id,))]
    assert types == ["signal.armed", "signal.triggered"]
    assert [e["payload"]["event_id"] for e in collector] == [merged.alert_id] * 2

    report = build_audit_report(eng.db, "llm:")
    assert len(report) == 2
    assert all(item["alert_count"] >= 1 for item in report)
    markdown = render_markdown(report)
    assert "E2E-NATIVE" in markdown and "e2e native" in markdown


def test_real_replay_labels_every_alert(tmp_path):
    from vnpy_patiming.replay import ReplayEvaluator

    bars = AkshareOneMinuteFeed().fetch_1m("RB0", "SHFE")
    assert len(bars) >= 90
    level = max(b.high_price for b in bars[:30])
    instruction = {
        "instruction_id": "REPLAY-1", "producer_revision": 1,
        "symbol": VT, "selection_timeframe": "1m", "exec_timeframe": "1m",
        "context_tag": "breakout", "signal_categories": ["breakout"],
        "key_levels": {"prior_high": round(level, 2)},
        "reason_code": "BREAKOUT_WATCH", "reason_note": "replay rolling high",
    }
    report = ReplayEvaluator(
        {"warmup_min_exec": 10, "atr_period": 5,
         "price_tick": 1.0, "buffer_ticks": 2},
        horizon=30,
    ).run(VT, "SHFE", bars, instruction)
    assert {"alerts", "summary"} <= set(report)
    valid = {"T1", "SL", "TRIGGERED_OPEN", "EXPIRED_OPEN", "INVALIDATED",
             "REPLACED", "CANCELLED"}
    for outcome in report["alerts"]:
        assert outcome["result"] in valid or outcome["lifecycle"] in valid
        assert outcome["mfe"] >= 0 and outcome["mae"] >= 0
    for bucket in report["summary"].values():
        assert bucket["win_rate"] is None or 0.0 <= bucket["win_rate"] <= 1.0
