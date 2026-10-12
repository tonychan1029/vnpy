"""HO002：H1/L1（M-PT-004）与 W/M（M-PT-005）detector 单测（RS004 判据逐条）。"""

from datetime import timedelta
from types import SimpleNamespace

from conftest import BASE, make_bar

from vnpy_patiming.config import build_config
from vnpy_patiming.signals import SignalContext
from vnpy_patiming.signals.detectors import (
    DoubleTopBottomDetector,
    PullbackOrdinalDetector,
    WmDetector,
    build_detectors,
)
from vnpy_patiming.structures import LevelManager, Pivot, PivotDetector


def _bars(n: int, closes=None):
    closes = closes or [100.0 + (i % 3) * 0.3 for i in range(n)]
    return [make_bar(BASE + timedelta(minutes=i), c - 0.1, c + 0.4, c - 0.4, c)
            for i, c in enumerate(closes)]


def _ctx(cfg, bars, pivots, ema_value, slope, context_tag, atr=1.0):
    return SignalContext(
        bars=bars, atr=atr, ema=SimpleNamespace(value=ema_value, slope=lambda lookback=5: slope),
        pivots=pivots, levels=LevelManager(), cfg=cfg, direction="both",
        context_tag=context_tag, now=bars[-1].datetime, price_tick=0.2, fake_log=[],
    )


def _pivots(pv):
    p = PivotDetector(2)
    p.confirmed = pv
    return p


# ---------------------------------------------------------------- H1/L1

def _h1_setup(extra_cfg=None, n_bars=40):
    """Happy path：H0(6) -> 前低(2) 远离 -> L1(30) -> H_mid(36) -> 确认K(39)。"""
    cfg = build_config({"price_tick": 0.2, "buffer_ticks": 2,
                        "enable_h1_l1": True, **(extra_cfg or {})})
    bars = _bars(n_bars)
    bars[-1] = make_bar(bars[-1].datetime, 100.6, 101.4, 100.5, 101.0)
    pv = [
        Pivot("L", 99.0, bars[2].datetime, bars[4].datetime),
        Pivot("H", 101.0, bars[6].datetime, bars[8].datetime),    # H0
        Pivot("L", 99.6, bars[30].datetime, bars[32].datetime),   # L1 首次回调
        Pivot("H", 100.4, bars[36].datetime, bars[38].datetime),  # H_mid
    ]
    return cfg, bars, _pivots(pv)


def test_h1_long_happy_path():
    cfg, bars, pivots = _h1_setup()
    drafts = PullbackOrdinalDetector().detect(_ctx(cfg, bars, pivots, 100.0, 0.2, "trend_channel"))
    assert len(drafts) == 1
    d = drafts[0]
    assert d.category == "h1_l1" and d.signal_id == "H1_L1_TREND"
    assert d.direction == "long" and d.trigger["type"] == "cross_above"
    assert d.trigger["level"] == 101.8          # 信号K高点 101.4 + 2tick(0.4)
    assert d.stop["level"] == 99.35             # L1 99.6 - 0.25 ATR
    assert d.invalidation == {"type": "close_below", "level": 99.6}


def test_h1_blocked_not_first_pullback():
    cfg, bars, pivots = _h1_setup()
    pv = pivots.confirmed
    pv[0] = Pivot("L", 99.0, bars[20].datetime, bars[22].datetime)  # 前低距 L1 仅 10 根 <= lookback
    drafts = PullbackOrdinalDetector().detect(_ctx(cfg, bars, _pivots(pv), 100.0, 0.2, "trend_channel"))
    assert drafts == []


def test_h1_blocked_deep_pullback():
    cfg, bars, pivots = _h1_setup()
    pv = pivots.confirmed
    pv[0] = Pivot("L", 98.5, bars[2].datetime, bars[4].datetime)
    pv[2] = Pivot("L", 98.9, bars[30].datetime, bars[32].datetime)  # 98.9 < EMA-0.5ATR=99.5
    drafts = PullbackOrdinalDetector().detect(_ctx(cfg, bars, _pivots(pv), 100.0, 0.2, "trend_channel"))
    assert drafts == []


def test_h1_blocked_structure_break():
    cfg, bars, pivots = _h1_setup()
    pv = pivots.confirmed
    pv[2] = Pivot("L", 98.8, bars[30].datetime, bars[32].datetime)  # L1 < 前低 99.0
    drafts = PullbackOrdinalDetector().detect(_ctx(cfg, bars, pivots, 100.0, 0.2, "trend_channel"))
    assert drafts == []


