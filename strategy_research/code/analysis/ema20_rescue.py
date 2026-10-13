# RESEARCH ONLY - 未获用户批准不得正式运行
"""EMA20_PULLBACK 否决复核（重验证登记册）：M-EX-003 式深跌闸门救援检验。

该信号基线 −0.202R（12/12 年负），失败形态=深跌接刀。
检验：信号 bar 的 prior_ret20 > −5%（浅调才放行）能否改善净R。
若放行组仍显著为负 → 否决维持且终局（连救援口径都失败）。
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
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["signal_id"] != "EMA20_PULLBACK":
                continue
            net = r.get("p1_net_r")
            if net in ("", None):
                continue
            pr = prior20(r["symbol"], r["bar_time"])
            if pr is None:
                continue
            y = datetime.strptime(r["bar_time"],
                                  "%Y-%m-%d %H:%M:%S").year
            g = "pass" if pr > -0.05 else "fail"
            groups[g][y].append(float(net))
    lines = ["# EMA20_PULLBACK 否决复核：深跌闸门（prior_ret20>−5%）救援检验", "",
             "| 组 | n | 胜率 | 平均净R |", "|---|---|---|---|"]
    tot = {}
    for g, name in (("pass", "放行（浅调/上行）"), ("fail", "拦截（深跌）")):
        allnets = [x for y in groups[g] for x in groups[g][y]]
        win = sum(1 for x in allnets if x > 0) / len(allnets) * 100 if allnets else 0
        avg = sum(allnets) / len(allnets) if allnets else 0
        tot[g] = avg
        lines.append(f"| {name} | {len(allnets)} | {win:.1f}% | {avg:+.4f} |")
    lines += ["", "## 分年（平均净R）", "",
              "| 年 | 放行 | 拦截 |", "|---|---|---|"]
    for y in sorted(set(groups["pass"]) | set(groups["fail"])):
        p = groups["pass"].get(y, [])
        f_ = groups["fail"].get(y, [])
        ps = f"{sum(p) / len(p):+.4f}({len(p)})" if p else "-"
        fs = f"{sum(f_) / len(f_):+.4f}({len(f_)})" if f_ else "-"
        lines.append(f"| {y} | {ps} | {fs} |")
    lines += ["", "判读：放行组仍为负 → 否决终局（救援失败，深跌不是唯一死因）；"
              "放行组转正 → 否决改判为'需闸门的受限启用'。"]
    (OUT / "ema20_rescue.md").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8")
    print("->", OUT / "ema20_rescue.md")


if __name__ == "__main__":
    main()
