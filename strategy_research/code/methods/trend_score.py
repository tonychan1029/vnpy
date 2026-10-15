# RESEARCH ONLY - 未获用户批准不得正式运行
"""MLIB 趋势强度研究级实现（M-TR-002 v1）。定义以登记册为单一事实来源。"""

from __future__ import annotations

import math


def ema(values: list[float], period: int = 20) -> list[float]:
    k = 2 / (period + 1)
    out: list[float] = []
    e: float | None = None
    for v in values:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def _swing_compliance(pivots: list, direction: int,
                      lookback: int = 4) -> float:
    """摆动点递进合规率（方向感知，阶段0-4 勘误）。

    多头（direction=+1）按 HH/HL（递增）统计；空头（−1）按 LH/LL（递减）
    统计——旧版仅统计递增，空头趋势 score 被系统性低估约 25%（权重 0.25），
    违反 M-TR-002 "HH/HL 或 LL/LH" 定义。
    """
    hs = [p for p in pivots if p.kind == "H"][-lookback:]
    ls = [p for p in pivots if p.kind == "L"][-lookback:]
    checks = 0
    ok = 0
    for a, b in zip(hs, hs[1:]):
        checks += 1
        ok += (b.price > a.price) if direction > 0 else (b.price < a.price)
    for a, b in zip(ls, ls[1:]):
        checks += 1
        ok += (b.price > a.price) if direction > 0 else (b.price < a.price)
    return ok / checks if checks else 0.5   # 无信息时取中性


def trend_score(closes: list[float], highs: list[float], lows: list[float],
                pivots: list, atr: float, period: int = 20,
                higher_tf_dir: int | None = None) -> tuple[int, float]:
    """M-TR-002：返回 (dir, score)。

    dir = +1/-1（EMA 斜率方向）；score ∈ [0,100]。
    higher_tf_dir：大周期方向（+1/-1/None），None 时一致性项记 0.5。
    """
    if len(closes) < period + 5 or atr <= 0:
        return 0, 0.0
    e = ema(closes, period)
    slope = e[-1] - e[-5]
    direction = 1 if slope > 0 else -1

    c_slope = math.tanh(abs(slope) / atr / 2)
    c_swing = _swing_compliance(pivots, direction)
    window = closes[-period:]
    path = sum(abs(window[i] - window[i - 1]) for i in range(1, len(window)))
    c_er = (abs(window[-1] - window[0]) / path) if path > 0 else 0.0
    age_bars = 0
    for i in range(len(e) - 1, 0, -1):
        if (e[i] - e[i - 1]) * direction < 0:
            age_bars = len(e) - 1 - i
            break
    c_age = math.exp(-age_bars / (3 * period))
    c_mtf = (1.0 if higher_tf_dir == direction else 0.0) if higher_tf_dir else 0.5

    score = 100 * (0.30 * c_slope + 0.25 * c_swing + 0.25 * c_er
                   + 0.10 * c_age + 0.10 * c_mtf)
    return direction, round(score, 1)