def test_h1_blocked_no_recovery():
    cfg, bars, pivots = _h1_setup()
    bars[-1] = make_bar(bars[-1].datetime, 100.2, 100.5, 100.1, 100.3)  # 收盘 100.3 <= H_mid 100.4
    drafts = PullbackOrdinalDetector().detect(_ctx(cfg, bars, pivots, 100.0, 0.2, "trend_channel"))
    assert drafts == []


def test_h1_short_happy_path():
    cfg = build_config({"price_tick": 0.2, "buffer_ticks": 2, "enable_h1_l1": True})
    bars = _bars(40)
    bars[-1] = make_bar(bars[-1].datetime, 99.8, 99.9, 99.4, 99.6)
    pv = [
        Pivot("H", 101.5, bars[2].datetime, bars[4].datetime),
        Pivot("L", 99.0, bars[6].datetime, bars[8].datetime),     # L0
        Pivot("H", 100.4, bars[30].datetime, bars[32].datetime),  # H1 首次回调（<= EMA+0.5ATR）
        Pivot("L", 100.2, bars[36].datetime, bars[38].datetime),  # 中间低点
    ]
    drafts = PullbackOrdinalDetector().detect(_ctx(cfg, bars, _pivots(pv), 100.0, -0.2, "trend_channel"))
    assert len(drafts) == 1
    d = drafts[0]
    assert d.direction == "short" and d.signal_id == "H1_L1_TREND"
    assert d.trigger["level"] == 99.0 and d.stop["level"] == 100.65
    assert d.invalidation == {"type": "close_above", "level": 100.4}


def test_h1_disabled_by_default():
    cfg, bars, pivots = _h1_setup({"enable_h1_l1": False})
    drafts = PullbackOrdinalDetector().detect(_ctx(cfg, bars, pivots, 100.0, 0.2, "trend_channel"))
    assert drafts == []
    cfg2 = build_config({"price_tick": 0.2, "buffer_ticks": 2})
    drafts2 = PullbackOrdinalDetector().detect(_ctx(cfg2, bars, pivots, 100.0, 0.2, "trend_channel"))
    assert drafts2 == []


# ---------------------------------------------------------------- W/M

def _w_setup(extra_cfg=None):
    """W 底 happy path：L1(5) -> 颈线(10) -> L2(15, wash) -> 收盘破颈线(20)。"""
    cfg = build_config({"price_tick": 0.2, "buffer_ticks": 2,
                        "enable_w_m": True, **(extra_cfg or {})})
    closes = [100.0 + (i % 3) * 0.3 for i in range(21)]
    bars = _bars(21, closes)
    bars[15] = make_bar(bars[15].datetime, 99.95, 100.1, 99.75, 100.0)  # L2 处 bull 针形（下影 0.2 >> 实体 0.05）
    bars[-1] = make_bar(bars[-1].datetime, 101.3, 101.8, 101.2, 101.6)  # 收盘破颈线
    pv = [
        Pivot("L", 100.0, bars[5].datetime, bars[7].datetime),
        Pivot("H", 101.2, bars[10].datetime, bars[12].datetime),  # 颈线
        Pivot("L", 99.75, bars[15].datetime, bars[17].datetime),  # L2（wash，|L2-L1|=0.25 同时满足双顶底 0.3 容差）
    ]
    return cfg, bars, _pivots(pv)


def test_w_bottom_happy_path_with_wash():
    cfg, bars, pivots = _w_setup()
    drafts = WmDetector().detect(_ctx(cfg, bars, pivots, 100.0, 0.0, "reversal"))
    assert len(drafts) == 1
    d = drafts[0]
    assert d.category == "w_m" and d.signal_id == "W_BOTTOM"
    assert d.direction == "long" and d.note == "wash"
    assert d.trigger["type"] == "cross_above" and d.trigger["level"] == 101.6  # 颈线 101.2 + 0.4
    assert d.stop["level"] == 99.5                                             # L2 99.75 - 0.25 ATR
    assert d.invalidation == {"type": "close_below", "level": 101.2}


def test_w_blocked_no_neck():
    cfg, bars, pivots = _w_setup()
    pv = [p for p in pivots.confirmed if p.kind == "L"]  # 移除颈线高点
    drafts = WmDetector().detect(_ctx(cfg, bars, _pivots(pv), 100.0, 0.0, "reversal"))
    assert drafts == []


def test_w_blocked_neck_rebound_too_small():
    cfg, bars, pivots = _w_setup()
    pv = pivots.confirmed
    pv[1] = Pivot("H", 100.8, bars[10].datetime, bars[12].datetime)  # 反弹 0.8 < 1.0 ATR
    drafts = WmDetector().detect(_ctx(cfg, bars, _pivots(pv), 100.0, 0.0, "reversal"))
    assert drafts == []


