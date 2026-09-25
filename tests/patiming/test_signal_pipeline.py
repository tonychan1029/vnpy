from vnpy.trader.constant import Exchange
from vnpy.trader.object import TickData

from conftest import BASE, feed_bars, flush_window, make_bar, make_engine, submit_ok


def _engine(tmp_path, clock, **kw):
    return make_engine(tmp_path, clock, **kw)


def _tick(clock, price: float) -> TickData:
    return TickData(symbol="rb2501", exchange=Exchange.SHFE, datetime=clock(),
                    gateway_name="SIM", last_price=price)


def _warm(eng, clock, n=10):
    submit_ok(eng, iid="INS-1", key_levels={"prior_high": 100.0})
    feed_bars(eng, clock, n)


def _armed(eng, signal_id):
    task = eng.tasks[("rb2501.SHFE", "1m")]
    return [a for a in task.alerts.values()
            if a.signal_id == signal_id and a.lifecycle == "ARMED"]


def test_s1_breakout_arm_trigger_targets(tmp_path, clock):
    eng = _engine(tmp_path, clock)
    _warm(eng, clock)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 99.4, 101.0, 99.0, 100.6))
    flush_window(eng, clock)
    alerts = _armed(eng, "BREAKOUT_KEY_LEVEL")
    assert len(alerts) == 1
    a = alerts[0]
    assert a.direction == "long"
    assert a.trigger["ref"] == "signal_bar_high"
    assert a.trigger["level"] == 101.4  # signal high 101.0 + 2 ticks * 0.2
    assert a.stop["ref"] == "key_level_offset"
    risk = abs(a.trigger["level"] - a.stop["level"])
    assert a.targets["t1"]["ref"] == "risk_multiple:1.0R"
    assert a.targets["t2"]["price"] == round(a.trigger["level"] + 2 * risk, 6)

    eng.on_tick(_tick(clock, 101.5))
    assert a.lifecycle == "TRIGGERED"
    rows = eng.db.query(
        "SELECT event_type FROM timing_alert_event WHERE alert_id=? ORDER BY id",
        (a.alert_id,))
    assert [r["event_type"] for r in rows] == ["signal.armed", "signal.triggered"]


def test_s2_fake_and_s3_second_breakout(tmp_path, clock):
    eng = _engine(tmp_path, clock)
    submit_ok(eng, iid="INS-1",
              signal_categories=["fake_breakout", "second_breakout"],
              key_levels={"prior_high": 100.0})
    feed_bars(eng, clock, 10)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 99.8, 100.6, 99.4, 99.6))
    flush_window(eng, clock)
    assert len(_armed(eng, "FAKE_BREAKOUT_REVERSE")) == 1
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 99.8, 101.0, 99.6, 100.7))
    flush_window(eng, clock)
    assert len(_armed(eng, "SECOND_BREAKOUT")) == 1


def test_s4_ema_pullback_detector_and_max_stop(tmp_path, clock):
    from types import SimpleNamespace
    from datetime import timedelta

    from vnpy_patiming.config import build_config
    from vnpy_patiming.signals import SignalContext
    from vnpy_patiming.signals.detectors import EmaPullbackDetector
    from vnpy_patiming.structures import LevelManager, Pivot, PivotDetector

    cfg = build_config({"price_tick": 0.2, "buffer_ticks": 2})
    seq = [99.0, 99.4, 99.9, 100.4, 100.9, 101.3, 101.6,
           101.2, 101.0, 100.2, 100.5, 100.9, 101.0]
    bars = [make_bar(BASE + timedelta(minutes=i), c - 0.1, c + 0.4, c - 0.4, c)
            for i, c in enumerate(seq)]
    pivots = PivotDetector(2)
    pivots.confirmed.append(Pivot("L", 99.8, bars[9].datetime, bars[11].datetime))
    ema = SimpleNamespace(value=100.9, slope=lambda lookback=5: 0.3)
    levels = LevelManager()

    def ctx(max_stop_atr: float) -> SignalContext:
        cfg2 = dict(cfg, max_stop_atr=max_stop_atr)
        return SignalContext(bars=bars, atr=1.0, ema=ema, pivots=pivots,
                             levels=levels, cfg=cfg2, direction="both",
                             context_tag="trend_strong", now=bars[-1].datetime,
                             price_tick=0.2, fake_log=[])

    drafts = EmaPullbackDetector().detect(ctx(50.0))
    assert len(drafts) == 1
    d = drafts[0]
    assert d.direction == "long" and d.order_type == "limit"
    assert d.trigger["ref"] == "ema_frozen"
    assert d.trigger["level"] == 100.5  # ema 100.9 - 2 ticks * 0.2
    assert d.stop == {"level": 99.55, "ref": "pivot_point"}  # 99.8 - 0.25 ATR

    # 止损结构过远（> max_stop_atr * ATR）-> 拒绝出预案（spec 6.4）
    pivots.confirmed[0].price = 96.0
    assert EmaPullbackDetector().detect(ctx(2.0)) == []


def test_s10_range_edge_pin(tmp_path, clock):
    eng = _engine(tmp_path, clock)
    submit_ok(eng, iid="INS-1", context_tag="range",
              signal_categories=["range_edge"],
              key_levels={"range_top": 105.0, "range_bottom": 98.0})
    feed_bars(eng, clock, 10)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 98.6, 98.9, 97.8, 98.8))
    flush_window(eng, clock)
    armed = _armed(eng, "RANGE_EDGE_REVERSAL")
    assert len(armed) == 1 and armed[0].direction == "long"


def test_s5_gap_edge_pullback(tmp_path, clock):
    eng = _engine(tmp_path, clock)
    submit_ok(eng, iid="INS-1", signal_categories=["structure_pullback"],
              key_levels={})
    feed_bars(eng, clock, 10)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 100.2, 100.5, 100.0, 100.3))  # gap up over 99.6
    for _ in range(6):
        dt = clock.advance(1)
        eng.on_1m_bar(make_bar(dt, 100.2, 100.4, 99.9, 100.3))
    task = eng.tasks[("rb2501.SHFE", "1m")]
    edge = [lv for lv in task.levels.levels if lv.kind == "gap_edge"][0]
    assert edge.status == "tested"
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 100.0, 100.2, 99.6, 99.9))
    flush_window(eng, clock)
    armed = _armed(eng, "STRUCTURE_PULLBACK")
    assert len(armed) == 1 and armed[0].direction == "long"


def test_two_sources_merge_into_one_alert(tmp_path, clock):
    eng = _engine(tmp_path, clock)
    submit_ok(eng, source="strategy:a", iid="INS-A",
              key_levels={"prior_high": 100.0})
    submit_ok(eng, source="strategy:b", iid="INS-B",
              key_levels={"prior_high": 100.0})
    feed_bars(eng, clock, 10)
    dt = clock.advance(1)
    eng.on_1m_bar(make_bar(dt, 99.4, 101.0, 99.0, 100.6))
    flush_window(eng, clock)
    armed = _armed(eng, "BREAKOUT_KEY_LEVEL")
    assert len(armed) == 1
    assert sorted(armed[0].instruction_keys) == ["strategy:a|INS-A", "strategy:b|INS-B"]
