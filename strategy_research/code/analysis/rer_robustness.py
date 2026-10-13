# RESEARCH ONLY - 未获用户批准不得正式运行
"""RANGE_EDGE_REVERSAL 品种/年度分布（及格待扩样项的稳健性前置检查）。"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    by_sym = defaultdict(list)
    by_year = defaultdict(list)
    in_out = defaultdict(list)
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["signal_id"] != "RANGE_EDGE_REVERSAL":
                continue
            net = r.get("p1_net_r")
            if net in ("", None):
                continue
            net = float(net)
            by_sym[r["symbol"]].append(net)
            try:
                y = datetime.strptime(r["bar_time"],
                                      "%Y-%m-%d %H:%M:%S").year
                by_year[y].append(net)
            except ValueError:
                pass
            io = "in" if r.get("in_sample") == "1" else "out"
            in_out[io].append(net)
    lines = ["# RANGE_EDGE_REVERSAL 稳健性前置检查（p1_net_r）", "",
             "## 分品种", "| 品种 | n | 胜率 | 平均净R |", "|---|---|---|---|"]
    for sym in sorted(by_sym):
        xs = by_sym[sym]
        win = sum(1 for x in xs if x > 0) / len(xs) * 100
        lines.append(f"| {sym} | {len(xs)} | {win:.1f}% | "
                     f"{sum(xs) / len(xs):+.3f} |")
    lines += ["", "## 分年度", "| 年 | n | 平均净R |", "|---|---|---|"]
    for y in sorted(by_year):
        xs = by_year[y]
        lines.append(f"| {y} | {len(xs)} | {sum(xs) / len(xs):+.3f} |")
    lines += ["", "## in/out", "| 段 | n | 平均净R |", "|---|---|---|"]
    for io in ("in", "out"):
        xs = in_out.get(io, [])
        if xs:
            lines.append(f"| {io} | {len(xs)} | {sum(xs) / len(xs):+.3f} |")
    lines += ["", "判读：正收益若集中于 1-2 品种或 1 年，则'及格待扩样'降级为"
              "'未证实'；若分散且方向一致，扩样（信号参数放宽）才值得立项。"]
    (OUT / "rer_robustness.md").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    print("->", OUT / "rer_robustness.md")


if __name__ == "__main__":
    main()
