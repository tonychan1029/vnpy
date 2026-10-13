# RESEARCH ONLY - 未获用户批准不得正式运行
"""by_year p1 补齐：工程侧 by_year 只导出 p0 档，本脚本从 signals_detail
逐笔 p1_net_r 重建 信号×年 矩阵（均值/胜率/n），并给每信号的 in/out 汇总对照。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"

SIGNALS = ("BREAKOUT_KEY_LEVEL", "DOUBLE_BOTTOM", "DOUBLE_TOP",
           "EMA20_PULLBACK", "FAKE_BREAKOUT_REVERSE", "H2L2_TREND",
           "RANGE_EDGE_REVERSAL", "STRUCTURE_PULLBACK", "WEDGE_THREE_PUSH")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cell = defaultdict(lambda: defaultdict(list))   # sig -> year -> [r]
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sig = r["signal_id"]
            if sig not in SIGNALS:
                continue
            net = r.get("p1_net_r")
            if net in ("", None):
                continue
            try:
                y = datetime.strptime(r["bar_time"],
                                      "%Y-%m-%d %H:%M:%S").year
            except ValueError:
                continue
            cell[sig][y].append(float(net))
    years = sorted({y for s in cell for y in cell[s]})
    lines = ["# by_year p1 补齐（信号×年，avg p1_net_r R / n；研究侧重建）", ""]
    for sig in SIGNALS:
        lines.append(f"## {sig}")
        lines.append("| 年 | avg | n | 胜率 |")
        lines.append("|---|---|---|---|")
        tot = []
        for y in years:
            xs = cell[sig].get(y)
            if not xs:
                continue
            tot.extend(xs)
            win = sum(1 for x in xs if x > 0) / len(xs) * 100
            mark = " ❌" if sum(xs) / len(xs) < -0.05 else ""
            lines.append(f"| {y}{mark} | {sum(xs) / len(xs):+.3f} | "
                         f"{len(xs)} | {win:.1f}% |")
        if tot:
            win = sum(1 for x in tot if x > 0) / len(tot) * 100
            lines.append(f"| **合计** | **{sum(tot) / len(tot):+.3f}** | "
                         f"{len(tot)} | {win:.1f}% |")
        neg = [y for y in years if cell[sig].get(y)
               and sum(cell[sig][y]) / len(cell[sig][y]) < -0.05]
        lines.append(f"- 负年（<−0.05R）：{', '.join(map(str, neg)) or '无'}")
        lines.append("")
    (OUT / "by_year_p1.md").write_text("\n".join(lines) + "\n",
                                       encoding="utf-8")
    print("->", OUT / "by_year_p1.md")


if __name__ == "__main__":
    main()
