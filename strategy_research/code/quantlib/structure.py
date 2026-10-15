# RESEARCH ONLY - 未获用户批准不得正式运行
"""quantlib.structure：趋势形态/摆动点/区间边界/支撑三法。

行布局：bars 为 list[list]，每行 [dt, o, h, l, c, v, oi]。

多方案设计（同一接口，不同实现可切换）：
  趋势判定：detect_trend_zigzag / detect_trend_ema_slope / classify_trend
  摆动点：find_swing_points (fractal k) / detect_rollover (换月)
  区间边界：find_range_boundary (摆动点 / 分位带)
  支撑判定：near_support / near_resistance / kline_density_zone
"""

from __future__ import annotations

from typing import Optional


# ── 摆动点检测 ────────────────────────────────────────────────

def find_swing_points(
    bars: list,
    left: int = 5,
    right: int = 5,
    use_hl: bool = True,
) -> list[dict]:
    """Fractal 摆动点检测（TradingView pivot 口径）。

    确认规则：bars[i] 的 high 严格大于左右各 left/right 根的 high → 摆动高点。
    同理 low。返回交替序列（连续同向取更极端值）。

    参数：
      bars: 行情列表（行布局见模块头）
      left: 左侧确认根数
      right: 右侧确认根数（确认延迟 = right 根）
      use_hl: True 用 high/low 判定，False 用 close

    返回：[{"index": int, "type": "H"/"L", "price": float, "confirmed_at": int}]
      confirmed_at = 摆动点被确认的 bar 索引（index + right）
    """
    n = len(bars)
    if n < left + right + 1:
        return []

    hi_i, lo_i = (I_H, I_L) if use_hl else (I_O, I_C)
    raw = []
    for i in range(left, n - right):
        is_high = all(bars[i][hi_i] > bars[j][hi_i]
                      for j in range(i - left, i + right + 1) if j != i)
        is_low = all(bars[i][lo_i] < bars[j][lo_i]
                     for j in range(i - left, i + right + 1) if j != i)
        if is_high:
            raw.append({"index": i, "type": "H", "price": bars[i][hi_i],
                        "confirmed_at": i + right})
        if is_low:
            raw.append({"index": i, "type": "L", "price": bars[i][lo_i],
                        "confirmed_at": i + right})

    # 交替序列：连续同向取更极端值
    result = []
    for p in raw:
        if result and result[-1]["type"] == p["type"]:
            prev = result[-1]
            if (p["type"] == "H" and p["price"] >= prev["price"]) or \
               (p["type"] == "L" and p["price"] <= prev["price"]):
                result[-1] = p
        else:
            result.append(p)
    return result


# ── 趋势判定（多方案）────────────────────────────────────────

def detect_trend_zigzag(
    bars: list,
    theta: float = 0.04,
    tail: int = 300,
    use_hl: bool = True,
) -> str:
    """方案A：ZigZag 比例确认 + HH/HL / LH/LL（Hermes pullback_screen 口径）。

    θ=4%：从极值回撤 4% 确认摆动点（日线档）。
    返回：多头/空头/震荡
    """
    seg = bars[-tail:]
    if len(seg) < 60:
        return "震荡"
    hi_i, lo_i, c_i = I_H, I_L, I_C
    if not use_hl:
        hi_i = lo_i = I_C

    piv = []
    trend = 0
    ext_i, ext_p = 0, seg[0][c_i]
    for i in range(1, len(seg)):
        hi, lo = seg[i][hi_i], seg[i][lo_i]
        if trend >= 0:
            if hi > ext_p:
                ext_i, ext_p = i, hi
            elif lo < ext_p * (1 - theta):
                piv.append((ext_i, "H", ext_p))
                trend = -1
                ext_i, ext_p = i, lo
        if trend <= 0:
            if lo < ext_p:
                ext_i, ext_p = i, lo
            elif hi > ext_p * (1 + theta):
                piv.append((ext_i, "L", ext_p))
                trend = 1
                ext_i, ext_p = i, hi

    hs = [p[2] for p in piv if p[1] == "H"][-2:]
    ls = [p[2] for p in piv if p[1] == "L"][-2:]
    if len(hs) < 2 or len(ls) < 2:
        return "震荡"
    if hs[-1] > hs[-2] and ls[-1] > ls[-2]:
        return "多头"
    if hs[-1] < hs[-2] and ls[-1] < ls[-2]:
        return "空头"
    return "震荡"


