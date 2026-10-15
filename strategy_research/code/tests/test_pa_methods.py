# RESEARCH ONLY - 研究级自测，禁止用于正式运行
"""MLIB 首批方法的单元自测：python -m pytest strategy_research/code/tests -q"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from methods.pa_methods import (  # noqa: E402
    SwingPoint, WmCheck, m_kb_001_is_pin, m_kb_002_is_engulf,
    m_kb_003_body_ratio, m_kb_004_no_follow, m_ex_001_push_decay,
    m_ex_002_body_decay, m_pt_001_confirmed_pivots, m_pt_004_h1_long,
    m_pt_005_w_bottom, m_pt_005_wm_trigger,
)
from methods.volume_methods import (  # noqa: E402
    m_dv_001_rebound_volume_divergence, m_dv_002_new_low_shrink,
    m_ex_003_volume_exhaustion, m_vr_002_rvol,
)
from methods.level_state_machine import (  # noqa: E402
    LevelRecord, LevelState, age_state, apply_event, classify_break_event,
    signal_weight_for,
)
from methods.trend_score import trend_score  # noqa: E402
from methods.benchmark_intraday import (  # noqa: E402
    DayOHLC, dual_thrust_signal, fiali_signal, r_breaker_signal,
    sky_garden_signal,
)
from methods.context_eval import agreement_matrix, ground_truth_label  # noqa: E402


@dataclass
class Bar:
    open_price: float
    high_price: float
    low_price: float
    close_price: float


def test_body_ratio():
    b = Bar(10, 12, 8, 11)
    assert abs(m_kb_003_body_ratio(b) - 0.25) < 1e-9
    assert m_kb_003_body_ratio(Bar(10, 10, 10, 10)) == 0.0


def test_pin_bull():
    bull_pin = Bar(100, 101, 90, 100.8)   # 下影 10 >> 实体 0.8，收盘在上 1/3
    assert m_kb_001_is_pin(bull_pin, bull=True)
    assert not m_kb_001_is_pin(bull_pin, bull=False)


def test_engulf():
    prev = Bar(100, 101, 99, 100.5)       # 阳线
    cur = Bar(101, 102, 98, 98.5)         # 大阴线吞没
    assert m_kb_002_is_engulf(cur, prev, bull=False)
    assert not m_kb_002_is_engulf(cur, prev, bull=True)


def test_no_follow():
    bars = [Bar(10, 10.5, 9.5, 10),
            Bar(10, 10.4, 9.6, 10.2),     # 突破K close=10.2 破 level 10.1
            Bar(10.2, 10.45, 10.1, 10.15),  # 跟随不足 (<0.5*ATR=0.5) 且收回
            Bar(10.1, 10.2, 9.9, 10.0)]
    assert m_kb_004_no_follow(bars, 1, level=10.1, direction="long", atr=1.0)
    # 无前瞻K时不判失败（防前视）
    assert not m_kb_004_no_follow(bars[:2], 1, level=10.1, direction="long", atr=1.0)


def test_push_decay_and_pivots():
    highs = [1, 5, 1, 3.5, 1, 3, 1]       # 推动 5->3.5 (a1=1.5), 3.5->3 (a2=0.5) 递减
    lows = [3, 0.5, 3, 1, 3, 1.5, 3]
    swings = m_pt_001_confirmed_pivots(highs, lows, k=1)
    r = m_ex_001_push_decay(swings, "H", decay_ratio=0.9)
    assert r is not None and r["two_seg_decay_ok"]
    # 幅度不递减的情形：5->4, 4->3 等幅，应返回 None
    highs_eq = [1, 5, 1, 4, 1, 3, 1]
    swings_eq = m_pt_001_confirmed_pivots(highs_eq, lows, k=1)
    assert m_ex_001_push_decay(swings_eq, "H", decay_ratio=0.9) is None


def test_body_decay():
    bars = [Bar(10, 10.1, 9.9, 10.05)] * 3   # 实体 0.05/0.2 = 0.25
    assert m_ex_002_body_decay(bars, 0) <= 0.45


def test_w_bottom():
    lows = [SwingPoint("L", 100.0, 5), SwingPoint("L", 99.8, 15)]  # wash 结构
    atr = 1.0
    r = m_pt_005_w_bottom(lows, tol_atr=0.5, neck_min_atr=1.0, atr=atr)
    assert r.ok and r.wash and abs(r.l2 - r.l1) <= 0.5 * atr
    # 间隔不足 -> 结构不成立
    lows2 = [SwingPoint("L", 100.0, 5), SwingPoint("L", 99.8, 8)]
    assert not m_pt_005_w_bottom(lows2, 0.5, 1.0, atr).ok


def test_rvol_and_new_low_shrink():
    vols = [100.0] * 20 + [200.0] * 5 + [60.0]        # L1@15 基准均量 100
    r = m_vr_002_rvol(vols, t=25, n=20)               # 当前 60，基准均 125
    assert r is not None and r < 1.0
    # 换月剔除：基准窗口含标记根时仍可算（剔除后半数以上即可）
    r2 = m_vr_002_rvol(vols, t=15, n=20, rollover_flags={5})
    assert r2 is not None
    # 数据不足 -> None
    assert m_vr_002_rvol([100.0] * 3, t=2, n=10) is None
    # 新低缩量：L2 创新低且相对量缩（L1/L2 均为 rvol，量纲一致——阶段0-4 勘误）
    pivots = [SwingPoint("L", 100.0, 15), SwingPoint("L", 99.0, 25)]
    # L2 根 rvol = 60/125 = 0.48 < 0.8 x rvol_l1(=100/100=1.0) -> True
    assert m_dv_002_new_low_shrink([], [], vols, pivots, rvol_at_new_low=0.48,
                                    shrink_ratio=0.8) is True
    # 量纲一致性回归（旧 bug 防御）：rvol_at_new_low=0.9 不缩量 -> False
    assert m_dv_002_new_low_shrink([], [], vols, pivots, 0.9, 0.8) is False
    # 未创新低 -> False
    pivots2 = [SwingPoint("L", 100.0, 15), SwingPoint("L", 101.0, 25)]
    assert m_dv_002_new_low_shrink([], [], vols, pivots2, 0.48, 0.8) is False
    # rvol 缺失 -> None
    assert m_dv_002_new_low_shrink([], [], vols, pivots, None, 0.8) is None


def test_level_state_machine():
    # 事件三分类
    assert classify_break_event(12.0, 10.5, level=10.0, atr=1.0,
                                direction="long") == "profit_break"   # 走出2ATR
    assert classify_break_event(10.4, 9.8, level=10.0, atr=1.0,
                                direction="long") == "fake_break"     # 触及即收回
    assert classify_break_event(10.7, 9.9, level=10.0, atr=1.0,
                                direction="long") == "fail_break"     # 走0.7收回
    assert classify_break_event(10.6, 10.2, level=10.0, atr=1.0,
                                direction="long") == "pending"        # 未定级
    # 状态机流转 + TTL
    rec = LevelRecord(price=10.0)
    apply_event(rec, "fake_break", bar_index=100)
    assert rec.state == LevelState.FAKE_BREAK
    assert age_state(rec, 110) == LevelState.FAKE_BREAK
    assert age_state(rec, 130) == LevelState.FRESH                    # TTL=20 超时回落
    # 后继权重表
    assert signal_weight_for(LevelState.FAKE_BREAK, "second_breakout") == 1.5
    assert signal_weight_for(LevelState.PROFIT_BREAK, "breakout") == 0.5
    assert signal_weight_for(LevelState.FRESH, "breakout") == 1.0


def test_volume_exhaustion_and_divergence():
    # M-EX-003：缩量 + 收盘靠反转侧 1/3（close ≥ low + 2/3 rng，阶段0-4 勘误）
    ex_bar = Bar(100, 100.4, 99.0, 100.2)      # rng=1.4, 反转侧阈值=99.933
    assert m_ex_003_volume_exhaustion(ex_bar, 0.6, prior_ret20=0.01) is True
    assert m_ex_003_volume_exhaustion(ex_bar, 0.9,
                                      prior_ret20=0.01) is False  # 不够缩量
    mid_bar = Bar(100, 100.4, 99.0, 99.7)      # 收盘中部（非反转侧 1/3）
    assert m_ex_003_volume_exhaustion(mid_bar, 0.6,
                                      prior_ret20=0.01) is False
    # 闸门：prior_ret20 ≤ −5% 或缺失 -> None（深跌不放行）
    assert m_ex_003_volume_exhaustion(ex_bar, 0.6, prior_ret20=-0.06) is None
    assert m_ex_003_volume_exhaustion(ex_bar, 0.6, prior_ret20=None) is None
    assert m_ex_003_volume_exhaustion(ex_bar, None, prior_ret20=0.01) is None
    # M-DV-001：反弹放量 + 探底缩量
    assert m_dv_001_rebound_volume_divergence([1.6, 1.8], [0.9, 0.7]) is True
    assert m_dv_001_rebound_volume_divergence([0.9, 0.8], [1.0, 0.9]) is False
    assert m_dv_001_rebound_volume_divergence([], [0.9]) is None


def test_ground_truth_label():
    closes = [100.0 + 0.5 * i for i in range(60)]     # 单边上涨
    gt = ground_truth_label(closes, atr=1.0, as_of=39, horizon=20)
    assert gt.label == "TREND_UP"
    # 区间：净位移小且不破边
    flat = [100.0 + (0.2 if i % 2 else -0.2) for i in range(60)]
    gt2 = ground_truth_label(flat, atr=1.0, as_of=39, horizon=20)
    assert gt2.label in ("RANGE", "UNDEFINED")
    # 数据不足 -> UNDEFINED
    assert ground_truth_label(closes, 1.0, as_of=55, horizon=20).label == "UNDEFINED"
    # v1.1：先涨后跌的往返（净位移收窄）-> REVERSAL；而非 TREND_DN
    rt = [100.0] + [100.0 + 0.2 * i for i in range(1, 11)] \
        + [102.0 - 0.2 * i for i in range(1, 11)]
    assert ground_truth_label(rt, 1.0, as_of=0, horizon=20).label == "REVERSAL"
    # 混淆矩阵协议
    agg = agreement_matrix(["TREND_UP", "TREND_UP", "RANGE"],
                           ["TREND_UP", "RANGE", "RANGE"])
    assert agg["top_pred_precision"]["RANGE"] == 1.0
    assert agg["matrix"]["TREND_UP"]["RANGE"] == 1


def test_benchmark_intraday():
    prev = DayOHLC(open=100, high=102, low=98, close=101)
    # Dual Thrust：k=0.5, rng=4 -> 上轨 open+2 / 下轨 open-2
    assert dual_thrust_signal(DayOHLC(101, 103.5, 100.5, 103), prev, 101) == 1
    assert dual_thrust_signal(DayOHLC(101, 101.5, 98.5, 99), prev, 101) == -1
    assert dual_thrust_signal(DayOHLC(101, 102.5, 99.5, 101), prev, 101) == 0
    # 菲阿里：昨高 102 / 昨低 98
    assert fiali_signal(DayOHLC(101, 102.5, 100, 102), prev) == 1
    assert fiali_signal(DayOHLC(101, 101, 97.5, 98.5), prev) == -1
    # R-Breaker：P=100.33, B=98.66? -> 突破买 = 2P-L = 102.66
    assert r_breaker_signal(DayOHLC(101, 103, 100.5, 102.8), prev) == 1
    assert r_breaker_signal(DayOHLC(101, 101, 97, 97.5), prev) == -1
    # 空中花园：跳空超阈值且首根同向
    assert sky_garden_signal(prev, DayOHLC(103, 104, 102.8, 103.8),
                             gap_atr=1.0, atr=1.0) == 1
    assert sky_garden_signal(prev, DayOHLC(99.5, 100.0, 99.0, 99.2),
                             gap_atr=1.0, atr=1.0) == -1
    assert sky_garden_signal(prev, DayOHLC(101.2, 102, 100.8, 101.5),
                             gap_atr=1.0, atr=1.0) == 0


def test_h1_first_pullback():
    # 老低点(30 根前) + 首次回调 L1 -> 合法 H1 结构
    pivots = [SwingPoint("L", 100.0, 0), SwingPoint("L", 101.0, 40),
              SwingPoint("L", 101.5, 48)]
    r = m_pt_004_h1_long(pivots, ema=101.0, atr=1.0)
    assert r is not None and r["l2"] > r["l1"]
    # L1 之前 20 根内还有低点 -> 非首次回调
    pivots2 = [SwingPoint("L", 100.0, 35), SwingPoint("L", 101.0, 40),
               SwingPoint("L", 101.5, 48)]
    assert m_pt_004_h1_long(pivots2, 101.0, 1.0) is None
    # 破前低 -> None
    pivots3 = [SwingPoint("L", 102.0, 0), SwingPoint("L", 101.0, 40),
               SwingPoint("L", 100.5, 48)]
    assert m_pt_004_h1_long(pivots3, 101.0, 1.0) is None
    # 深回调（低于 EMA-0.5ATR）-> None
    pivots4 = [SwingPoint("L", 100.0, 0), SwingPoint("L", 101.0, 40),
               SwingPoint("L", 100.2, 48)]
    assert m_pt_004_h1_long(pivots4, 101.5, 1.0) is None


def test_wm_trigger():
    wm = WmCheck(ok=True, l1=100.0, l2=99.8, neck=101.0, wash=True)
    # 收盘突破颈线 -> 触发（无 prev 时仅看颈线）
    assert m_pt_005_wm_trigger(wm, Bar(100.5, 101.6, 100.4, 101.2),
                               direction="long") is True
    # 未破颈线 -> 不触发
    assert m_pt_005_wm_trigger(wm, Bar(100.5, 101.2, 100.4, 100.8),
                               direction="long") is False
    # 结构不成立 -> 一律不触发
    bad = WmCheck(ok=False, reasons=["sep"])
    assert m_pt_005_wm_trigger(bad, Bar(100.5, 101.6, 100.4, 101.2),
                               direction="long") is False


def test_trend_score():
    # 稳定上升序列：应给出 +1 方向与高分散化分值
    n = 40
    closes = [100 + 0.5 * i for i in range(n)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    pivots = [SwingPoint("H", 101 + 0.5 * i, i) for i in (5, 15, 25, 35)] + \
             [SwingPoint("L", 99 + 0.5 * i, i) for i in (10, 20, 30)]
    atr = 1.0
    d, s = trend_score(closes, highs, lows, pivots, atr,
                       period=20, higher_tf_dir=1)
    assert d == 1
    assert s > 70, f"强趋势应高分, got {s}"
    # 反转趋势方向：一致性项惩罚生效
    d2, s2 = trend_score(closes, highs, lows, pivots, atr,
                         period=20, higher_tf_dir=-1)
    assert d2 == 1 and s2 < s
    # 震荡序列：低分
    chop = [100 + (1 if i % 2 else -1) * (0.2 if i % 3 else 0.4) for i in range(n)]
    _, s3 = trend_score(chop, [c + 0.5 for c in chop], [c - 0.5 for c in chop],
                        [], atr, period=20)
    assert s3 < 40, f"震荡应低分, got {s3}"
    # 空头趋势：方向感知合规（阶段0-4 勘误回归——旧版仅统计递增，空头被低估）
    dn = [200 - 0.5 * i for i in range(n)]
    dn_highs = [c + 0.5 for c in dn]
    dn_lows = [c - 0.5 for c in dn]
    dn_pivots = [SwingPoint("H", 199 - 0.5 * i, i) for i in (5, 15, 25, 35)] + \
                [SwingPoint("L", 197 - 0.5 * i, i) for i in (10, 20, 30)]
    d4, s4 = trend_score(dn, dn_highs, dn_lows, dn_pivots, atr,
                         period=20, higher_tf_dir=-1)
    assert d4 == -1
    assert s4 > 70, f"空头趋势应高分（方向感知合规）, got {s4}"
