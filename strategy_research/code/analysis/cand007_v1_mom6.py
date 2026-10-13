# RESEARCH ONLY - 未获用户批准不得正式运行
"""CAND-007 v1 复测收尾：v1 regime 确认入场（B 臂）× mom6 分位分割。

重验证登记册：v1 迟滞交付后，检验 mom6 分位闸门在 v1 regime 事件上
是否恢复区分力（v0 时 B 臂 n 不足/闪烁）。B 臂=事件后第 5 根仍 breakout。
mom6 品种内百分位（B 臂事件池内），分 ≥60% / <60% 两档对照。
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
HZ = 20


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
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
                j = i + 5
                if j + HZ < n and tags[j] == "breakout" \
                        and j >= 6 and closes[j - 6] > 0:
                    entries.append((sym, j, closes[j] / closes[j - 6] - 1))
            elif not t:
                in_event = False

    by_sym = defaultdict(list)
    for sym, j, m6 in entries:
        by_sym[sym].append((j, m6))
    ranked = []
    for sym, lst in by_sym.items():
        closes = None
        vals = sorted(m for _, m in lst)
        ranks = {}
        for k, (_, m) in enumerate(lst):
            ranks[k] = sum(1 for v in vals if v < m) / max(len(vals) - 1, 1)
        closes = SYMBOLS[sym][0]
        dts, o, h, l, c, v = [], [], [], [], [], []
        with closes.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(r["datetime"])
                c.append(float(r["close"]))
        for k, (j, m) in enumerate(lst):
            if j + HZ < len(c):
                ranked.append((sym, ranks[k], c[j + HZ] / c[j] - 1))
    lines = ["# CAND-007 v1 复测收尾：B 臂（regime 确认入场）× mom6 分位", "",
             "| mom6 分位 | n | 胜率 | 平均收益 |", "|---|---|---|---|"]
    buckets = {">=60%": lambda r: r >= 0.6, "<60%": lambda r: r < 0.6}
    for name, fn in buckets.items():
        xs = [fw for _, rk, fw in ranked if fn(rk)]
        if not xs:
            continue
        win = sum(1 for x in xs if x > 0) / len(xs) * 100
        lines.append(f"| {name} | {len(xs)} | {win:.1f}% | "
                     f"{sum(xs) / len(xs) * 100:.3f}% |")
    lines += ["", "判读：高分位档 > 低分位档 → mom6 闸门在 v1 regime 下恢复区分力"
              "（CAND-007 可转受限启用）；两档接近 → 维持 gated。"]
    (OUT / "cand007_v1_mom6.md").write_text("\n".join(lines) + "\n",
                                            encoding="utf-8")
    print("->", OUT / "cand007_v1_mom6.md")


if __name__ == "__main__":
    main()
