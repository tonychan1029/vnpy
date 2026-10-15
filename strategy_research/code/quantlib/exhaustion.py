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
    decay_ratio: float = 0.67,
) -> dict | None:
    """信号#9 三推楔形（幅度衰减版；语义对齐生产 WedgeThreePushDetector）。

    上升三推=short：依次抬高的三个摆动高点 H1<H2<H3，各推幅
    amp_i = H_i − 其前低；amp1>amp2>amp3 且 amp3 ≤ decay_ratio×amp1
    （动能衰竭）。下降三推=long 镜像（L1>L2>L3，amp 为前高到 L_i 幅度）。
    返回 {"direction": "short"/"long", "pushes": [amp1,amp2,amp3]} 或 None。

    勘误（2026-10-15 阶段0-4）：旧版用价格序（H1>H2>H3 判 short）且
    decay_ratio 死参数——与定义/生产分叉，本版改为幅度衰减口径并启用参数。
    """
    if len(bars) < window:
        return None
    seg = bars[-window:]
    closes = [b[I_C] for b in seg]
    n = len(closes)
    if n < 10:
        return None

    # 局部极值（3 根窗口）→ 压缩为交替序列（同类取更极端者）
    ext = []
    for i in range(2, n - 2):
        if closes[i] > closes[i - 1] and closes[i] >= closes[i + 1]:
            ext.append([i, "H", closes[i]])
        if closes[i] < closes[i - 1] and closes[i] <= closes[i + 1]:
            ext.append([i, "L", closes[i]])
    alt: list[list] = []
    for e in ext:
        if alt and alt[-1][1] == e[1]:
            if (e[1] == "H" and e[2] >= alt[-1][2]) or \
                    (e[1] == "L" and e[2] <= alt[-1][2]):
                alt[-1] = e
        else:
            alt.append(e)

    def push_amps(pivots3, opposite):
        amps = []
        for p in pivots3:
            prev = [x for x in opposite if x[0] < p[0]]
            base = prev[-1][2] if prev else None
            if base is None:
                base = min(closes) if p[1] == "H" else max(closes)
            amps.append(abs(p[2] - base))
        return amps

    hs = [e for e in alt if e[1] == "H"][-3:]
    ls_all = [e for e in alt if e[1] == "L"]
    if len(hs) == 3 and hs[0][2] < hs[1][2] < hs[2][2]:
        amps = push_amps(hs, ls_all)
        if amps[0] > 0 and amps[0] > amps[1] > amps[2] and \
                amps[2] <= decay_ratio * amps[0]:
            return {"direction": "short", "pushes": amps}

    ls = [e for e in alt if e[1] == "L"][-3:]
    hs_all = [e for e in alt if e[1] == "H"]
    if len(ls) == 3 and ls[0][2] > ls[1][2] > ls[2][2]:
        amps = push_amps(ls, hs_all)
        if amps[0] > 0 and amps[0] > amps[1] > amps[2] and \
                amps[2] <= decay_ratio * amps[0]:
            return {"direction": "long", "pushes": amps}
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