def test_w_blocked_no_exhaustion():
    cfg, bars, pivots = _w_setup()
    bars[15] = make_bar(bars[15].datetime, 99.65, 99.85, 99.75, 99.8)  # 小实体无长影，非针形非吞没
    drafts = WmDetector().detect(_ctx(cfg, bars, pivots, 100.0, 0.0, "reversal"))
    assert drafts == []


def test_m_top_happy_path():
    cfg = build_config({"price_tick": 0.2, "buffer_ticks": 2, "enable_w_m": True})
    bars = _bars(21)
    bars[15] = make_bar(bars[15].datetime, 100.9, 101.1, 100.8, 100.85)  # H2 处 bear 针形
    bars[-1] = make_bar(bars[-1].datetime, 99.6, 99.7, 99.2, 99.4)       # 收盘破颈线
    pv = [
        Pivot("H", 101.0, bars[5].datetime, bars[7].datetime),
        Pivot("L", 99.8, bars[10].datetime, bars[12].datetime),  # 颈线
        Pivot("H", 101.1, bars[15].datetime, bars[17].datetime),  # H2（wash）
    ]
    drafts = WmDetector().detect(_ctx(cfg, bars, _pivots(pv), 100.0, 0.0, "range"))
    assert len(drafts) == 1
    d = drafts[0]
    assert d.category == "w_m" and d.signal_id == "M_TOP"
    assert d.direction == "short" and d.note == "wash"
    assert d.trigger["level"] == 99.4 and d.stop["level"] == 101.35
    assert d.invalidation == {"type": "close_above", "level": 99.8}


def test_wm_disabled_by_default():
    cfg, bars, pivots = _w_setup({"enable_w_m": False})
    drafts = WmDetector().detect(_ctx(cfg, bars, pivots, 100.0, 0.0, "reversal"))
    assert drafts == []


# ----------------------------------------------- 注册零回归 + 抑制

def test_registry_disabled_zero_drafts():
    """默认配置下全量 11 detector 跑 H1/W happy 场景：新两类的 category 零产出。"""
    cfg = build_config({"price_tick": 0.2, "buffer_ticks": 2})
    _, bars_h1, pivots_h1 = _h1_setup()
    _, bars_w, pivots_w = _w_setup()
    for ctx in (_ctx(cfg, bars_h1, pivots_h1, 100.0, 0.2, "trend_channel"),
                _ctx(cfg, bars_w, pivots_w, 100.0, 0.0, "reversal")):
        cats = {d.category for det in build_detectors() for d in det.detect(ctx)}
        assert "h1_l1" not in cats and "w_m" not in cats


def _wm_task(enable_w_m: bool):
    """构造 MonitoringTask：W/M 与双顶底同场，验证同向抑制。"""
    from vnpy_patiming.runtime import MonitoringTask

    cfg = build_config({
        "price_tick": 0.2, "buffer_ticks": 2, "enable_w_m": enable_w_m,
        "min_stop_atr": 0.05, "max_stop_atr": 50.0,
        "bar_min_atr": 0.05, "bar_max_atr": 50.0, "overlap_max": 1.0,
    })
    counter = {"n": 0}

    def next_id():
        counter["n"] += 1
        return f"A-{counter['n']}"

    eng = SimpleNamespace(cfg=cfg, data_mode="ctp_tick",
                          emit_alert=lambda *a, **k: None, next_alert_id=next_id)
    task = MonitoringTask(eng, "X", "1m", "1m")
    task.contributions[("s", "i")] = {
        "status": "ACTIVE", "direction": "both", "context_tag": "reversal",
        "signal_categories": {"w_m", "double_top_bottom"}, "key_levels": {},
        "source": "s", "instruction_id": "i", "content_hash": "h",
    }
    return task


def test_wm_suppresses_double_bottom_same_direction():
    task = _wm_task(enable_w_m=True)
    cfg, bars, pivots = _w_setup()
    task.bars = bars
    task.pivots = pivots
    task.atr.value = 1.0
    task.ema = SimpleNamespace(value=100.0, slope=lambda lookback=5: 0.0)
    task._detect_and_arm()
    ids = {a.signal_id for a in task.alerts.values()}
    assert "W_BOTTOM" in ids
    assert "DOUBLE_BOTTOM" not in ids  # 同向双顶底被抑制


def test_double_bottom_survives_when_wm_disabled():
    task = _wm_task(enable_w_m=False)
    cfg, bars, pivots = _w_setup({"enable_w_m": False})
    task.bars = bars
    task.pivots = pivots
    task.atr.value = 1.0
    task.ema = SimpleNamespace(value=100.0, slope=lambda lookback=5: 0.0)
    task._detect_and_arm()
    ids = {a.signal_id for a in task.alerts.values()}
    assert "DOUBLE_BOTTOM" in ids and "W_BOTTOM" not in ids
