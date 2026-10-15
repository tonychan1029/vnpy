# RESEARCH ONLY - quantlib.exhaustion：衰竭信号模块
"""衰竭信号：楔形三推 / 量价背离 / 抛售高潮。

行布局：bars 为 list[list]，7 元素：
  [0]=dt, [1]=open, [2]=high, [3]=low, [4]=close, [5]=volume, [6]=position
"""

from __future__ import annotations

# 行布局常量（全模块统一引用，禁止硬编码数字）
I_DT, I_O, I_H, I_L, I_C, I_V, I_OI = range(7)


def wedge_three_push(
    bars: list,
    window: int = 30,
    min_pushes: int = 3,
    decay_ratio: float = 0.67,
) -> dict | None:
    """信号#9 楔形三推：三段推幅递减（p3<p2<p1，第三推≤decay_ratio×第一推）。

    返回 {"direction": "short"（三推上升=看跌）/"long", "pushes": [p1,p2,p3]} 或 None。
    """
    if len(bars) < window:
        return None
    seg = bars[-window:]
    closes = [b[I_C] for b in seg]
    n = len(closes)
    if n < 10:
        return None

    # 找局部极值（简化：3根窗口局部极值）
    piv_h, piv_l = [], []
    for i in range(2, n - 2):
        if closes[i] > closes[i - 1] and closes[i] >= closes[i + 1]:
            piv_h.append((i, closes[i]))
        if closes[i] < closes[i - 1] and closes[i] <= closes[i + 1]:
            piv_l.append((i, closes[i]))

    if len(piv_h) >= 3:
        p1, p2, p3 = piv_h[-3], piv_h[-2], piv_h[-1]
        if p1[1] > p2[1] > p3[1]:
            return {"direction": "short", "pushes": [p1[1], p2[1], p3[1]]}

    if len(piv_l) >= 3:
        p1, p2, p3 = piv_l[-3], piv_l[-2], piv_l[-1]
        if p1[1] < p2[1] < p3[1]:
            return {"direction": "long", "pushes": [p1[1], p2[1], p3[1]]}
    return None


def volume_divergence(
    bars: list,
    lookback: int = 20,
) -> str | None:
    """量价背离：价格创新高但成交量萎缩（看跌背离），或价格创新低但量缩（看涨背离）。

    返回 "bearish" / "bullish" / None。
    """
    if len(bars) < lookback + 5:
        return None
    seg = bars[-lookback:]
    closes = [b[I_C] for b in seg]
    volumes = [b[I_V] for b in seg]

    half = lookback // 2
    price_first = sum(closes[:half]) / half
    price_second = sum(closes[half:]) / half
    vol_first = sum(volumes[:half]) / half
    vol_second = sum(volumes[half:]) / half

    price_up = price_second > price_first
    vol_down = vol_second < vol_first

    if price_up and vol_down:
        return "bearish"  # 价涨量缩 → 上涨动能衰竭
    if not price_up and vol_down:
        return "bullish"  # 价跌量缩 → 抛压减轻
    return None


def selling_climax(
    bars: list,
    atr: float,
    vol_mult: float = 2.0,
) -> bool:
    """抛售高潮：单根大幅下跌 + 成交量 ≥ vol_mult × 前期均量。

    返回 True = 检测到抛售高潮。
    """
    if len(bars) < 2 or atr <= 0:
        return False
    cur = bars[-1]
    prev_c = bars[-2][I_C]
    body = prev_c - cur[I_C]  # 阴线跌幅
    avg_vol = sum(b[I_V] for b in bars[-21:-1]) / min(20, len(bars) - 1)
    if avg_vol <= 0:
        return False
    vol_ratio = cur[I_V] / avg_vol
    return body > 2 * atr and vol_ratio >= vol_mult
