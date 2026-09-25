from conftest import feed_bars, submit_ok

from vnpy_patiming.engine import PatimingEngine


def test_warmup_then_anchor_then_countdown(tmp_path, clock):
    from conftest import make_engine

    eng = make_engine(tmp_path, clock)
    submit_ok(eng, iid="INS-1")
    row = eng.db.fetch_instruction("strategy:demo", "INS-1")
    assert row["remaining_bars"] is None

    feed_bars(eng, clock, 9)  # warmup 8 closes + anchor on the 9th 1m close
    row = eng.db.fetch_instruction("strategy:demo", "INS-1")
    assert row["status"] == "ACTIVE" and row["remaining_bars"] == 12
    assert row["anchor_bar"] is not None and row["effective_from"] is not None

    feed_bars(eng, clock, 2)
    row = eng.db.fetch_instruction("strategy:demo", "INS-1")
    assert row["remaining_bars"] == 10


def test_expiry_cancels_alerts(tmp_path, clock):
    from conftest import make_engine

    eng = make_engine(tmp_path, clock)
    submit_ok(eng, iid="INS-1", valid_bars=4)
    feed_bars(eng, clock, 9)   # anchor
    feed_bars(eng, clock, 5)   # 4 decrements -> EXPIRED
    row = eng.db.fetch_instruction("strategy:demo", "INS-1")
    assert row["status"] == "EXPIRED"
    types = [e["event_type"] for e in eng.db.fetch_instruction_events(
        "strategy:demo", "INS-1")]
    assert "STATUS_CHANGED" in types


def test_wall_clock_valid_until(tmp_path, clock):
    eng = PatimingEngine(str(tmp_path / "db.sqlite"), clock=clock)
    submit_ok(eng, iid="INS-1", valid_until="2026-09-21T09:30:00")
    clock.advance(45)
    eng.reconcile()
    assert eng.db.fetch_instruction("strategy:demo", "INS-1")["status"] == "EXPIRED"


def test_restart_recovery_persists_countdown(tmp_path, clock):
    from conftest import make_engine

    eng = make_engine(tmp_path, clock)
    db = eng.db.path
    submit_ok(eng, iid="INS-1")
    feed_bars(eng, clock, 10)  # anchor + 1 decrement
    row = eng.db.fetch_instruction("strategy:demo", "INS-1")
    assert row["remaining_bars"] == 11
    eng.close()

    eng2 = PatimingEngine(db, clock=clock)
    eng2.reconcile()
    feed_bars(eng2, clock, 3)
    row2 = eng2.db.fetch_instruction("strategy:demo", "INS-1")
    assert row2["remaining_bars"] == 9
    eng2.close()
