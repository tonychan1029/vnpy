# RESEARCH ONLY - 未获用户批准不得正式运行
"""经典日内策略判据集研究级实现（CAND-005，基准对照用）。

用途：作为 PA 信号族的绩效对照基准（同数据、同成本口径），
不构成任何正式策略。判据为业界公开常识版，系数取常用缺省。
与工程代码零依赖。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DayOHLC:
    open: float
    high: float
    low: float
    close: float


def dual_thrust_levels(prev: DayOHLC, today_open: float,
                       k1: float = 0.5, k2: float = 0.5) -> tuple[float, float]:
    """Dual Thrust 上下轨。Δ 取三振幅最大值（含 M-FL/KB 同源口径）。"""
    rng = max(prev.high - prev.low,
              prev.high - prev.close,
              prev.close - prev.low)
    return today_open + k1 * rng, today_open - k2 * rng


def dual_thrust_signal(today: DayOHLC, prev: DayOHLC, today_open: float,
                       k1: float = 0.5, k2: float = 0.5) -> int:
    """+1 做多 / -1 做空 / 0 观望（日内收盘平仓口径）。"""
    up, dn = dual_thrust_levels(prev, today_open, k1, k2)
    if today.high >= up:
        return 1
    if today.low <= dn:
        return -1
    return 0


def fiali_levels(prev: DayOHLC) -> tuple[float, float]:
    """菲阿里四价：昨日高/低为上下轨。"""
    return prev.high, prev.low


def fiali_signal(today: DayOHLC, prev: DayOHLC) -> int:
    up, dn = fiali_levels(prev)
    if today.high > up:
        return 1
    if today.low < dn:
        return -1
    return 0


def r_breaker_levels(prev: DayOHLC) -> dict[str, float]:
    """R-Breaker 六价位（标准系数版）。"""
    p = (prev.high + prev.low + prev.close) / 3
    return {
        "B": 2 * p - prev.low,          # 突破买入
        "S": p + (prev.high - prev.low),  # 反转卖出
        "R": p - (prev.high - prev.low),  # 反转买入
        "S2": 2 * p - prev.high,        # 突破卖出
        "P": p,
    }


def r_breaker_signal(today: DayOHLC, prev: DayOHLC) -> int:
    """R-Breaker 简化信号（趋势+反转双模式，日内平仓口径）。

    规则（公开常识版，观察盘中先后顺序的完整版属工程实现细节）：
    - high > B -> +1（突破做多）
    - low < S2 -> -1（突破做空）
    - 触 S 未破 B 后回落收于 P 下 -> -1（反转做空）
    - 触 R 未破 S2 后回升收于 P 上 -> +1（反转做多）
    """
    lv = r_breaker_levels(prev)
    if today.high > lv["B"]:
        return 1
    if today.low < lv["S2"]:
        return -1
    if (today.high >= lv["S"] and today.close < lv["P"]):
        return -1
    if (today.low <= lv["R"] and today.close > lv["P"]):
        return 1
    return 0


def sky_garden_signal(prev: DayOHLC, today: DayOHLC,
                      gap_atr: float, atr: float) -> int:
    """空中花园：跳空超 gap_atr x ATR 定方向，首根K同向突破入场。"""
    gap = today.open - prev.close
    if gap > gap_atr * atr and today.high > today.open:
        return 1
    if gap < -gap_atr * atr and today.low < today.open:
        return -1
    return 0
