# RESEARCH ONLY - 未获用户批准不得正式运行
"""市场级 regime 过滤原型：池内 breadth × DOUBLE_BOTTOM 负年拦截力。

breadth(t) = 6 品种中 prior_ret20>0 的占比（等权，逐根现算）。
假设：DB 负年（2015/2018/2023/2024，尤其 2024 全品种负）的信号集中在
低 breadth 环境；breadth 闸门（如 >=1/3）可拦截系统性负年而不伤正年。
输出：分桶收益、负年/正年在各桶的分布、建议阈值。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"

SYMBOLS = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
           "CU": DATA / "SHFE" / "CU" / "CU.csv",
           "AG": DATA / "SHFE" / "AG" / "AG.csv",
           "M": DATA / "DCE" / "M" / "M.csv",
           "MA": DATA / "CZCE" / "MA" / "MA.csv",
           "TA": DATA / "CZCE" / "TA" / "TA.csv"}
NEG_YEARS = {2015, 2018, 2023, 2024}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ret20 = {}
    for sym, p in SYMBOLS.items():
        dts, closes = [], []
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(r["datetime"])
                closes.append(float(r["close"]))
        m = {}
        for i in range(20, len(closes)):
            m[dts[i]] = closes[i] / closes[i - 20] - 1
        ret20[sym] = m

    def breadth(dtstr):
        vals = [m[dtstr] for m in ret20.values() if dtstr in m]
        if len(vals) < 3:
            return None
        return sum(1 for x in vals if x > 0) / len(vals)

    cell = defaultdict(lambda: defaultdict(list))   # (year) -> bucket -> [net]
    bcount = defaultdict(lambda: defaultdict(int))  # year -> bucket -> n
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["signal_id"] != "DOUBLE_BOTTOM":
                continue
            net = r.get("p1_net_r")
            if net in ("", None):
                continue
            b = breadth(r["bar_time"])
            if b is None:
                continue
            bucket = "<1/3" if b < 0.34 else ("1/3~2/3" if b < 0.67 else ">=2/3")
            try:
                y = datetime.strptime(r["bar_time"],
                                      "%Y-%m-%d %H:%M:%S").year
            except ValueError:
                continue
            cell[y][bucket].append(float(net))
            bcount[y][bucket] += 1
    buckets = ("<1/3", "1/3~2/3", ">=2/3")
    lines = ["# 市场 breadth 过滤原型 × DOUBLE_BOTTOM（breadth=池内 prior_ret20>0 占比）", ""]
    lines.append("## 分桶总览（触发样本 avg p1_net_r，R）")
    lines.append("| 桶 | n | 胜率 | 平均净R |")
    lines.append("|---|---|---|---|")
    for bk in buckets:
        xs = [x for y in cell for x in cell[y][bk]]
        if not xs:
            continue
        win = sum(1 for x in xs if x > 0) / len(xs) * 100
        lines.append(f"| {bk} | {len(xs)} | {win:.1f}% | {sum(xs) / len(xs):+.3f} |")
    lines += ["", "## 负年 vs 正年在各桶的笔数分布", "",
              "| 年组 | " + " | ".join(buckets) + " |", "|---|" + "---|" * 3]
    for name, ys in (("负年", NEG_YEARS), ("正年", set(cell) - NEG_YEARS)):
        row = []
        for bk in buckets:
            n = sum(bcount[y][bk] for y in ys)
            tot = sum(sum(bcount[y].values()) for y in ys) or 1
            row.append(f"{n} ({n / tot * 100:.0f}%)")
        lines.append(f"| {name} | " + " | ".join(row) + " |")
    lines += ["", "## 分年×桶平均净R（R）"]
    lines.append("| 年 | " + " | ".join(buckets) + " |")
    lines.append("|---|" + "---|" * 3)
    for y in sorted(cell):
        flag = " ❌" if y in NEG_YEARS else ""
        row = [f"{y}{flag}"]
        for bk in buckets:
            xs = cell[y][bk]
            row.append(f"{sum(xs) / len(xs):+.3f}({len(xs)})" if xs else "-")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "判读：若负年集中于 <1/3 桶且该桶均值为深负、正年在 >=1/3 桶"
              "不受损，则 breadth 闸门（>=1/3）作为市场级过滤器成立。"]
    (OUT / "db_breadth_filter.md").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")
    print("->", OUT / "db_breadth_filter.md")


if __name__ == "__main__":
    main()
