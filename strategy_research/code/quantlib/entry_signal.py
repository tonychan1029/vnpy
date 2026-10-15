# RESEARCH ONLY - quantlib.entry_signal：入场信号量化模块
"""入场信号（择时层信号 K 判定）：突破/H2L2/垂线/反包/近均十字星。

行布局：bars 为 list[list]，7 元素：
  [0]=dt, [1]=open, [2]=high, [3]=low, [4]=close, [5]=volume, [6]=position
"""

from __future__ import annotations

# 行布局常量（全模块统一引用，禁止硬编码数字）
I_DT, I_O, I_H, I_L, I_C, I_V, I_OI = range(7)


def breakout_confirm(
    bars: list,
    window: int = 20,
    body_ratio_min: float = 0.6,
    buffer_atr: float = 0.1,
    atr: float = 0,
) -> dict | None:
    """信号#1 关键位突破：收盘穿越 key_level + 实体比过滤。

    判定：当前 bar 收盘 > 前 window 根最高 + buffer → 向上突破
          当前 bar 收盘 < 前 window 根最低 − buffer → 向下突破
    body_ratio_min：实体/全长最低比例（过滤长影线假突破）
    """
    if len(bars) < window + 1:
        return None
    prev_bars = bars[-window - 1:-1]  # 不含当前根
    if not prev_bars:
        return None
    prev_high = max(b[I_H] for b in prev_bars)
    prev_low = min(b[I_L] for b in prev_bars)
    cur = bars[-1]
    c = cur[I_C]
    o = cur[I_O]

    body = abs(c - o)
    full = cur[I_H] - cur[I_L]
    if full <= 0:
        return None
    if body / full < body_ratio_min:
        return None

    # 向上突破
    if c > prev_high + buffer_atr * atr:
        return {"direction": "long", "trigger": prev_high + buffer_atr * atr}
    # 向下突破
    if c < prev_low - buffer_atr * atr:
        return {"direction": "short", "trigger": prev_low - buffer_atr * atr}
    return None


def h2l2_detect(
    bars: list,
    window: int = 10,
    tolerance_atr: float = 0.1,
    atr: float = 0,
) -> dict | None:
    """信号#6 高2/低2：两个相邻 pivot，第二个不破第一个（容差内）。

    bars: 尾 window+2 根，行布局同主常量
    返回 {"direction": "long"/"short"} 或 None
    """
    if len(bars) < window + 2:
        return None
    tol = tolerance_atr * atr
    lows = [b[I_L] for b in bars]
    highs = [b[I_H] for b in bars]

    # 找局部摆动低点（左右各 1 根确认）
    piv_l = []
    for i in range(1, len(lows) - 1):
        if lows[i] < lows[i - 1] and lows[i] <= lows[i + 1]:
            piv_l.append((i, lows[i]))
    # 找局部摆动高点
    piv_h = []
    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i - 1] and highs[i] >= highs[i + 1]:
            piv_h.append((i, highs[i]))

    # 高2：两个相邻摆动高点，第二个不高于第一个太多（≤tol），当前收盘突破
    if len(piv_h) >= 2:
        _, p1 = piv_h[-2]
        _, p2 = piv_h[-1]
        if abs(p2 - p1) <= tol and p2 > 0:
            cur_c = bars[-1][I_C]
            if cur_c > p2:
                return {"direction": "long", "entry_ref": p2}

    # 低2：两个相邻摆动低点，第二个不低于第一个太多（≤tol），当前收盘跌破
    if len(piv_l) >= 2:
        _, p1 = piv_l[-2]
        _, p2 = piv_l[-1]
        if abs(p2 - p1) <= tol and p2 > 0:
            cur_c = bars[-1][I_C]
            if cur_c < p2:
                return {"direction": "short", "entry_ref": p2}
    return None


def pin_bar(
    o: float,
    h: float,
    l: float,
    c: float,
    shadow_body_ratio: float = 2.0,
    close_position: float = 1 / 3,
) -> str | None:
    """信号#3 垂线（pin bar）：影线≥ratio×实体 且收盘在K线外侧1/3。

    返回 "long"（下影线长=看涨）/ "short"（上影线长=看跌）/ None。
    """
    body = abs(c - o)
    rng = h - l
    if rng <= 0 or body <= 0:
        return None
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)

    # 看涨 pin：下影线长且收盘在K线上1/3
    if lower_wick >= shadow_body_ratio * body and c >= l + rng * (1 - close_position):
        return "long"
    # 看跌 pin：上影线长且收盘在K线下1/3
    if upper_wick >= shadow_body_ratio * body and c <= h - rng * (1 - close_position):
        return "short"
    return None


def engulf_detect(
    o: float, h: float, l: float, c: float,
    prev_o: float, prev_h: float, prev_l: float, prev_c: float,
) -> str | None:
    """信号#4 反包K线：当前K线实体完全包住前一根实体（方向相反）。"""
    cur_bull = c > o
    prev_bull = prev_c > prev_o
    if cur_bull == prev_bull:
        return None
    cur_lo = min(o, c)
    cur_hi = max(o, c)
    prev_lo = min(prev_o, prev_c)
    prev_hi = max(prev_o, prev_c)
    if cur_lo <= prev_lo and cur_hi >= prev_hi:
        return "long" if cur_bull else "short"
    return None


def near_ma_doji(
    o: float, h: float, l: float, c: float,
    ma: float,
    ma_tolerance: float,
    doji_body_ratio: float = 0.1,
) -> bool:
    """近均十字星：价格靠近均线时出现十字星/小K线。"""
    rng = h - l
    body = abs(c - o)
    if rng <= 0:
        return False
    is_doji = body / rng <= doji_body_ratio
    is_near_ma = abs(c - ma) <= ma_tolerance
    return is_doji and is_near_ma
