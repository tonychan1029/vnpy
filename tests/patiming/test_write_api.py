from vnpy_patiming.engine import PatimingEngine

from conftest import submit_ok


def _events(engine, source, iid, etype=None):
    rows = engine.db.fetch_instruction_events(source, iid)
    if etype:
        rows = [r for r in rows if r["event_type"] == etype]
    return rows


def test_create_active_and_cas(tmp_path, clock):
    eng = PatimingEngine(str(tmp_path / "db.sqlite"), clock=clock)
    r = submit_ok(eng, iid="INS-1", rev=1)
    assert r["status"] == "ACTIVE"

    stale = eng.submit_instruction("strategy:demo", {
        "instruction_id": "INS-1", "producer_revision": 1, "symbol": "rb2501.SHFE",
        "selection_timeframe": "1m", "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH", "reason_note": "x"})
    assert not stale["ok"] and stale["error"] == "stale_revision"
    assert _events(eng, "strategy:demo", "INS-1", "REJECTED")


def test_composite_key_and_scope(tmp_path, clock):
    eng = PatimingEngine(str(tmp_path / "db.sqlite"), clock=clock)
    submit_ok(eng, source="strategy:a", iid="INS-X")
    submit_ok(eng, source="strategy:b", iid="INS-X")
    assert eng.db.fetch_instruction("strategy:a", "INS-X")
    assert eng.db.fetch_instruction("strategy:b", "INS-X")

    ok = eng.revoke("strategy:b", "INS-X", 2)
    assert ok["ok"]
    eng.reconcile()
    assert eng.db.fetch_instruction("strategy:a", "INS-X")["status"] == "ACTIVE"
    assert eng.db.fetch_instruction("strategy:b", "INS-X")["status"] == "REVOKED"


def test_revoke_is_terminal(tmp_path, clock):
    eng = PatimingEngine(str(tmp_path / "db.sqlite"), clock=clock)
    submit_ok(eng, iid="INS-1")
    eng.revoke("strategy:demo", "INS-1", 2)
    eng.reconcile()
    r = eng.submit_instruction("strategy:demo", {
        "instruction_id": "INS-1", "producer_revision": 3, "symbol": "rb2501.SHFE",
        "selection_timeframe": "1m", "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH", "reason_note": "resurrect"})
    assert not r["ok"] and r["error"] == "terminal_status"


def test_invalid_row_and_revive(tmp_path, clock):
    eng = PatimingEngine(str(tmp_path / "db.sqlite"), clock=clock)
    payload = {
        "instruction_id": "INS-1", "producer_revision": 1, "symbol": "rb2501.SHFE",
        "selection_timeframe": "1m", "exec_timeframe": "1m",
        "context_tag": "not_a_context", "reason_code": "BREAKOUT_WATCH",
        "reason_note": "x",
    }
    r = eng.submit_instruction("strategy:demo", payload)
    assert r["ok"] and r["status"] == "INVALID"
    payload["context_tag"] = "breakout"
    payload["producer_revision"] = 2
    r2 = eng.submit_instruction("strategy:demo", payload)
    assert r2["ok"] and r2["status"] == "ACTIVE"
    assert eng.db.fetch_instruction("strategy:demo", "INS-1")["status"] == "ACTIVE"


def test_llm_params_locked(tmp_path, clock):
    eng = PatimingEngine(str(tmp_path / "db.sqlite"), clock=clock)
    r = eng.submit_instruction("llm:session-1", {
        "instruction_id": "INS-1", "producer_revision": 1, "symbol": "rb2501.SHFE",
        "selection_timeframe": "1m", "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH", "reason_note": "x", "params": {"atr": 99}})
    assert not r["ok"] and r["error"] == "params_locked"


def test_quota_per_source(tmp_path, clock):
    eng = PatimingEngine(str(tmp_path / "db.sqlite"),
                         {"quota_per_source": 1}, clock=clock)
    submit_ok(eng, iid="A")
    r = eng.submit_instruction("strategy:demo", {
        "instruction_id": "B", "producer_revision": 1, "symbol": "rb2501.SHFE",
        "selection_timeframe": "1m", "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH", "reason_note": "x"})
    assert not r["ok"] and r["error"] == "quota_per_source_exceeded"


def test_validity_window_validation(tmp_path, clock):
    eng = PatimingEngine(str(tmp_path / "db.sqlite"), clock=clock)
    r = eng.submit_instruction("strategy:demo", {
        "instruction_id": "INS-1", "producer_revision": 1, "symbol": "rb2501.SHFE",
        "selection_timeframe": "60m", "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH", "reason_note": "x"})
    assert r["ok"] and r["status"] == "INVALID"
    r2 = eng.submit_instruction("strategy:demo", {
        "instruction_id": "INS-2", "producer_revision": 1, "symbol": "rb2501.SHFE",
        "selection_timeframe": "5m", "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH", "reason_note": "x"})
    assert r2["ok"] and r2["status"] == "INVALID"
