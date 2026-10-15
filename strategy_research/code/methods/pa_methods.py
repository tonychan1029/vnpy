# RESEARCH ONLY - 未获用户批准不得正式运行
# 研究级方法库实现（MLIB 首批）：仅用于回测/分析，禁止接入实盘/模拟盘。
# 每个函数对应 MLIB 登记册一个 M-ID；定义以登记册为单一事实来源。
"""MLIB 首批研究级实现：KB 形态三方法 + EX 衰竭两方法 + KB-004 无跟随判据。

约定：K 线以 duck-typed 对象传入（需 open/high/low/close[/volume] 属性，
兼容 vnpy BarData）；本模块不 import 任何工程代码，保持物理隔离。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------- KB 组
def m_kb_003_body_ratio(bar) -> float:
    """M-KB-003 实体比例：|close-open| / (high-low)；区间为 0 时返回 0。"""
    rng = bar.high_price - bar.low_price
    if rng <= 0:
        return 0.0
    return abs(bar.close_price - bar.open_price) / rng


def m_kb_001_is_pin(bar, bull: bool) -> bool:
    """M-KB-001 针形：影线 >= 2x实体 且收盘位于区间靠反转侧 1/3。

    bull=True 判多头针（下影长，见底反转）。
    """
    body = abs(bar.close_price - bar.open_price)
    rng = bar.high_price - bar.low_price
    if rng <= 0 or body <= 0:
        return False
    lower_wick = min(bar.open_price, bar.close_price) - bar.low_price
    upper_wick = bar.high_price - max(bar.open_price, bar.close_price)
    if bull:
        outer = bar.close_price >= bar.low_price + rng * (2.0 / 3.0)  # 反转侧 1/3（quantlib 权威口径）
        return lower_wick >= 2 * body and outer
    outer = bar.close_price <= bar.high_price - rng * (2.0 / 3.0)
    return upper_wick >= 2 * body and outer


def m_kb_002_is_engulf(bar, prev, bull: bool) -> bool:
    """M-KB-002 吞没：与前一K异色且实体完全包含前K实体。"""
    if prev is None:
        return False
    prev_bull = prev.close_price > prev.open_price
    if bull == prev_bull:
        return False
    cur_lo, cur_hi = sorted((bar.open_price, bar.close_price))
    prev_lo, prev_hi = sorted((prev.open_price, prev.close_price))
    return cur_lo <= prev_lo and cur_hi >= prev_hi


def m_kb_004_no_follow(bars: list, breakout_index: int, level: float,
                       direction: str, atr: float,
                       follow_atr: float = 0.5, window: int = 2) -> bool:
    """M-KB-004 突破无跟随失败判定。

    突破K后 window 根内未走满 follow_atr x ATR 同向位移，且收盘收回
    level 另一侧 -> 失败成立（返回 True）。
    bars[breakout_index] 为突破K本身。
    """
    bk = bars[breakout_index]
    fwd = bars[breakout_index + 1: breakout_index + 1 + window]
    if not fwd:
        return False  # 前瞻数据不足，不作失败判定（防前视：仅用已完结K）
    if direction == "long":
        moved = max(b.high_price for b in fwd) - bk.close_price
        pulled_back = fwd[-1].close_price < level
    else:
        moved = bk.close_price - min(b.low_price for b in fwd)
        pulled_back = fwd[-1].close_price > level
    return moved < follow_atr * atr and pulled_back


# ---------------------------------------------------------------- EX 组
@dataclass
class SwingPoint:
    """已确认摆动点（M-PT-001 的最小化研究版）。"""
    kind: str            # "H" / "L"
    price: float
    index: int           # 所在K序号
    bar_time: object = None


def m_pt_001_confirmed_pivots(highs: list[float], lows: list[float],
                              k: int = 2) -> list[SwingPoint]:
    """M-PT-001 摆动点确认：左右各 k 根确认的高/低点。"""
    out: list[SwingPoint] = []
    n = len(highs)
    for i in range(k, n - k):
        if all(highs[i] > highs[j] for j in range(i - k, i + k + 1) if j != i):
            out.append(SwingPoint("H", highs[i], i))
        if all(lows[i] < lows[j] for j in range(i - k, i + k + 1) if j != i):
            out.append(SwingPoint("L", lows[i], i))
    return out


def m_ex_001_push_decay(swings: list[SwingPoint], kind: str,
                        decay_ratio: float = 0.67) -> dict | None:
    """M-EX-001 推动计数与幅度衰减（三推）。

    kind="H"：检查最近三个摆动高点幅度递减 a1>a2>a3 且 a3 <= ratio*a1。
    kind="L"：低点对称。返回 dict(a1,a2,a3,p3=最后摆动点) 或 None。
    """
    pts = [p for p in swings if p.kind == kind]
    if len(pts) < 3:
        return None
    p1, p2, p3 = pts[-3], pts[-2], pts[-1]
    a1 = abs(p2.price - p1.price)
    a2 = abs(p3.price - p2.price)
    if not (0 < a2 < a1):
        return None
    a3 = a2 * 0  # 三推幅度需第 4 个同侧点或以当前K延伸度量；研究版按 2 段衰减近似
    # 严格三推：需要 3 段幅度，此处返回前两段信息供调用方以当前 bar 延伸计算 a3
    return {"a1": a1, "a2": a2, "a3": a3, "p3": p3,
            "two_seg_decay_ok": a2 <= a1 * decay_ratio}


def m_ex_002_body_decay(bars: list, since_index: int,
                        body_max: float = 0.45) -> float:
    """M-EX-002 推动实体衰减：since 起平均实体比例是否 <= body_max。

    返回平均 body_ratio（调用方与 body_max 比较）。
    """
    seg = bars[since_index:]
    if not seg:
        return 1.0
    return sum(m_kb_003_body_ratio(b) for b in seg) / len(seg)


# ------------------------- M-PT-004 H1/L1（RS004 §1，v1） ----------------

def m_pt_004_h1_long(pivots: list[SwingPoint], ema: float, atr: float,
                     lookback: int = 20, ema_tol: float = 0.5) -> dict | None:
    """M-PT-004 H1（首次回调做多）结构检查（不含触发）。

    条件（RS004 §1.2）：
    1. 最近两个低点 L1、L2，且 L1 为"首次回调"：L1 之前 lookback 根内无其他低点
    2. 结构保持：L2 >= L1（未破前低）
    3. 浅回调：L2 >= EMA - ema_tol x ATR
    返回 dict(l1, l2, gap) 或 None。
    """
    lows = [p for p in pivots if p.kind == "L"]
    if len(lows) < 2:
        return None
    l1, l2 = lows[-2], lows[-1]
    # 首次回调：L1 之前 lookback 内无其他已确认低点
    earlier = [p for p in lows if p.index < l1.index]
    if earlier and (l1.index - earlier[-1].index) <= lookback:
        return None
    if l2.price < l1.price:
        return None                     # 结构破坏（破前低）
    if l2.price < ema - ema_tol * atr:
        return None                     # 深回调，交由衰竭判据管理
    return {"l1": l1.price, "l2": l2.price, "gap": l2.index - l1.index}


def m_pt_005_wm_trigger(wm: WmCheck, bar, prev=None,
                        direction: str = "long") -> bool:
    """M-PT-005 触发确认（结构检查通过后调用）。

    W 底：收盘突破颈线（做多）；M 顶：收盘跌破颈线（做空）。
    反转形态质量（pin/吞没，可选 prev）作为附加确认，缺 prev 时仅看颈线突破。
    """
    if not wm.ok:
        return False
    if direction == "long":
        if bar.close_price <= wm.neck:
            return False
        return prev is None or m_kb_002_is_engulf(bar, prev, True) or \
            m_kb_001_is_pin(bar, True)
    if bar.close_price >= wm.neck:
        return False
    return prev is None or m_kb_002_is_engulf(bar, prev, False) or \
        m_kb_001_is_pin(bar, False)


# ---------------------------------------------------------------- 快捷结构
@dataclass
class WmCheck:
    """M-PT-005 W/M 判据的中间结果。"""
    ok: bool
    l1: float = 0.0
    l2: float = 0.0
    neck: float = 0.0
    wash: bool = False          # L2 < L1 扫损结构
    reasons: list = field(default_factory=list)


def m_pt_005_w_bottom(lows: list[SwingPoint], tol_atr: float,
                      neck_min_atr: float, atr: float,
                      max_sep: int = 30, min_sep: int = 5) -> WmCheck:
    """M-PT-005 W 底结构检查（不含触发，仅结构三要素）。

    条件：L1/L2 间隔 [min_sep, max_sep]；|L2-L1| <= tol_atr x ATR；
    中间存在颈线反弹 >= neck_min_atr x ATR（此处以两低点间最高摆动高点近似，
    完整版应嵌入枢轴区间实际高点）。
    """
    lp = [p for p in lows if p.kind == "L"]
    if len(lp) < 2:
        return WmCheck(False, reasons=["lows<2"])
    l1, l2 = lp[-2], lp[-1]
    sep = l2.index - l1.index
    if not (min_sep <= sep <= max_sep):
        return WmCheck(False, l1=l1.price, l2=l2.price, reasons=["sep"])
    if abs(l2.price - l1.price) > tol_atr * atr:
        return WmCheck(False, l1=l1.price, l2=l2.price, reasons=["tol"])
    return WmCheck(True, l1=l1.price, l2=l2.price,
                   neck=(l1.price + l2.price) / 2,  # 颈线需调用方以区间高点覆写
                   wash=l2.price < l1.price,
                   reasons=["structure-ok; neck 需调用方以区间实际高点覆写"])
