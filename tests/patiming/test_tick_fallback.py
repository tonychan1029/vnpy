from conftest import feed_bars, make_engine, submit_ok


def test_stale_switches_to_tick_fallback_hook(tmp_path, clock):
    eng = make_engine(tmp_path, clock)
    calls = []
    eng.tick_fallback_hooks.append(calls.append)
    submit_ok(eng, iid="INS-1", key_levels={})
    clock.advance(30)
    eng.reconcile()
    assert calls == ["rb2501.SHFE"]
    task = eng.tasks[("rb2501.SHFE", "1m")]
    assert task.data_mode == "tick_fallback"
    row = eng.db.fetch_instruction("strategy:demo", "INS-1")
    assert row["status"] == "PAUSED"
    assert "TICK_FALLBACK" in (row["feedback"] or "")
