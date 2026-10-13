# RESEARCH ONLY - 未获用户批准不得正式运行
"""RER 扩样分析：RangeEdge 形态去掉 v0 range 标签闸门后的表现。

现网判据（detectors.py RangeEdgeDetector）：
  ① 引擎 range 标签（闸门，0.9% 触发——稀缺根源）
  ② 触及 range_bottom/top（确认摆动点 + 0.25×ATR 容差）
  ③ 反转K：pin（影线≥2×实体 且 收盘在区间上/下 1/3）或 吞没
研究侧近似：摆动点（M-PT-001, k=2）为 range 沿；对照
  A 现网口径（② + ③ + ①）
  B 无标签口径（② + ③）
前瞻 20 根（毛口径，另注成本线 −0.0006）。假设：B 样本扩而边际保留
（则 HO003-A1 落地后 RER 自动扩样且有效）。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
TAGS = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"
COST = 0.0006

SYMBOLS = {"RB": (DATA / "SHFE" / "RB" / "RB.csv", TAGS / "RB_context_tags.csv"),
           "CU": (DATA / "SHFE" / "CU" / "CU.csv", TAGS / "CU_context_tags.csv"),
           "AG": (DATA / "SHFE" / "AG" / "AG.csv", TAGS / "AG_context_tags.csv"),
           "M": (DATA / "DCE" / "M" / "M.csv", TAGS / "M_context_tags.csv"),
           "MA": (DATA / "CZCE" / "MA" / "MA.csv", TAGS / "MA_context_tags.csv"),
           "TA": (DATA / "CZCE" / "TA" / "TA.csv", TAGS / "TA_context_tags.csv")}
HZ = 20
TOL_K = 0.25


def pin(h, l, o, c, bull):
    body = abs(c - o)
    rng = h - l
    if rng <= 0 or body <= 0:
        return False
    lower = min(o, c) - l
    upper = h - max(o, c)
    if bull:
        return lower >= 2 * body and c >= l + rng / 3
    return upper >= 2 * body and c <= h - rng / 3


def engulf(o, c, po, pc, bull):
    if (pc > po) == bull:
        return False
    return min(o, c) <= min(po, pc) and max(o, c) >= max(po, pc)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = defaultdict(lambda: defaultdict(list))   # arm -> dir -> [ret]
    for sym, (dpath, tpath) in SYMBOLS.items():
        dts, o, h, l, c = [], [], [], [], []
        with dpath.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(r["datetime"])
                o.append(float(r["open"]))
                h.append(float(r["high"]))
                l.append(float(r["low"]))
                c.append(float(r["close"]))
        n = len(c)
        tr = [h[i] - l[i] if i == 0 else
              max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
              for i in range(n)]
        atr = [None] * n
        for i in range(13, n):
            atr[i] = sum(tr[i - 13:i + 1]) / 14
        tags = [None] * n
        strict = [0] * n
        idx = {d: i for i, d in enumerate(dts)}
        with tpath.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                i = idx.get(r["datetime"])
                if i is not None:
                    tags[i] = (r.get("context_tag") or "").strip().lower()
                    strict[i] = int(r.get("strict_range") or 0)
        pivL = [i for i in range(2, n - 2)
                if all(l[i] < l[j] for j in range(i - 2, i + 3) if j != i)]
        pivH = [i for i in range(2, n - 2)
                if all(h[i] > h[j] for j in range(i - 2, i + 3) if j != i)]
        fired = set()
        for i in range(20, n - HZ):
            a = atr[i]
            if a in (None, 0):
                continue
            tol = TOL_K * a
            for side, piv, lvl, bull in (("long", pivL, "bottom", True),
                                         ("short", pivH, "top", False)):
                recent = [p for p in piv if 0 < i - p <= 60]
                hit = None
                for p in recent:
                    px = l[p] if side == "long" else h[p]
                    if side == "long" and l[i] <= px + tol:
                        hit = px
                        break
                    if side == "short" and h[i] >= px - tol:
                        hit = px
                        break
                if hit is None:
                    continue
                rev = (pin(h[i], l[i], o[i], c[i], bull)
                       or engulf(o[i], c[i], o[i - 1], c[i - 1], bull))
                if not rev:
                    continue
                key = (sym, i, side)
                if key in fired:
                    continue
                fired.add(key)
                ret = (c[i + HZ] / c[i] - 1) * (1 if side == "long" else -1) - COST
                res["B_notag"][side].append(ret)
                if tags[i] == "range":
                    res["A_v1range"][side].append(ret)
                if strict[i] == 1:
                    res["C_strict"][side].append(ret)
    lines = ["# RER 扩样分析（RangeEdge 形态 × 有/无 v0 range 标签闸门）", "",
             f"前瞻 {HZ} 根、方向调整后、扣双边万3；形态=摆动沿触及+pin/吞没", "",
             "| 口径 | 方向 | n | 胜率 | 平均净R* |", "|---|---|---|---|---|",
             "*此处为收益率口径（非基线 R 单位），与基线不可直接比；只比 A vs B。", ""]
    for arm in ("A_v1range", "C_strict", "B_notag"):
        name = {"A_v1range": "A v1 range 标签",
                "C_strict": "C v1 strict_range 子态",
                "B_notag": "B 无标签（裸形态）"}[arm]
        for side in ("long", "short"):
            xs = res[arm][side]
            if not xs:
                lines.append(f"| {name} | {side} | 0 | - | - |")
                continue
            win = sum(1 for x in xs if x > 0) / len(xs) * 100
            lines.append(f"| {name} | {side} | {len(xs)} | {win:.1f}% | "
                         f"{sum(xs) / len(xs) * 100:.3f}% |")
    lines += ["", "判读：B 样本较 A 扩 N 倍且均收益仍为正（扣费后）→ HO003-A1 "
              "落地后 RER 自动扩样且有效；B 为负 → 形态依赖 range 标签环境，"
              "扩样仅靠标签放宽不足。"]
    (OUT / "rer_expand.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", OUT / "rer_expand.md")


if __name__ == "__main__":
    main()
