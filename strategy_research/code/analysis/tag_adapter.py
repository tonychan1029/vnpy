# RESEARCH ONLY - 未获用户批准不得正式运行
"""context_tag v0 → RS012 预测契约适配器。

工程侧 v0 词表（baseline_report.md「判定侧 context v0 规则」）映射：
  breakout → BREAKOUT
  range → RANGE
  reversal → REVERSAL
  trend_strong / trend_channel → TREND_UP 若 close>EMA20 否则 TREND_DN
    （v0 规则本身要求斜率与 (close-EMA20) 同向，方向由 close-EMA20 符号恢复；
     EMA20 以 60m 收盘价按同一周期现算，与生产口径一致）
  空 tag → 跳过
输出 assets/RS012/incoming/predictions.csv（datetime,symbol,pred_label）。
"""

from __future__ import annotations

import csv
from pathlib import Path

BASE = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "RS012" / "incoming" / "predictions.csv"

SYMBOLS = ("RB", "CU", "AG", "M", "MA", "TA")
SRC = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
       "CU": DATA / "SHFE" / "CU" / "CU.csv",
       "AG": DATA / "SHFE" / "AG" / "AG.csv",
       "M": DATA / "DCE" / "M" / "M.csv",
       "MA": DATA / "CZCE" / "MA" / "MA.csv",
       "TA": DATA / "CZCE" / "TA" / "TA.csv"}


def ema20_map(path):
    with path.open(newline="", encoding="utf-8") as f:
        rows = [(r["datetime"], float(r["close"])) for r in csv.DictReader(f)]
    k = 2 / 21
    e = None
    out = {}
    for dt, c in rows:
        e = c if e is None else c * k + e * (1 - k)
        out[dt] = (c, e)
    return out


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    stats = defaultdict(int)
    out_rows = ["datetime,symbol,pred_label"]
    for sym in SYMBOLS:
        emap = ema20_map(SRC[sym])
        src = BASE / f"{sym}_context_tags.csv"
        with src.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                tag = (r.get("context_tag") or "").strip().lower()
                if not tag:
                    stats["skip_empty"] += 1
                    continue
                if tag in ("breakout", "range", "reversal"):
                    lab = tag.upper()
                elif tag in ("trend_strong", "trend_channel"):
                    ce = emap.get(r["datetime"])
                    if ce is None:
                        lab = "UNDEFINED"
                    else:
                        lab = "TREND_UP" if ce[0] > ce[1] else "TREND_DN"
                else:
                    stats[f"unknown_{tag}"] += 1
                    continue
                stats[lab] += 1
                out_rows.append(f"{r['datetime']},{sym},{lab}")
    OUT.write_text("\n".join(out_rows) + "\n", encoding="utf-8")
    print(f"-> {OUT}")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    from collections import defaultdict
    main()
