# RESEARCH ONLY - 未获用户批准不得正式运行
"""HO004 交付评估附册：量化 DOUBLE_TOP/BOTTOM 对 reversal 标签的真实暴露。
基线 signals_detail（v0 标签时代）逐笔按 v1 context_tags 归位背景，
回答：B4 把 DT/DB 背景 {range,reversal}→{range} 会改动多少信号总体。
输出：控制台 + assets/RS015/ho004_dt_db_exposure.md
"""
import csv
from collections import Counter
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
TAGS = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
OUT = Path(__file__).resolve().parents[2] / "assets" / "RS015"
SYMS = {"RB": "SHFE", "CU": "SHFE", "AG": "SHFE",
        "M": "DCE", "MA": "CZCE", "TA": "CZCE"}

c = Counter()
tot = Counter()
for s in SYMS:
    tags = {}
    with (TAGS / f"{s}_context_tags.csv").open(newline="",
                                               encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tags[r["datetime"]] = (r.get("context_tag") or "").strip().lower()
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sid = r["signal_id"]
            if sid not in ("DOUBLE_BOTTOM", "DOUBLE_TOP"):
                continue
            t = tags.get(r["bar_time"], "") or "(空)"
            c[(sid, t)] += 1
            tot[sid] += 1

L = ["# HO004-B4 影响量化：DT/DB 背景对 reversal 标签的暴露", "",
     "- 基线 signals_detail（v0 时代）逐笔按 v1 context_tags 归位；", ""]
for sid in ("DOUBLE_BOTTOM", "DOUBLE_TOP"):
    L.append(f"## {sid}（基线总量 {tot[sid]}）")
    L.append("")
    L.append("| 窗口起点背景 | 笔数 | 占比 |")
    L.append("|---|---|---|")
    for k in ("range", "reversal", "breakout", "trend_strong",
              "trend_channel", "(空)"):
        n = c.get((sid, k), 0)
        if n:
            L.append(f"| {k} | {n} | {n / tot[sid]:.1%} |")
    L.append("")
rev_db = c.get(("DOUBLE_BOTTOM", "reversal"), 0)
rev_dt = c.get(("DOUBLE_TOP", "reversal"), 0)
L += ["## 判读", "",
      f"- B4（背景 {{range,reversal}}→{{range}}）改动量：DB {rev_db}/{tot['DOUBLE_BOTTOM']}"
      f"（{rev_db / tot['DOUBLE_BOTTOM']:.1%}）、DT {rev_dt}/{tot['DOUBLE_TOP']}"
      f"（{rev_dt / tot['DOUBLE_TOP']:.1%}）——来自 reversal 标签窗的信号将不再触发；",
      "- 若不改 B4（保留 {range, reversal_v2}），v2 reversal 触发 36.2% 将使 DT/DB"
      " 背景大幅扩面，信号总体显著膨胀——故 B4→{range} 是收缩性选择；",
      "- 对 DB（optimizing 中）影响：基线 +0.086 的可比性被打破一部分，",
      "  v2 标签基线重跑时 DB 分层报告须同时给新旧背景两组。"]
out = OUT / "ho004_dt_db_exposure.md"
out.write_text("\n".join(L) + "\n", encoding="utf-8")
print("->", out)
print("DB rev:", rev_db, "/", tot["DOUBLE_BOTTOM"],
      " DT rev:", rev_dt, "/", tot["DOUBLE_TOP"])
