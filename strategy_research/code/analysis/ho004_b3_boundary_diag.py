# RESEARCH ONLY - 未获用户批准不得正式运行
"""HO004-B3 边界诊断（验收 FAIL 形迹核查，非判读变更）。

形迹：B3 报告中 v2 tags 与 v1 锚逐列显示值完全一致（RANGE 19.0%/17.0%、
BREAKOUT 31.8%/31.8%）——与预注册"tag 集合结构性应逐点一致"相符；
机械 FAIL 疑因阈值 ≥31.8% 取自四舍五入显示值（精确值或为 31.79x%）。
本诊断输出：①B3 各列精确精确率（6 位小数）②v1 锚同阈值自检
③v1→v2 标签逐点差分（确认差异仅发生在 reversal/trend 占位）。
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.context_v2_diagnostic import (   # noqa: E402
    SYMBOLS, atr_series, ema_series, evaluate, load_bars)
from analysis.ho004_acceptance import GT_V1, TAGS_V1, TAGS_V2, map_tag  # noqa: E402

OUT = ROOT.parent / "assets" / "RS015"


def main():
    rows_b3, rows_ref = [], []
    tag_diff = Counter()
    n_cmp = 0
    for sym, exch in SYMBOLS.items():
        from analysis.context_v2_diagnostic import DATA
        dts, highs, lows, closes = load_bars(DATA / exch / sym / f"{sym}.csv")
        emas = ema_series(closes)
        dt2i = {d: k for k, d in enumerate(dts)}
        v2tags, v1tags = {}, {}
        with (TAGS_V2 / f"{sym}_context_tags.csv").open(
                newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                v2tags[r["datetime"]] = (r.get("context_tag") or "").strip().lower()
        with (TAGS_V1 / f"{sym}_context_tags.csv").open(
                newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                v1tags[r["datetime"]] = (r.get("context_tag") or "").strip().lower()
        with (GT_V1 / f"{sym}_gt_labels.csv").open(
                newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                d = r["datetime"]
                i = dt2i.get(d)
                if i is None or emas[i] is None:
                    continue
                diff = closes[i] - emas[i]
                t1, t2 = v1tags.get(d, ""), v2tags.get(d, "")
                if t1 or t2:
                    n_cmp += 1
                    if t1 != t2:
                        tag_diff[(t1 or "<empty>", t2 or "<empty>")] += 1
                p2 = map_tag(t2, diff)
                if p2:
                    rows_b3.append((sym, d, r["gt_label"], p2))
                if t1 in ("breakout", "range", "reversal") or \
                        t1 in ("trend_strong", "trend_channel"):
                    p1 = map_tag(t1, diff)
                    if p1:
                        rows_ref.append((sym, d, r["gt_label"], p1))

    L = ["# HO004-B3 边界诊断（v2 vs v1 锚精确值 + 逐点差分）", ""]
    for name, rows in (("v2 tags", rows_b3), ("v1 tags 锚", rows_ref)):
        rr = evaluate(rows, "RANGE")
        bb = evaluate(rows, "BREAKOUT")
        L.append(f"## {name}")
        L.append(f"- RANGE 精确率 {rr['prec']:.6f}（触发 {rr['share']:.6f}）")
        L.append(f"- BREAKOUT 精确率 {bb['prec']:.6f}（触发 {bb['share']:.6f}）")
        L.append("")
    L.append("## v1→v2 标签差分（同 datetime 逐点）")
    L.append(f"- 可比对点数 {n_cmp}，差异点数 {sum(tag_diff.values())}")
    L.append("")
    L.append("| v1 → v2 | 点数 |")
    L.append("|---|---|")
    for (a, b), k in sorted(tag_diff.items(), key=lambda x: -x[1]):
        L.append(f"| {a} → {b} | {k} |")
    out = OUT / "ho004_b3_boundary_diag.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    rr2 = evaluate(rows_b3, "BREAKOUT")
    rr1 = evaluate(rows_ref, "BREAKOUT")
    print(f"BREAKOUT exact: v2={rr2['prec']:.6f} v1anchor={rr1['prec']:.6f} "
          f"threshold=0.318000 v1_anchor_pass={rr1['prec'] >= 0.318}")


if __name__ == "__main__":
    main()
