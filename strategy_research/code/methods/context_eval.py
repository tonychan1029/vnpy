# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS012 真值标注器与混淆矩阵协议（context_tag 判定准确率实验，验证队列 #1）。

真值只用 as_of 之后数据；判定标签（引擎 context_tag）由调用方按相同
时间戳对齐传入。与工程代码零依赖。
"""

from __future__ import annotations

from dataclasses import dataclass

GT_LABELS = ("TREND_UP", "TREND_DN", "RANGE", "BREAKOUT", "REVERSAL", "UNDEFINED")


@dataclass
class GroundTruth:
    label: str
    horizon: int          # 判定用到的根数（不足 horizon 时含未完结惩罚由调用方处理）


def ground_truth_label(closes: list[float], atr: float, as_of: int,
                       horizon: int = 20, consist: float = 0.6) -> GroundTruth:
    """RS012 §1 操作性真值 v1.1：只用 as_of 之后 horizon 根的已实现路径。

    优先级（v1.1 修订，防序偏差）：
    1. TREND_UP/DN：净位移 >= 2xATR 且方向根占比 >= consist
    2. RANGE：净位移 < 1xATR 且未破前 40 根区间边缘
    3. BREAKOUT：突破前 40 根边缘且顺势走出 >= 2xATR
    4. REVERSAL：往返形态——上、下行 Excursion 各 >= 1.5xATR 且净位移 < 1.5xATR
    5. UNDEFINED：其余
    """
    fwd = closes[as_of + 1: as_of + 1 + horizon]
    if len(fwd) < horizon or atr <= 0:
        return GroundTruth("UNDEFINED", len(fwd))
    base = closes[as_of]
    net = fwd[-1] - base
    ups = sum(1 for a, b in zip(fwd, fwd[1:]) if b > a)
    total = max(len(fwd) - 1, 1)
    pre = closes[max(0, as_of - 40): as_of + 1]
    hi40, lo40 = (max(pre), min(pre)) if pre else (base, base)

    # 1. TREND（最优先：净位移+一致性双条件；一致性按净位移方向计）
    if abs(net) >= 2 * atr:
        consistency = (ups / total) if net > 0 else (1 - ups / total)
        if consistency >= consist:
            return GroundTruth("TREND_UP" if net > 0 else "TREND_DN", horizon)

    # 2. RANGE（严格：小区间内）
    if abs(net) < 1 * atr and max(fwd) <= hi40 and min(fwd) >= lo40:
        return GroundTruth("RANGE", horizon)

    # 3. REVERSAL v1.1：往返——两段相反各 >= 1.5ATR，且净位移收窄（走了又回来）。
    #    置于 BREAKOUT 之前：破位 2ATR 又完整回落=失败突破，归 REVERSAL 而非 BREAKOUT
    best = 0.0
    for k in range(1, horizon):
        seg1, seg2 = fwd[:k], fwd[k:]
        m1 = seg1[-1] - fwd[0]
        m2 = seg2[-1] - seg2[0]
        if m1 * m2 < 0:
            best = max(best, min(abs(m1), abs(m2)) / atr)
    if best >= 1.5 and abs(net) < 1.5 * atr:
        return GroundTruth("REVERSAL", horizon)

    # 4. BREAKOUT（顺势突破前 40 根边缘 >= 2ATR）
    if max(fwd) > hi40 and max(fwd) - hi40 >= 2 * atr:
        return GroundTruth("BREAKOUT", horizon)
    if min(fwd) < lo40 and lo40 - min(fwd) >= 2 * atr:
        return GroundTruth("BREAKOUT", horizon)

    return GroundTruth("UNDEFINED", horizon)


def agreement_matrix(gts: list[str], preds: list[str],
                     labels: tuple = GT_LABELS) -> dict:
    """混淆矩阵协议：返回 {gt: {pred: count}} 与每 GT 类的 top-pred 精确率。"""
    m: dict = {g: {p: 0 for p in labels} for g in labels}
    for g, p in zip(gts, preds):
        if g in m and p in m[g]:
            m[g][p] += 1
    prec: dict = {}
    for g in labels:
        tot = sum(m[g].values())
        prec[g] = round(max(m[g].values()) / tot, 3) if tot else None
    return {"matrix": m, "top_pred_precision": prec}
