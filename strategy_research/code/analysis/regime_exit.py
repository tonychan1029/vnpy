# RESEARCH ONLY - 未获用户批准不得正式运行
"""持仓管理规则研究（RS013 溢价"守"假说的可测形式）。

入场：突破事件首根（引擎 breakout 标签，同 regime_retest 臂 A）。
离场对比：
  F 固定持有：第 20 根离场（现网 horizon 口径）
  R regime 离场：min(第20根, 首个标签离开 breakout 的根) 离场
若 R 优于 F（均收益/回避负尾），则"regime 存续期间不提前离场"的反面——
"regime 结束即离场"有增量；若 R 差于 F，则 regime 内也应持有满期。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

TAGS = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "RS013"

SYMBOLS = {"RB": (DATA / "SHFE" / "RB" / "RB.csv", TAGS / "RB_context_tags.csv"),
           "CU": (DATA / "SHFE" / "CU" / "CU.csv", TAGS / "CU_context_tags.csv"),
           "AG": (DATA / "SHFE" / "AG" / "AG.csv", TAGS / "AG_context_tags.csv"),
           "M": (DATA / "DCE" / "M" / "M.csv", TAGS / "M_context_tags.csv"),
           "MA": (DATA / "CZCE" / "MA" / "MA.csv", TAGS / "MA_context_tags.csv"),
           "TA": (DATA / "CZCE" / "TA" / "TA.csv", TAGS / "TA_context_tags.csv")}
HMAX = 20


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = defaultdict(list)
    holds = defaultdict(int)
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
                j_end = min(i + HMAX, n - 1)
                j_regime = j_end
                for j in range(i + 1, j_end + 1):
                    if tags[j] not in (None, "breakout"):
                        j_regime = j
                        break
                res["F_fixed"].append(closes[j_end] / closes[i] - 1)
                res["R_regime"].append(closes[j_regime] / closes[i] - 1)
                holds[j_regime - i] += 1
            elif not t:
                in_event = False

    def st(key):
        xs = res[key]
        win = sum(1 for r in xs if r > 0) / len(xs) if xs else 0
        return len(xs), win, sum(xs) / len(xs) if xs else 0

    lines = ["# 持仓管理规则研究：regime 离场 vs 固定持有（突破事件多头）", "",
             "| 规则 | n | 胜率 | 平均收益 |", "|---|---|---|---|"]
    for key, desc in (("F_fixed", "F 固定持有 20 根"),
                      ("R_regime", "R 标签离开 breakout 即离场（上限20根）")):
        n, w, a = st(key)
        lines.append(f"| {desc} | {n} | {w * 100:.1f}% | {a * 100:.3f}% |")
    lines.append("")
    lines.append("## R 规则持有期分布（根：笔数）")
    lines.append(" ".join(f"{k}:{v}" for k, v in sorted(holds.items())))
    lines += ["", "判读：R>F →『regime 结束即离场』有增量（溢价在 regime 内、离场应及时）；"
              "R<F → regime 内也应持有满期（提前离场截断利润）。"]
    (OUT / "regime_exit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", OUT / "regime_exit.md")


if __name__ == "__main__":
    main()
