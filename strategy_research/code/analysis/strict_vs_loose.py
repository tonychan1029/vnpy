# RESEARCH ONLY - 未获用户批准不得正式运行
"""突破确认严格度对照（CAND-009 核心规则的预评）。

日级水平位 = 前一日高点（60m 聚合，与基准同源）。
- 宽松臂 A：任一 60m 根收盘 > 前日高 → 当根收盘入场
- 严格臂 B（CAND-009 双重确认）：先记录首次触碰（high>=前日高），
  等待收盘 > max(前日高, 触碰极值) → 当根收盘入场；当日未触发则放弃
两臂均日末平仓、双边万3、前瞻 10/20 根（持仓内）与隔日（日末平仓收益）。
问题：更严的确认是否以足够少的样本损失换来更高的单笔质量。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "CAND-009"
COST = 0.0006

SYMBOLS = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
           "CU": DATA / "SHFE" / "CU" / "CU.csv",
           "AG": DATA / "SHFE" / "AG" / "AG.csv",
           "M": DATA / "DCE" / "M" / "M.csv",
           "MA": DATA / "CZCE" / "MA" / "MA.csv",
           "TA": DATA / "CZCE" / "TA" / "TA.csv"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = defaultdict(lambda: defaultdict(list))   # arm -> hz -> [ret]
    dayclose_ret = defaultdict(list)               # arm -> [ret]（日末平仓）
    for sym, path in SYMBOLS.items():
        days = defaultdict(list)
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                days[r["datetime"][:10]].append(
                    (float(r["open"]), float(r["high"]),
                     float(r["low"]), float(r["close"])))
        dates = sorted(days)
        for t in range(1, len(dates)):
            bars = days[dates[t]]
            if len(bars) < 3:
                continue
            level = max(b[1] for b in days[dates[t - 1]])
            day_close = bars[-1][3]
            ent_a = None
            ent_b = None
            first_touch_ext = None
            for o_, h_, l_, c_ in bars:
                # 宽松：首次收盘越位
                if ent_a is None and c_ > level:
                    ent_a = c_
                # 严格（CAND-009 语义）：首次触碰极值只记第一次，
                # 等待其后某根收盘 > max(level, 首触极值)
                if first_touch_ext is None and h_ >= level:
                    first_touch_ext = h_
                elif first_touch_ext is not None and ent_b is None:
                    if c_ > max(level, first_touch_ext):
                        ent_b = c_
            if ent_a is not None:
                dayclose_ret["A_loose"].append(
                    day_close / ent_a - 1 - COST)
            if ent_b is not None:
                dayclose_ret["B_strict"].append(
                    day_close / ent_b - 1 - COST)
    lines = ["# 突破确认严格度对照（前日高位，60m 代理，双边万3，日末平仓）", "",
             "| 臂 | 口径 | n | 胜率 | 平均净收益 |", "|---|---|---|---|---|"]
    for arm, desc in (("A_loose", "宽松：首根收盘越位"),
                      ("B_strict", "严格：首触后收盘越首触极值")):
        dr = dayclose_ret[arm]
        n_d = len(dr)
        avg_d = sum(dr) / n_d * 100 if n_d else 0
        win_d = sum(1 for r in dr if r > 0) / n_d * 100 if n_d else 0
        lines.append(f"| {arm} | {desc} | {n_d} | {win_d:.1f}% | {avg_d:.3f}% |")
    (OUT / "strict_vs_loose.md").write_text("\n".join(lines) + "\n",
                                            encoding="utf-8")
    print("->", OUT / "strict_vs_loose.md")


if __name__ == "__main__":
    main()
