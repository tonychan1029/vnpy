# RESEARCH ONLY - 未获用户批准不得正式运行
"""M-EX-003 闸门在 DOUBLE_BOTTOM 上的编排口径验证。

闸门：信号 bar 的 prior_ret20 = close[t]/close[t-20]−1 > −5%（浅调/非深跌才放行）。
对照：DB 全部已触发逐笔（p1_outcome 非空），闸门通过组 vs 拦截组的
净收益/胜率/年度分布。假设：拦截组集中于负年与负收益尾部。
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
    closes_map = {}
    for sym, p in SYMBOLS.items():
        dts, closes = [], []
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(r["datetime"])
                closes.append(float(r["close"]))
        closes_map[sym] = (dts, closes)

    def prior20(sym, dtstr):
        dts, closes = closes_map[sym]
        i = dts.index(dtstr) if dtstr in dts else -1
        if i < 20:
            return None
        return closes[i] / closes[i - 20] - 1

    groups = {"pass": defaultdict(list), "fail": defaultdict(list)}
    trig = {"pass": [0, 0], "fail": [0, 0]}       # [triggered, total]
    n_noctx = 0
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["signal_id"] != "DOUBLE_BOTTOM":
                continue
            sym = r["symbol"]
            try:
                dt = datetime.strptime(r["bar_time"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            pr = prior20(sym, r["bar_time"])
            if pr is None:
                n_noctx += 1
                continue
            g = "pass" if pr > -0.05 else "fail"
            is_trig = bool(r.get("p1_outcome"))
            trig[g][1] += 1
            if is_trig:
                trig[g][0] += 1
                net = r.get("p1_net_r")
                if net not in ("", None):
                    groups[g][dt.year].append(float(net))
    lines = ["# M-EX-003 闸门 × DOUBLE_BOTTOM 编排口径验证（闸门 prior_ret20>−5%）", ""]
    for g, name in (("pass", "通过闸门"), ("fail", "被拦截")):
        allnets = [x for y in groups[g] for x in groups[g][y]]
        win = sum(1 for x in allnets if x > 0) / len(allnets) * 100 if allnets else 0
        avg = sum(allnets) / len(allnets) if allnets else 0
        lines.append(f"- **{name}**：触发 {trig[g][0]}/{trig[g][1]}"
                     f"（触发率 {trig[g][0] / max(trig[g][1], 1) * 100:.1f}%），"
                     f"n={len(allnets)}，胜率 {win:.1f}%，平均净R {avg:+.3f}R")
    lines += ["", "## 分年（触发样本平均净R，括号=n）", "",
              "| 年 | 通过闸门 | 被拦截 |", "|---|---|---|"]
    all_years = sorted(set(groups["pass"]) | set(groups["fail"]))
    for y in all_years:
        p = groups["pass"].get(y, [])
        f_ = groups["fail"].get(y, [])
        ps = f"{sum(p) / len(p):+.3f}R({len(p)})" if p else "-"
        fs = f"{sum(f_) / len(f_):+.3f}R({len(f_)})" if f_ else "-"
        mark = " ❌" if y in NEG_YEARS else ""
        lines.append(f"| {y}{mark} | {ps} | {fs} |")
    lines += ["", f"无上下文样本（60m 序列前 20 根内）：{n_noctx}",
              "", "判读：若拦截组均收益显著为负且集中在负年，则闸门在编排口径下成立，"
              "M-EX-003 v1.1 推广到信号编排获基线数据支持。"]
    (OUT / "db_gate_test.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", OUT / "db_gate_test.md")


if __name__ == "__main__":
    main()
