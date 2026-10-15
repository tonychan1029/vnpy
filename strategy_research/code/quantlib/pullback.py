# RESEARCH ONLY - quantlib.pullback：回调质量评估模块
"""回调质量：回撤比例 / MA 贴近 / 支撑有效性。

行布局：bars 为 list[list]，[dt, o, h, l, c, v, oi]。
"""

from __future__ import annotations

# 行布局常量（全模块统一引用，禁止硬编码数字）
I_DT, I_O, I_H, I_L, I_C, I_V, I_OI = range(7)


def retracement_fraction(
    leg_high: float,
    leg_low: float,
    current_close: float,
) -> float:
    """回撤比例：当前价在腿幅中的回撤位置（0=起点，1=终点）。

    long 回调：pb = (leg_high - current) / (leg_high - leg_low)
    short 反弹：pb = (current - leg_low) / (leg_high - leg_low)
    """
    leg_range = leg_high - leg_low
    if leg_range <= 0:
        return 0.0
    return (leg_high - current_close) / leg_range


def near_ma(
    close: float,
    ma: float,
    atr: float,
    tolerance_atr: float = 0.5,
    tolerance_pct: float = 0.005,
) -> bool:
    """MA 贴近判定：|close - ma| ≤ max(tolerance_atr × ATR, tolerance_pct × price)。"""
    if atr <= 0 or close <= 0:
        return False
    tolerance = max(tolerance_atr * atr, tolerance_pct * close)
    return abs(close - ma) <= tolerance


def near_level(
    close: float,
    level: float,
    atr: float,
    tolerance_atr: float = 0.5,
) -> bool:
    """关键位接近判定：|close - level| ≤ tolerance_atr × ATR。"""
    if atr <= 0:
        return False
    return abs(close - level) <= tolerance_atr * atr


def support_held(
    bars: list,
    support: float,
    buffer_pct: float = 0.02,
    confirm_bars: int = 3,
) -> bool:
    """支撑守住判定：最近 confirm_bars 根收盘均未有效跌破支撑（buffer_pct 容差）。

    bars: [[dt, o, h, l, c, v, oi]]（尾 confirm_bars 根）
    """
    if len(bars) < confirm_bars:
        return False
    threshold = support * (1 - buffer_pct)
    for bar in bars[-confirm_bars:]:
        if bar[I_C] < threshold:
            return False
    return True
