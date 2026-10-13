# RESEARCH ONLY - 未获用户批准不得正式运行
"""DOUBLE_BOTTOM 负年共性解剖（MTG004 优化首任务）。

从 signals_detail 逐笔行取 DOUBLE_BOTTOM，输出：
1) 品种×年 avg_net_r(p1) 矩阵（定位负年负品种集中度）
2) 负年 vs 正年的结构差异：触发率、方向分布、context_tag 分布
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cell = defaultdict(list)              # (sym, year) -> [net_r(p1), trig]
    tagcnt = defaultdict(lambda: defaultdict(int))   # year -> tag -> n
    dircnt = defaultdict(lambda: defaultdict(int))   # year -> dir -> n
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["signal_id"] != "DOUBLE_BOTTOM":
                continue
            try:
                dt = datetime.strptime(r["bar_time"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            year = dt.year
            net = r.get("p1_net_r")
            netv = float(net) if net not in ("", None) else None
            trig = 1 if r.get("p1_outcome") else 0
            cell[(r["symbol"], year)].append((netv, trig))
            tagcnt[year][r.get("context_tag") or "empty"] += 1
            dircnt[year][r["direction"]] += 1
    syms = sorted({s for s, _ in cell})
    years = sorted({y for _, y in cell})
    lines = ["# DOUBLE_BOTTOM 负年解剖（品种×年，avg p1_net_r / n）", "",
             "| 年 | " + " | ".join(syms) + " | 年均 |", "|---|" + "---|" * (len(syms) + 1)]
    neg_years = {2015, 2018, 2023, 2024}
    for y in years:
        cells = []
        tot = []
        for s in syms:
            xs = cell.get((s, y))
            if xs:
                nets = [x[0] for x in xs if x[0] is not None]
                m = sum(nets) / len(nets) if nets else None
                tot.extend(nets)
                mark = " ❌" if (m is not None and m < -0.15) else ""
                cells.append(f"{m:.3f}/{len(nets)}{mark}" if m is not None else "-")
            else:
                cells.append("-")
        avg = sum(tot) / len(tot) if tot else 0
        flag = " ❌负年" if y in neg_years else ""
        lines.append(f"| {y}{flag} | " + " | ".join(cells) +
                     f" | {avg:.3f} |")
    lines.append("")
    lines.append("## 负年 vs 正年结构对比")
    lines.append("| 年组 | 指标 | 值 |")
    lines.append("|---|---|---|")
    for name, ys in (("负年", neg_years), ("正年", set(years) - neg_years)):
        trig_all = [t for (s, y), xs in cell.items() if y in ys
                    for t in [x[1] for x in xs]]
        tr = sum(trig_all) / len(trig_all) * 100 if trig_all else 0
        short = sum(dircnt[y].get("short", 0) for y in ys)
        long_ = sum(dircnt[y].get("long", 0) for y in ys)
        lines.append(f"| {name} | 触发率 | {tr:.1f}% |")
        lines.append(f"| {name} | 空/多 | {short}/{long_} |")
    lines.append("")
    lines.append("## 负年 context_tag 分布（v0）")
    for y in sorted(neg_years):
        tot = sum(tagcnt[y].values()) or 1
        parts = ", ".join(f"{k}:{v / tot * 100:.0f}%"
                          for k, v in sorted(tagcnt[y].items(),
                                             key=lambda kv: -kv[1])[:3])
        lines.append(f"- {y}: {parts}")
    (OUT / "db_negative_anatomy.md").write_text("\n".join(lines) + "\n",
                                                encoding="utf-8")
    print("->", OUT / "db_negative_anatomy.md")


if __name__ == "__main__":
    main()