def detect_trend_ema_slope(
    bars: list,
    ema_period: int = 21,
    slope_bars: int = 3,
    tail: int = 120,
) -> str:
    """方案B：EMA 斜率 + HH/HL 结构（PABackgroundEngine 口径）。

    BULL: close > EMA21 且 EMA 上斜(3根) 且低点抬高
    BEAR: close < EMA21 且 EMA 下斜(3根) 且高点降低
    返回：多头/空头/震荡
    """
    seg = bars[-tail:]
    if len(seg) < max(ema_period + slope_bars, 30):
        return "震荡"
    closes = [r[I_C] for r in seg]
    highs = [r[I_H] for r in seg]
    lows = [r[I_L] for r in seg]

    # EMA
    k = 2 / (ema_period + 1)
    ema = [closes[0]]
    for c in closes[1:]:
        ema.append(c * k + ema[-1] * (1 - k))
    ema_now = ema[-1]
    ema_before = ema[-1 - slope_bars]

    # HH/HL
    h_max = max(highs[-20:])
    h_prev = max(highs[-40:-20]) if len(highs) > 40 else h_max
    l_min = min(lows[-20:])
    l_prev = min(lows[-40:-20]) if len(lows) > 40 else l_min

    if closes[-1] > ema_now and ema_now > ema_before and l_min > l_prev:
        return "多头"
    if closes[-1] < ema_now and ema_now < ema_before and h_max < h_prev:
        return "空头"
    return "震荡"


def classify_trend(
    bars: list,
    method: str = "zigzag",
    **kwargs,
) -> str:
    """统一接口：按 method 分发到不同趋势判定方案。

    method: "zigzag" → detect_trend_zigzag
            "ema_slope" → detect_trend_ema_slope
    返回：多头/空头/震荡
    """
    if method == "zigzag":
        return detect_trend_zigzag(bars, **kwargs)
    if method == "ema_slope":
        return detect_trend_ema_slope(bars, **kwargs)
    return "震荡"


# ── 区间边界 ────────────────────────────────────────────────

def find_range_boundary(
    bars: list,
    lookback: int = 60,
    method: str = "swing",
    swing_left: int = 5,
    swing_right: int = 5,
) -> tuple[Optional[float], Optional[float]]:
    """区间上下边界检测（支撑三法之③）。

    method="swing": 最近两个摆动高点/低点（fractal 口径）
    method="percentile": P10-P90 分位带

    返回 (support, resistance) 或 (None, None)
    """
    seg = bars[-lookback:]
    if method == "percentile":
        closes = sorted(r[I_C] for r in seg)
        n = len(closes)
        if n < 10:
            return None, None
        lo_b = closes[int(n * 0.10)]
        hi_b = closes[min(n - 1, int(n * 0.90))]
        return lo_b, hi_b
    # swing 方法（默认）
    swings = find_swing_points(seg, swing_left, swing_right)
    highs = [s["price"] for s in swings if s["type"] == "H"]
    lows = [s["price"] for s in swings if s["type"] == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return None, None
    # 支撑 = 最近摆动低点中的较低者；压力 = 最近摆动高点中的较高者
    return min(lows[-2:]), max(highs[-2:])


# ── 支撑判定三法 ──────────────────────────────────────────────

def near_support(
    close: float,
    support: float,
    atr: float,
    tolerance_atr: float = 0.5,
) -> bool:
    """价格是否接近支撑位（距离 ≤ tolerance_atr × ATR）。"""
    if atr <= 0:
        return False
    return abs(close - support) <= tolerance_atr * atr


def near_resistance(
    close: float,
    resistance: float,
    atr: float,
    tolerance_atr: float = 0.5,
) -> bool:
    return abs(close - resistance) <= tolerance_atr * atr


def kline_density_zone(
    bars: list,
    lookback: int = 40,
    p_low: float = 0.10,
    p_high: float = 0.90,
) -> tuple[Optional[float], Optional[float]]:
    """K线密集区（分位带）：区间内收盘价 P10-P90 分位。

    返回 (zone_low, zone_high) 或 (None, None)。
    """
    seg = bars[-lookback:]
    closes = sorted(r[I_C] for r in seg)
    if len(closes) < 10:
        return None, None
    lo_b = closes[int(len(closes) * p_low)]
    hi_b = closes[min(len(closes) - 1, int(len(closes) * p_high))]
    return lo_b, hi_b


# ── 行情布局常量（模块级导入）────────────────────────────────

I_DT, I_O, I_H, I_L, I_C, I_V, I_OI = range(7)
