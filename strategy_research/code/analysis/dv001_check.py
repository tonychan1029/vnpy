# RESEARCH ONLY - 未获用户批准不得正式运行
"""M-DV-001 反弹放量+探底缩量：操作化检验与条件分解。

操作化（与 MLIB 定义 v1 对应，参数显式化）：
- 窗口 10 根；探底K = 当根 low 为窗口新低；反弹K = 当根 close > open
- 条件A（反弹放量）：反弹K rvol 均值 / 探底K rvol 均值 >= 1.5（各至少 2 根）
- 条件B（探底缩量）：当根为新低K 且 rvol <= 0.8
- 三组对照：A+B（完整 M-DV-001）/ 仅B / 全部新低K（无条件）
前瞻 5/10/20 根，6 品种合并。诊断性实验。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MLIB"

SYMBOLS = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
           "CU": DATA / "SHFE" / "CU" / "CU.csv",
           "AG": DATA / "SHFE" / "AG" / "AG.csv",
           "M": DATA / "DCE" / "M" / "M.csv",
           "MA": DATA / "CZCE" / "MA" / "MA.csv",
           "TA": DATA / "CZCE" / "TA" / "TA.csv"}
HORIZONS = (5, 10, 20)
W = 10


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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = defaultdict(lambda: defaultdict(list))   # group -> hz -> [(sym, ret)]
    for sym, path in SYMBOLS.items():
        dts, o, h, l, c, v = load(path)
        n = len(c)
        v20 = [None] * n
        for i in range(19, n):
            v20[i] = sum(v[i - 19:i + 1]) / 20
        for i in range(W, n - max(HORIZONS)):
            if v20[i] in (None, 0):
                continue
            win_l = l[i - W + 1:i + 1]
            if l[i] > min(win_l):                  # 只看新低K
                continue
            rvol_i = v[i] / v20[i]
            dip_r, reb_r = [], []
            for j in range(i - W + 1, i + 1):
                if v20[j] in (None, 0):
                    continue
                r = v[j] / v20[j]
                if l[j] <= min(win_l):
                    dip_r.append(r)
                if c[j] > o[j]:
                    reb_r.append(r)
            cond_b = rvol_i <= 0.8
            close_pos = (c[i] - l[i]) / max(h[i] - l[i], 1e-9)
            cond_v2 = cond_b and close_pos >= 0.66      # v2 草案：B + 收盘位置
            cond_a = (len(dip_r) >= 2 and len(reb_r) >= 2
                      and sum(reb_r) / len(reb_r) /
                      max(sum(dip_r) / len(dip_r), 1e-9) >= 1.5)
            groups = ["all_dip"]
            if cond_b:
                groups.append("B_only")
                if cond_a:
                    groups.append("A_plus_B")
            if cond_v2:
                groups.append("v2_draft")
            for g in groups:
                for hz in HORIZONS:
                    res[g][hz].append((sym, c[i + hz] / c[i] - 1))
    lines = ["# M-DV-001 操作化检验（10根窗口，新低K 入场口径）", "",
             "| 组 | 条件 | 5根 n/均值 | 10根 n/均值 | 20根 n/均值 | 20根胜率 |",
             "|---|---|---|---|---|---|"]
    for g, name in (("A_plus_B", "A+B 完整(v1)"), ("B_only", "仅B 探底缩量"),
                    ("v2_draft", "v2草案 B+收盘位置"),
                    ("all_dip", "全部新低K")):
        cells = []
        for hz in HORIZONS:
            xs = res[g][hz]
            rets = [r for _, r in xs]
            cells.append(f"{len(rets)}/{sum(rets) / len(rets) * 100:.3f}%" if rets else "-")
        r20 = [r for _, r in res[g][20]]
        win = f"{sum(1 for r in r20 if r > 0) / len(r20) * 100:.1f}%" if r20 else "-"
        lines.append(f"| {name} | " +
                     ("A≥1.5 且 B≤0.8" if g == "A_plus_B" else
                      "B≤0.8 且 收盘≥上1/3" if g == "v2_draft" else
                      "B≤0.8" if g == "B_only" else "无") +
                     " | " + " | ".join(cells) + f" | {win} |")
    lines.append("")
    lines.append("## 分品种 20 根")
    lines.append("| 品种 | v1(A+B) n/均值 | v2草案 n/均值 | 仅B n/均值 | 全部 n/均值 |")
    lines.append("|---|---|---|---|---|")
    for sym in SYMBOLS:
        row = [sym]
        for g in ("A_plus_B", "v2_draft", "B_only", "all_dip"):
            xs = [r for s, r in res[g][20] if s == sym]
            row.append(f"{len(xs)}/{sum(xs) / len(xs) * 100:.3f}%" if xs else "-")
        lines.append("| " + " | ".join(row) + " |")
    (OUT / "dv001_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", OUT / "dv001_check.md")


if __name__ == "__main__":
    main()
