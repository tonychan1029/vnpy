from datetime import datetime

from conftest import ManualClock, feed_bars, flush_window, make_bar, \
    make_engine, submit_ok
from vnpy_patiming.mcp_service import _warmup_live_tasks


def test_selection_key_levels_mapping(tmp_path, clock):
    eng = make_engine(tmp_path, clock)
    r = submit_ok(eng, iid="SEL-1",
                  key_levels={"support": 99.0, "resistance": 101.0,
                              "swing_points": [100.5]})
    assert r["ok"]
    task = eng.tasks[("rb2501.SHFE", "1m")]
    kinds = {lv.kind: lv.price for lv in task.levels.levels}
    assert kinds["prior_low"] == 99.0 and kinds["prior_high"] == 101.0
    assert "support" not in kinds and "resistance" not in kinds


def test_key_levels_out_of_band(tmp_path, clock):
    eng = make_engine(tmp_path, clock)
    submit_ok(eng, iid="WARM-1", key_levels={})
    feed_bars(eng, clock, 3)  # last price ~99.2
    r = eng.submit_instruction("strategy:demo", {
        "instruction_id": "FAR-1", "producer_revision": 1,
        "symbol": "rb2501.SHFE", "selection_timeframe": "1m",
        "exec_timeframe": "1m", "context_tag": "breakout",
        "key_levels": {"prior_high": 150.0},
        "reason_code": "BREAKOUT_WATCH", "reason_note": "far level"})
    assert r["ok"] and r["status"] == "INVALID"


def test_rate_limit(tmp_path, clock):
    eng = make_engine(tmp_path, clock, request_min_interval_s=60)
    submit_ok(eng, iid="A-1")
    r = eng.submit_instruction("strategy:demo", {
        "instruction_id": "B-1", "producer_revision": 1,
        "symbol": "rb2501.SHFE", "selection_timeframe": "1m",
        "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH", "reason_note": "second"})
    assert not r["ok"] and r["error"] == "rate_limited"
    clock.advance(61)
    r2 = eng.submit_instruction("strategy:demo", {
        "instruction_id": "B-1", "producer_revision": 2,
        "symbol": "rb2501.SHFE", "selection_timeframe": "1m",
        "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH", "reason_note": "after window"})
    assert r2["ok"]


def test_confidence_rule_scored(tmp_path, clock):
    import json

    eng = make_engine(tmp_path, clock)
    submit_ok(eng, iid="INS-1", key_levels={"prior_high": 100.0})
    feed_bars(eng, clock, 10)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 99.4, 101.0, 99.0, 100.8))
    flush_window(eng, clock)
    task = eng.tasks[("rb2501.SHFE", "1m")]
    alert = next(a for a in task.alerts.values()
                 if a.signal_id == "BREAKOUT_KEY_LEVEL")
    payload = eng.db.query_one(
        "SELECT payload_snapshot FROM timing_alert_event WHERE alert_id=? AND "
        "event_type='signal.armed'", (alert.alert_id,))
    conf = json.loads(payload["payload_snapshot"])["payload"]["confidence"]
    assert isinstance(conf, float) and 0.05 <= conf <= 0.95


def test_expires_bar_refreshes_with_countdown(tmp_path, clock):
    eng = make_engine(tmp_path, clock)
    submit_ok(eng, iid="INS-1")
    feed_bars(eng, clock, 9)
    row = eng.db.fetch_instruction("strategy:demo", "INS-1")
    assert row["remaining_bars"] == 12 and row["expires_bar"]
    first = row["expires_bar"]
    feed_bars(eng, clock, 2)
    row = eng.db.fetch_instruction("strategy:demo", "INS-1")
    assert row["remaining_bars"] == 10
    # 纯倒计时下的不变量：估算值 = 锚点 open + valid_bars（随基值同步移动）
    assert row["expires_bar"] == first


def test_live_startup_warmup_excludes_incomplete_snapshot(tmp_path):
    class Feed:
        def fetch_1m(self, symbol: str, exchange: str):
            assert (symbol, exchange) == ("rb0", "SHFE")
            return [
                make_bar(dt, 99.0, 99.6, 98.6, 99.2, symbol=symbol)
                for dt in (
                    datetime(2026, 9, 28, 9, 0),
                    datetime(2026, 9, 28, 9, 1),
                    datetime(2026, 9, 28, 9, 2),
                )
            ]

    clock = ManualClock(datetime(2026, 9, 28, 9, 2))
    eng = make_engine(tmp_path, clock, data_mode="akshare_poll",
                      warmup_min_exec=2, atr_period=1, ema_period=1)
    submit_ok(eng, iid="WARMUP-1", symbol="rb0.SHFE")
    counts = _warmup_live_tasks(eng, Feed())

    assert counts == {"rb0.SHFE": 2}
    assert eng.tasks[("rb0.SHFE", "1m")].ready is True
