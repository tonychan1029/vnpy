import json

from conftest import BASE, make_engine, submit_ok
from vnpy_patiming.runtime import Alert


def _task(eng):
    return eng.tasks[("rb2501.SHFE", "1m")]


def _mk_alert(eng, task, i, trigger=101.0, direction="long"):
    alert = Alert(
        alert_id=f"TIM-X-{i:04d}", instruction_keys=[f"s|I-{i}"],
        category="breakout", signal_id="BREAKOUT_KEY_LEVEL", family="breakout",
        rank=30, direction=direction, order_type="stop",
        trigger={"type": "cross_above", "level": trigger},
        stop={"level": trigger - 1.0},
        invalidation={"type": "close_below", "level": trigger - 2.0},
        targets={}, context_tag="breakout", data_mode="ctp_tick",
        armed_bar_time=BASE, expire_bars_left=3,
    )
    task.alerts[alert.alert_id] = alert
    return alert


def test_summary_best_per_direction_and_expiring(tmp_path, clock):
    eng = make_engine(tmp_path, clock)
    submit_ok(eng, iid="S-1", key_levels={"prior_high": 100.0}, valid_bars=6)
    submit_ok(eng, iid="S-2", key_levels={"prior_high": 101.0})
    feed_warm_and_arm(eng, clock)
    _mk_alert(eng, _task(eng), 1, trigger=100.5)
    _mk_alert(eng, _task(eng), 2, trigger=101.5)
    eng.reconcile()

    rows = eng.db.query(
        "SELECT payload_json FROM alert_outbox WHERE event_type='signal.summary'")
    assert len(rows) == 1
    payload = json.loads(rows[0]["payload_json"])["payload"]
    longs = [i for i in payload["items"] if i["direction"] == "long"]
    assert len(longs) == 1  # 决策 D1：每标的×方向只保留最佳机会
    assert any(e["instruction_id"] == "S-1"
               for e in payload["expiring_instructions"])  # 决策 D3

    eng.reconcile()
    rows = eng.db.query(
        "SELECT payload_json FROM alert_outbox WHERE event_type='signal.summary'")
    assert len(rows) == 1  # 无变化不重发


def feed_warm_and_arm(eng, clock):
    from conftest import feed_bars, make_bar, flush_window

    feed_bars(eng, clock, 10)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 99.4, 101.0, 99.0, 100.8))
    flush_window(eng, clock)


def test_multi_tf_confirmed_flag(tmp_path, clock):
    eng = make_engine(tmp_path, clock)
    submit_ok(eng, iid="M-1", exec_timeframe="1m",
              key_levels={"prior_high": 100.0})
    submit_ok(eng, iid="M-2", exec_timeframe="5m",
              key_levels={"prior_high": 100.0})
    _mk_alert(eng, _task(eng), 1, trigger=101.0)
    _mk_alert(eng, eng.tasks[("rb2501.SHFE", "5m")], 2, trigger=101.2)
    payload = eng._alert_payload(
        _task(eng), eng.tasks[("rb2501.SHFE", "1m")].alerts["TIM-X-0001"],
        "signal.armed")["payload"]
    assert payload["multi_tf_confirmed"] is True  # 决策 D2
    assert payload["confidence"] > 0.05


def test_replay_mode_forbids_scheduler(tmp_path, clock):
    import pytest

    from vnpy_patiming.engine import PatimingEngine

    eng = PatimingEngine(str(tmp_path / "db.sqlite"),
                         {"warmup_min_exec": 4}, clock=clock,
                         run_mode="REPLAY")
    with pytest.raises(RuntimeError):
        eng.start()
    assert not eng._running
