from vnpy.trader.constant import Exchange
from vnpy.trader.object import TickData

from conftest import feed_bars, flush_window, make_bar, make_engine, submit_ok


def _tick(clock, price: float) -> TickData:
    return TickData(symbol="rb2501", exchange=Exchange.SHFE, datetime=clock(),
                    gateway_name="SIM", last_price=price)


def _armed(eng):
    task = eng.tasks[("rb2501.SHFE", "1m")]
    armed = [a for a in task.alerts.values() if a.lifecycle == "ARMED"]
    assert armed
    return armed[0]


def _setup_armed(tmp_path, clock, **kw):
    eng = make_engine(tmp_path, clock, **kw)
    submit_ok(eng, iid="INS-1", key_levels={"prior_high": 100.0})
    feed_bars(eng, clock, 10)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 99.4, 101.0, 99.0, 100.6))
    flush_window(eng, clock)
    return eng, _armed(eng)


def test_provisional_at_risk_then_restore_then_confirm(tmp_path, clock):
    eng, alert = _setup_armed(tmp_path, clock)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 100.4, 100.6, 99.5, 100.4))
    flush_window(eng, clock)
    assert alert.lifecycle == "ARMED"

    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 100.2, 100.3, 99.6, 99.7))
    flush_window(eng, clock)
    assert alert.lifecycle == "INVALIDATED"
    types = [e["event_type"] for e in eng.db.query(
        "SELECT event_type FROM timing_alert_event WHERE alert_id=? ORDER BY id",
        (alert.alert_id,))]
    assert types == ["signal.armed", "signal.invalidated"]


def test_expire_after_three_exec_closes(tmp_path, clock):
    eng, alert = _setup_armed(tmp_path, clock)
    for _ in range(3):
        dt = clock.advance(1)
        eng.on_1m_bar(make_bar(dt, 100.2, 100.4, 100.1, 100.3))
        flush_window(eng, clock)
    assert alert.lifecycle == "EXPIRED"


def test_data_pause_cancels_and_resume(tmp_path, clock):
    eng, alert = _setup_armed(tmp_path, clock)
    clock.advance(30)
    eng.reconcile()
    assert alert.lifecycle == "CANCELLED"
    assert alert.extra.get("cancel_reason") == "data_pause"
    assert eng.db.fetch_instruction("strategy:demo", "INS-1")["status"] == "PAUSED"

    feed_bars(eng, clock, 3)
    eng.reconcile()
    assert eng.db.fetch_instruction("strategy:demo", "INS-1")["status"] == "ACTIVE"


def test_poll_mode_triggers_on_1m_close(tmp_path, clock):
    eng = make_engine(tmp_path, clock, data_mode="akshare_poll")
    submit_ok(eng, iid="INS-1", key_levels={"prior_high": 100.0})
    feed_bars(eng, clock, 10)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 99.4, 100.9, 99.0, 100.6))  # arm, trigger 101.3
    flush_window(eng, clock)
    alert = _armed(eng)
    assert alert.data_mode == "akshare_poll"
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 101.0, 101.6, 100.9, 101.5))  # 1m close crosses
    assert alert.lifecycle == "TRIGGERED"


def test_outbox_order_and_retry(tmp_path, clock):
    eng, alert = _setup_armed(tmp_path, clock)
    eng.on_tick(_tick(clock, 101.5))
    assert alert.lifecycle == "TRIGGERED"

    delivered = []
    attempts = {"n": 0}

    def flaky(event):
        if attempts["n"] == 0:
            attempts["n"] += 1
            raise RuntimeError("downstream down")
        delivered.append(event["payload"]["event_id"])

    eng.register_delivery_handler(flaky)
    eng.deliver_pending()
    rows = eng.db.query("SELECT * FROM alert_outbox ORDER BY id")
    assert rows[0]["attempts"] == 1 and rows[0]["delivery_status"] == "pending"
    assert all(r["delivery_status"] == "pending" for r in rows)

    clock.advance(1)
    eng.deliver_pending()
    rows = eng.db.query("SELECT * FROM alert_outbox ORDER BY id")
    assert [r["delivery_status"] for r in rows] == ["delivered", "delivered"]
    assert delivered == [rows[0]["alert_id"], rows[1]["alert_id"]]


def test_alert_payload_schema_fields(tmp_path, clock):
    eng, alert = _setup_armed(tmp_path, clock)
    row = eng.db.query_one(
        "SELECT payload_snapshot AS payload_json FROM timing_alert_event WHERE alert_id=? AND "
        "event_type='signal.armed'", (alert.alert_id,))
    import json

    p = json.loads(row["payload_json"])["payload"]
    for field in ("event_id", "instrument", "context_tag", "signal_id", "direction",
                  "order_type", "trigger", "stop", "targets", "invalidation",
                  "lifecycle", "data_mode", "source", "instruction_ids",
                  "admission_reason", "context_snapshot"):
        assert field in p, field
    assert p["data_mode"] == "ctp_tick"
    assert p["admission_reason"]["code"] == "BREAKOUT_WATCH"
    assert p["context_snapshot"]["config_version"] == "patiming-v1.2"
