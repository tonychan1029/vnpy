# RESEARCH ONLY - 未获用户批准不得正式运行
"""M-TR-002 trend_score 实证检验：方向闸门是否有预测力。

口径：非重叠采样（步长 20），因子 = dir × score（-100..100，因果），
跨品种合并百分位秩 IC + 用法阈值分桶（<40 放弃 / 40-70 可做 / >=70 强趋势，
按 dir 取向的前瞻收益）。ATR14。多周期一致性项退化 0.5（与现网一致）。
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from methods.pa_methods import m_pt_001_confirmed_pivots  # noqa: E402
from methods.trend_score import trend_score  # noqa: E402

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = ROOT.parent / "assets" / "MLIB"

SYMBOLS = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
           "CU": DATA / "SHFE" / "CU" / "CU.csv",
           "AG": DATA / "SHFE" / "AG" / "AG.csv",
           "M": DATA / "DCE" / "M" / "M.csv",
           "MA": DATA / "CZCE" / "MA" / "MA.csv",
           "TA": DATA / "CZCE" / "TA" / "TA.csv"}
H = 20
HORIZONS = (20, 40)


def load(path):
    dts, o, h, l, c, v = [], [], [], [], [], []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dts.append(r["datetime"])
            o.append(float(r["open"]))
            h.append(float(r["high"]))
            l.append(float(r["low"]))
            c.append(float(r["close"]))
            v.append(float(r["volume"]))
    return dts, o, h, l, c, v


def pct_ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    for rank, i in enumerate(order):
        out[i] = rank / max(len(vals) - 1, 1)
    return out


def pearson(xs, ys):
    n = len(xs)
    if n < 30:
        return None, n
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs) ** 0.5
    vy = sum((b - my) ** 2 for b in ys) ** 0.5
    return (cov / (vx * vy)) if vx and vy else None, n


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    per_sym = {}
    for sym, path in SYMBOLS.items():
        dts, o, h, l, c, v = load(path)
        n = len(c)
        tr = [h[i] - l[i] if i == 0 else
              max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
              for i in range(n)]
        pivots = m_pt_001_confirmed_pivots(h, l, k=2)
        samples = []                      # (i, signed_score)
        for i in range(60, n - max(HORIZONS), H):
            atr = sum(tr[i - 13:i + 1]) / 14
            pi = [p for p in pivots if p.index <= i - 2]
            if len(pi) < 2:
                continue
            direction, score = trend_score(c[:i + 1], h[:i + 1], l[:i + 1],
                                           pi, atr)
            if direction == 0 or score <= 0:
                continue
            samples.append((i, dts[i], direction * score))
        per_sym[sym] = (c, samples)
    # 合并秩 IC（品种内百分位秩 vs 前瞻收益）
    lines = ["# M-TR-002 trend_score 实证检验（非重叠 H=20，因子=dir×score）", ""]
    for hz in HORIZONS:
        xs, ys = [], []
        for sym, (c, samples) in per_sym.items():
            valid = [(i, s) for i, _, s in samples if i + hz < len(c)]
            if len(valid) < 30:
                continue
            ranks = pct_ranks([s for _, s in valid])
            for (i, _), rk in zip(valid, ranks):
                xs.append(rk)
                ys.append(c[i + hz] / c[i] - 1)
        ic, n = pearson(xs, ys)
        lines.append(f"- 前瞻 {hz} 根：pooled rank IC = **{ic:+.3f}** (n={n})"
                     if ic is not None else f"- 前瞻 {hz} 根：n 不足")
    # 阈值分桶（用法口径：dir 取向前瞻收益）
    lines += ["", "## 用法阈值分桶（dir 取向，dir=-1 时收益取负即空头方向收益）", "",
              "| score 桶 | 前瞻 | n | 胜率 | 平均方向收益 |", "|---|---|---|---|---|"]
    buckets = {"<40 放弃线": lambda s: abs(s) < 40,
               "40-70 可做": lambda s: 40 <= abs(s) < 70,
               ">=70 强趋势": lambda s: abs(s) >= 70}
    for name, fn in buckets.items():
        for hz in (HORIZONS[0],):
            rets = []
            for sym, (c, samples) in per_sym.items():
                for i, _, s in samples:
                    if fn(s) and i + hz < len(c):
                        rets.append((1 if s > 0 else -1) *
                                    (c[i + hz] / c[i] - 1))
            if rets:
                win = sum(1 for r in rets if r > 0) / len(rets)
                lines.append(f"| {name} | {hz}根 | {len(rets)} | "
                             f"{win * 100:.1f}% | {sum(rets) / len(rets) * 100:.3f}% |")
    # 分数单调性（十分位）
    lines += ["", "## 分数十分位单调性（|score| 十分位 -> dir 取向 20 根收益）", "",
              "| |score| 分位 | n | 平均方向收益 |", "|---|---|---|---|"]
    allpairs = []
    for sym, (c, samples) in per_sym.items():
        for i, _, s in samples:
            if i + 20 < len(c):
                allpairs.append((abs(s), (1 if s > 0 else -1) *
                                 (c[i + 20] / c[i] - 1)))
    if allpairs:
        allpairs.sort(key=lambda x: x[0])
        m = len(allpairs) // 10
        for d in range(10):
            seg = allpairs[d * m:(d + 1) * m if d < 9 else len(allpairs)]
            lines.append(f"| D{d + 1} | {len(seg)} | "
                         f"{sum(r for _, r in seg) / len(seg) * 100:.3f}% |")
    (OUT / "trend_score_check.md").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")
    print("->", OUT / "trend_score_check.md")


if __name__ == "__main__":
    main()
