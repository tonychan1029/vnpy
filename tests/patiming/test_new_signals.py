from datetime import timedelta

from conftest import BASE, make_bar, make_engine


def _task(eng):
    return eng.tasks[("rb2501.SHFE", "1m")]


def test_h2_trailing_update(tmp_path, clock):
    from types import SimpleNamespace

    from vnpy_patiming.config import build_config
    from vnpy_patiming.runtime import Alert, MonitoringTask
    from vnpy_patiming.signals import AlertDraft

    emitted = []
    fake_engine = SimpleNamespace(
        cfg=build_config({"price_tick": 0.2, "buffer_ticks": 2}),
        data_mode="ctp_tick",
        emit_alert=lambda task, alert, etype, lf: emitted.append(etype),
    )
    task = MonitoringTask(fake_engine, "X", "1m", "1m")
    task.atr.value = 1.0
    alert = Alert(
        alert_id="A-1", instruction_keys=["s|i"], category="h2_l2",
        signal_id="H2L2_TREND", family="h2_l2", rank=26, direction="long",
        order_type="stop", trigger={"type": "cross_above", "level": 10.0},
        stop={"level": 9.0}, invalidation={"type": "close_below", "level": 9.0},
        targets={}, context_tag="trend_channel", data_mode="ctp_tick",
        armed_bar_time=BASE, expire_bars_left=3,
    )
    task.alerts[alert.alert_id] = alert
    task.bars = [make_bar(BASE, 10, 10.5, 9.8, 10.4)]
    draft = AlertDraft(
        category="h2_l2", signal_id="H2L2_TREND", family="h2_l2", rank=26,
        order_type="stop", direction="long",
        trigger={"type": "cross_above", "level": 10.6},
        stop={"level": 9.4}, invalidation={"type": "close_below", "level": 9.4},
    )
    task._arm_or_merge(draft)
    assert alert.trigger["level"] == 10.6 and alert.stop["level"] == 9.4
    assert alert.lifecycle == "ARMED" and len(emitted) == 0
    assert len(task.alerts) == 1


def test_h2_detector_draft(tmp_path, clock):
    from types import SimpleNamespace

    from vnpy_patiming.config import build_config
    from vnpy_patiming.signals import SignalContext
    from vnpy_patiming.signals.detectors import HighTwoLowTwoDetector
    from vnpy_patiming.structures import LevelManager, Pivot, PivotDetector

    cfg = build_config({"price_tick": 0.2, "buffer_ticks": 2})
    seq = [100.0, 100.6, 101.2, 100.8, 100.4, 100.9, 101.3, 101.1, 100.6,
           100.9, 101.2, 101.4]
    bars = [make_bar(BASE + timedelta(minutes=i), c - 0.1, c + 0.4, c - 0.4, c)
            for i, c in enumerate(seq)]
    pivots = PivotDetector(2)
    pivots.confirmed = [
        Pivot("L", 100.0, bars[4].datetime, bars[6].datetime),
        Pivot("H", 101.6, bars[6].datetime, bars[8].datetime),
        Pivot("L", 100.2, bars[8].datetime, bars[10].datetime),
    ]
    ema = SimpleNamespace(value=99.9, slope=lambda lookback=5: 0.2)
    ctx = SignalContext(bars=bars, atr=1.0, ema=ema, pivots=pivots,
                        levels=LevelManager(), cfg=cfg, direction="both",
                        context_tag="trend_channel", now=bars[-1].datetime,
                        price_tick=0.2, fake_log=[])
    drafts = HighTwoLowTwoDetector().detect(ctx)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.direction == "long" and d.signal_id == "H2L2_TREND"
    assert d.stop["level"] == 100.2 and d.trigger["type"] == "cross_above"


def test_double_top_detector_draft(tmp_path, clock):
    from types import SimpleNamespace

    from vnpy_patiming.config import build_config
    from vnpy_patiming.signals import SignalContext
    from vnpy_patiming.signals.detectors import DoubleTopBottomDetector
    from vnpy_patiming.structures import LevelManager, Pivot, PivotDetector

    cfg = build_config({"price_tick": 0.2, "buffer_ticks": 2})
    seq = [104.0, 105.2, 103.8, 104.6, 105.4, 104.0, 103.6, 103.2]
    bars = [make_bar(BASE + timedelta(minutes=i), c - 0.1, c + 0.4, c - 0.4, c)
            for i, c in enumerate(seq)]
    pivots = PivotDetector(2)
    pivots.confirmed = [
        Pivot("H", 105.0, bars[1].datetime, bars[3].datetime),
        Pivot("H", 105.2, bars[4].datetime, bars[6].datetime),
    ]
    ema = SimpleNamespace(value=104.0, slope=lambda lookback=5: -0.1)
    ctx = SignalContext(bars=bars, atr=1.0, ema=ema, pivots=pivots,
                        levels=LevelManager(), cfg=cfg, direction="both",
                        context_tag="range", now=bars[-1].datetime,
                        price_tick=0.2, fake_log=[])
    drafts = DoubleTopBottomDetector().detect(ctx)
    assert len(drafts) == 1
    d = drafts[0]
    assert d.direction == "short" and d.signal_id == "DOUBLE_TOP"
    assert d.stop["level"] == 105.45  # 105.2 + 0.25 ATR
    assert d.invalidation == {"type": "close_above", "level": 105.2}
