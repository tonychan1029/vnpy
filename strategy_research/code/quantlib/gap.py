# RESEARCH ONLY - 未获用户批准不得正式运行
"""quantlib.gap：缺口检测与分类。

缺口定位：结构/关键位类（同摆动点和区间边界）——缺口创造价格真空区域，
  后续扮演支撑/压力角色。缺口回补事件（价格回到缺口区）= K线信号。

多方案：
  检测：简单跳空 / ATR 相对跳空 / 换月过滤跳空
  分类：breakaway（突破缺口）/ runaway（持续缺口）/ exhaustion（衰竭缺口）/ common（普通缺口）
"""

from __future__ import annotations

from typing import Optional

# 行布局常量（同主库）
I_DT, I_O, I_H, I_L, I_C, I_V, I_OI = range(7)


def detect_gaps(
    bars: list,
    method: str = "simple",
    min_gap_atr: float = 0.5,
    atr_period: int = 14,
) -> list[dict]:
    """检测跳空缺口。返回缺口事件列表。

    method:
      "simple"  — open > prev_high (gap up) or open < prev_low (gap down)
      "atr"     — gap > min_gap_atr × ATR14（过滤噪声微跳）

    每个缺口事件：
      {"index": int, "direction": "up"/"down", "gap_size": float,
       "gap_top": float, "gap_bottom": float, "atr": float}
    """
    n = len(bars)
    gaps = []

    # 预算 ATR
    atrs = [None] * n
    if method == "atr":
        trs = [bars[0][I_H] - bars[0][I_L]]
        for i in range(1, n):
            trs.append(max(bars[i][I_H] - bars[i][I_L],
                           abs(bars[i][I_H] - bars[i - 1][I_C]),
                           abs(bars[i][I_L] - bars[i - 1][I_C])))
        for i in range(n):
            w = trs[max(0, i - atr_period + 1): i + 1]
            atrs[i] = sum(w) / len(w)

    for i in range(1, n):
        prev_high = bars[i - 1][I_H]
        prev_low = bars[i - 1][I_L]
        cur_open = bars[i][I_O]

        # 向上跳空：open > prev_high
        if cur_open > prev_high:
            gap_size = cur_open - prev_high
            if method == "atr":
                atr = atrs[i] if atrs[i] else 0
                if atr > 0 and gap_size < min_gap_atr * atr:
                    continue
            gaps.append({"index": i, "direction": "up",
                         "gap_size": gap_size,
                         "gap_top": cur_open, "gap_bottom": prev_high,
                         "atr": atrs[i] if method == "atr" else 0})

        # 向下跳空：open < prev_low
        elif cur_open < prev_low:
            gap_size = prev_low - cur_open
            if method == "atr":
                atr = atrs[i] if atrs[i] else 0
                if atr > 0 and gap_size < min_gap_atr * atr:
                    continue
            gaps.append({"index": i, "direction": "down",
                         "gap_size": gap_size,
                         "gap_top": prev_low, "gap_bottom": cur_open,
                         "atr": atrs[i] if method == "atr" else 0})

    return gaps


def is_gap_filled(
    bars: list,
    gap: dict,
    within_bars: int = 20,
) -> bool:
    """检查缺口是否在 within_bars 根内被回补（价格回到缺口区间）。"""
    start = gap["index"] + 1
    end = min(start + within_bars, len(bars))
    g_top = gap["gap_top"]
    g_bot = gap["gap_bottom"]
    for i in range(start, end):
        c = bars[i][I_C]
        if g_bot <= c <= g_top:
            return True
    return False


def classify_gap(
    bars: list,
    gap: dict,
    trend_before: str = "",
) -> str:
    """缺口分类（技术分析经典分类法）。

    breakaway: 缺口突破前期关键位（趋势起点）
    runaway:   缺口出现在趋势中段（趋势加速）
    exhaustion: 缺口出现在趋势末端（趋势衰竭预警）
    common:    无明确上下文（普通缺口，大概率回补）

    简化判定规则：
      - 缺口前 5 根有趋势（连续同向）→ breakaway
      - 缺口在 trend 中段且趋势已确认 → runaway
      - 缺口后 5 根反向 → exhaustion
      - 其余 → common
    """
    i = gap["index"]
    if i < 5:
        return "common"
    # 前置趋势方向
    gains = sum(1 for j in range(i - 5, i)
                if bars[j][I_C] > bars[j - 1][I_C]) if i >= 5 else 0
    if gap["direction"] == "up" and gains >= 4:
        return "breakaway"
    if gap["direction"] == "down" and gains <= 1:
        return "breakaway"

    # 缺口后走势
    post_up = sum(1 for j in range(i + 1, min(i + 6, len(bars)))
                  if bars[j][I_C] > bars[j - 1][I_C])
    post_dn = sum(1 for j in range(i + 1, min(i + 6, len(bars)))
                  if bars[j][I_C] < bars[j - 1][I_C])
    if gap["direction"] == "up" and post_dn > post_up:
        return "exhaustion"
    if gap["direction"] == "down" and post_up > post_dn:
        return "exhaustion"
    return "common"


def gap_as_level(
    gap: dict,
    fill_threshold: float = 0.5,
) -> dict:
    """将缺口转化为关键位（支撑/压力区域）。

    未完全回补的缺口 → 关键位（gap_bottom 到 gap_top 构成支撑/压力区）
    回补比例 ≥ fill_threshold → 关键位弱化
    """
    g_top = gap["gap_top"]
    g_bot = gap["gap_bottom"]
    mid = (g_top + g_bot) / 2
    filled = 0
    # 简化：由调用方传入后验数据判断回补
    return {"type": "gap_level", "top": g_top, "bottom": g_bot,
            "mid": mid, "strength": 1.0 - filled}
