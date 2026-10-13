# RESEARCH ONLY - 未获用户批准不得正式运行
"""突破族 regime 重测（MTG004 决议 2 的修订臂验证）。

臂 A（穿越时刻）：首次进入 breakout 标签当根收盘入场（=现网口径）。
臂 B（regime 确认）：同事件后第 5 根仍为 breakout 标签才入场（该根收盘）。
前瞻 10/20 根，事件级（非采样步长），6 品种合并。
假设：regime 溢价在确认后仍可捕获（RS013 GT 版），穿越时刻已被消耗（基线 ≈0）。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

TAGS = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"

SYMBOLS = {"RB": (DATA / "SHFE" / "RB" / "RB.csv", TAGS / "RB_context_tags.csv"),
           "CU": (DATA / "SHFE" / "CU" / "CU.csv", TAGS / "CU_context_tags.csv"),
           "AG": (DATA / "SHFE" / "AG" / "AG.csv", TAGS / "AG_context_tags.csv"),
           "M": (DATA / "DCE" / "M" / "M.csv", TAGS / "M_context_tags.csv"),
           "MA": (DATA / "CZCE" / "MA" / "MA.csv", TAGS / "MA_context_tags.csv"),
           "TA": (DATA / "CZCE" / "TA" / "TA.csv", TAGS / "TA_context_tags.csv")}
HORIZONS = (10, 20)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = defaultdict(lambda: defaultdict(list))
    for sym, (dpath, tpath) in SYMBOLS.items():
        dts, closes = [], []
        with dpath.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(r["datetime"])
                closes.append(float(r["close"]))
        n = len(closes)
        tags = [None] * n
        idx = {d: i for i, d in enumerate(dts)}
        with tpath.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                i = idx.get(r["datetime"])
                if i is not None:
                    tags[i] = (r.get("context_tag") or "").strip().lower()
        in_event = False
        for i in range(1, n):
            t = tags[i] == "breakout"
            if t and not in_event:
                in_event = True
                # 臂 A：当根入场
                for hz in HORIZONS:
                    if i + hz < n:
                        res["A_event"][hz].append(
                            (sym, closes[i + hz] / closes[i] - 1))
                # 臂 B：+5 根仍 breakout 才入场
                j = i + 5
                if j + max(HORIZONS) < n and tags[j] == "breakout":
                    for hz in HORIZONS:
                        res["B_regime"][hz].append(
                            (sym, closes[j + hz] / closes[j] - 1))
            elif not t:
                in_event = False
    lines = ["# 突破族 regime 重测（引擎 breakout 标签，事件级）", "",
             "| 臂 | 前瞻 | n | 胜率 | 平均收益 |", "|---|---|---|---|---|"]
    for arm, desc in (("A_event", "A 穿越时刻入场"), ("B_regime", "B regime 确认后入场")):
        for hz in HORIZONS:
            xs = res[arm][hz]
            rets = [r for _, r in xs]
            if not rets:
                continue
            win = sum(1 for r in rets if r > 0) / len(rets)
            lines.append(f"| {arm} | {hz}根 | {len(rets)} | {win * 100:.1f}% | "
                         f"{sum(rets) / len(rets) * 100:.3f}% |")
    lines.append("")
    lines.append("## 分品种 20 根")
    lines.append("| 品种 | A n/均值 | B n/均值 |")
    lines.append("|---|---|---|")
    for sym in SYMBOLS:
        row = [sym]
        for arm in ("A_event", "B_regime"):
            xs = [r for s, r in res[arm][20] if s == sym]
            row.append(f"{len(xs)}/{sum(xs) / len(xs) * 100:.3f}%" if xs else "-")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "判读：B>A 显著则 regime 确认后入场成立（突破族修订方向获得数据支撑）；"
              "B≤A 则 regime 溢价已被确认等待期消耗，修订方向需再议。"]
    (OUT / "regime_retest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", OUT / "regime_retest.md")


if __name__ == "__main__":
    main()
