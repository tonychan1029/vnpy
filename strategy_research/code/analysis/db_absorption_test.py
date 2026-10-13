# RESEARCH ONLY - 未获用户批准不得正式运行
"""W 底 × absorption 配对检验（M-EX-003 优化首实验）。

DB 信号 bar 的量能状态（rvol = 当根量/20 根均量）分桶：
  absorption ≤0.8（缩量筑底）/ normal 0.8-1.5 / climax >1.5（放量）
假设（来自 RS014 h2h 与 M-EX-003）：缩量筑底的 W 底质量更高。
对照 p1_net_r；分年抽查负年（2015/18/23/24）是否被量能分桶区分。
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
    rvol_map = {}
    for sym, p in SYMBOLS.items():
        dts, closes, vols = [], [], []
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(r["datetime"])
                closes.append(float(r["close"]))
                vols.append(float(r["volume"]))
        m = {}
        for i in range(19, len(closes)):
            m[dts[i]] = vols[i] / (sum(vols[i - 19:i + 1]) / 20)
        rvol_map[sym] = m

    cell = defaultdict(list)                # bucket -> [net]
    cell_year = defaultdict(lambda: defaultdict(list))
    n_missing = 0
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["signal_id"] != "DOUBLE_BOTTOM":
                continue
            net = r.get("p1_net_r")
            if net in ("", None):
                continue
            rv = rvol_map.get(r["symbol"], {}).get(r["bar_time"])
            if rv is None:
                n_missing += 1
                continue
            bk = "absorption(<=0.8)" if rv <= 0.8 else \
                ("normal(0.8-1.5)" if rv <= 1.5 else "climax(>1.5)")
            cell[bk].append(float(net))
            try:
                y = datetime.strptime(r["bar_time"],
                                      "%Y-%m-%d %H:%M:%S").year
                cell_year[bk][y].append(float(net))
            except ValueError:
                pass
    lines = ["# W 底 × absorption 配对检验（DB 信号 bar 量能状态 → p1_net_r）", "",
             "| 量能桶 | n | 胜率 | 平均净R |", "|---|---|---|---|"]
    for bk in ("absorption(<=0.8)", "normal(0.8-1.5)", "climax(>1.5)"):
        xs = cell[bk]
        if not xs:
            continue
        win = sum(1 for x in xs if x > 0) / len(xs) * 100
        lines.append(f"| {bk} | {len(xs)} | {win:.1f}% | "
                     f"{sum(xs) / len(xs):+.3f} |")
    lines += ["", "## 负年 × 量能桶（平均净R）", "",
              "| 年 | absorption | normal | climax |", "|---|---|---|---|"]
    for y in sorted(NEG_YEARS):
        row = [f"{y} ❌"]
        for bk in ("absorption(<=0.8)", "normal(0.8-1.5)", "climax(>1.5)"):
            xs = cell_year[bk].get(y, [])
            row.append(f"{sum(xs) / len(xs):+.3f}({len(xs)})" if xs else "-")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", f"无量能上下文样本：{n_missing}",
              "", "判读：absorption 桶优于 climax 桶且负年改善则配对成立；"
              "否则 M-EX-003 与 W 底编排无叠加价值（各用各的）。"]
    (OUT / "db_absorption_test.md").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8")
    print("->", OUT / "db_absorption_test.md")


if __name__ == "__main__":
    main()
