# RESEARCH ONLY - 未获用户批准不得正式运行
"""HO004 验收 runner（B1/B2/B3，预注册于 HO004 §B；工程交付后即插即跑）。

输入契约：vnpy_patiming/output/baseline/context_tags_v2/{SYM}_context_tags.csv
（列不变：datetime,symbol,context_tag,strict_range；v1 目录保留作对照）。

  B1 主验收：v2 tags × GT v2（assets/RS015/{sym}_gt_rev2_labels.csv）
     → reversal 列精确率 ≥30% 且 LR ≥1.0
  B2 敏感性：GT v2 变体（leg 回看窗 40↔20 × 阈值 1.5↔2.0，共 4 组）
     → reversal 列精确率均 ≥25%（防定义亲和伪影；失败→回滚 A2 保留 A1）
  B3 非退化：v2 tags × GT v1.1 → RANGE 列精确率 ≥19.0% 且触发 ≥8%；
     BREAKOUT 列精确率 ≥31.8%（v1 修正实测值；tag 集合结构性应逐点一致）

输出：assets/RS015/ho004_acceptance.md
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # strategy_research/code
sys.path.insert(0, str(ROOT))

from analysis.context_v2_diagnostic import (   # noqa: E402
    DATA, SYMBOLS, atr_series, ema_series, evaluate, load_bars)

GT_V1 = ROOT.parent / "assets" / "RS012"
GT_V2 = ROOT.parent / "assets" / "RS015"
OUT = ROOT.parent / "assets" / "RS015"
TAGS_V1 = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
TAGS_V2 = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags_v2")
HORIZON = 20
STEP = 4


def map_tag(tag: str, diff: float) -> str:
    tag = (tag or "").strip().lower()
    if tag in ("breakout", "range", "reversal"):
        return tag.upper()
    if tag in ("trend_strong", "trend_channel"):
        return "TREND_UP" if diff > 0 else "TREND_DN"
    return ""


def gt_label_v2_p(closes, atr, as_of, leg_win, leg_k,
                  horizon=HORIZON, consist=0.6):
    """GT v2 参数化变体（leg 回看窗 / 阈值可变；其余同 v1.1 优先级）。"""
    fwd = closes[as_of + 1: as_of + 1 + horizon]
    if len(fwd) < horizon or atr <= 0:
        return "UNDEFINED"
    base = closes[as_of]
    net = fwd[-1] - base
    ups = sum(1 for a, b in zip(fwd, fwd[1:]) if b > a)
    total = max(len(fwd) - 1, 1)
    pre = closes[max(0, as_of - 40): as_of + 1]
    hi40, lo40 = (max(pre), min(pre)) if pre else (base, base)

    if abs(net) >= 2 * atr:
        consistency = (ups / total) if net > 0 else (1 - ups / total)
        if consistency >= consist:
            return "TREND_UP" if net > 0 else "TREND_DN"
    if abs(net) < 1 * atr and max(fwd) <= hi40 and min(fwd) >= lo40:
        return "RANGE"

    back = closes[max(0, as_of - leg_win): as_of]
    hit = False
    if back:
        tH = max(range(len(back)), key=lambda j: back[j])
        H = back[tH]
        leg_up = H - min(back[:tH + 1])
        tL = min(range(len(back)), key=lambda j: back[j])
        Lw = back[tL]
        leg_dn = max(back[:tL + 1]) - Lw
        rev_up = leg_up >= leg_k * atr and min(fwd) <= H - 1.5 * atr \
            and abs(net) < 1.5 * atr
        rev_dn = leg_dn >= leg_k * atr and max(fwd) >= Lw + 1.5 * atr \
            and abs(net) < 1.5 * atr
        hit = rev_up or rev_dn
    if hit:
        return "REVERSAL"
    if max(fwd) > hi40 and max(fwd) - hi40 >= 2 * atr:
        return "BREAKOUT"
    if min(fwd) < lo40 and lo40 - min(fwd) >= 2 * atr:
        return "BREAKOUT"
    return "UNDEFINED"


def main():
    missing = [s for s in SYMBOLS
               if not (TAGS_V2 / f"{s}_context_tags.csv").exists()]
    if missing:
        print(f"[waiting] context_tags_v2 缺 {missing}——等待工程按 HO004-A3 交付。")
        return 1

    rows_b1 = []
    rows_b2 = {w: {k: [] for k in (1.5, 2.0)} for w in (40, 20)}
    rows_b3 = []
    rows_b3_ref = []      # v1 tags × GT v1.1（对照锚）
    for sym, exch in SYMBOLS.items():
        dts, highs, lows, closes = load_bars(DATA / exch / sym / f"{sym}.csv")
        atrs = atr_series(highs, lows, closes)
        emas = ema_series(closes)
        n = len(closes)
        dt2i = {d: k for k, d in enumerate(dts)}
        v2tags = {}
        with (TAGS_V2 / f"{sym}_context_tags.csv").open(
                newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                v2tags[r["datetime"]] = (r.get("context_tag") or "").strip().lower()
        v1tags = {}
        with (TAGS_V1 / f"{sym}_context_tags.csv").open(
                newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                v1tags[r["datetime"]] = (r.get("context_tag") or "").strip().lower()

        def pred_of(dt):
            i = dt2i.get(dt)
            if i is None or emas[i] is None:
                return None
            return map_tag(v2tags.get(dt, ""), closes[i] - emas[i])

        def pred_v1(dt, diff):
            t = v1tags.get(dt, "")
            if t in ("breakout", "range", "reversal"):
                return t.upper()
            if t in ("trend_strong", "trend_channel"):
                return "TREND_UP" if diff > 0 else "TREND_DN"
            return ""

        # B1：GT v2（已交付 CSV）
        with (GT_V2 / f"{sym}_gt_rev2_labels.csv").open(
                newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                p = pred_of(r["datetime"])
                if p:
                    rows_b1.append((sym, r["datetime"], r["gt_label"], p))

        # B2：GT v2 变体（现场重算）
        for w in (40, 20):
            for k in (1.5, 2.0):
                for as_of in range(40, n - HORIZON - 1, STEP):
                    a = atrs[as_of]
                    if a is None or a <= 0 or emas[as_of] is None or as_of < 45:
                        continue
                    g = gt_label_v2_p(closes, a, as_of, w, k)
                    if g == "UNDEFINED":
                        continue
                    d = dts[as_of]
                    p = pred_of(d)
                    if p:
                        rows_b2[w][k].append((sym, d, g, p))

        # B3：GT v1.1
        with (GT_V1 / f"{sym}_gt_labels.csv").open(
                newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                d = r["datetime"]
                i = dt2i.get(d)
                if i is None or emas[i] is None:
                    continue
                diff = closes[i] - emas[i]
                p2 = pred_of(d)
                if p2:
                    rows_b3.append((sym, d, r["gt_label"], p2))
                p1 = pred_v1(d, diff)
                if p1:
                    rows_b3_ref.append((sym, d, r["gt_label"], p1))

    L = ["# HO004 验收报告（B1/B2/B3 机械判读）", "",
         "- 输入：`vnpy_patiming/output/baseline/context_tags_v2/`；"
         "trend 拆向按 EMA20 现算 diff 符号（与诊断 harness 一致）。", ""]

    r1 = evaluate(rows_b1, "REVERSAL")
    b1 = r1["prec"] >= 0.30 and r1["lr"] >= 1.0
    L += ["## B1 主验收（GT v2）", "",
          f"- reversal 触发 {r1['fires']}（占比 {r1['share']:.1%}）、"
          f"列精确率 **{r1['prec']:.1%}**、LR {r1['lr']:.2f}",
          f"- 判定：{'✅ PASS（≥30% 且 LR≥1.0）' if b1 else '❌ FAIL'}", ""]

    L += ["## B2 敏感性（GT v2 变体 ×4，均 ≥25% 为 PASS）", "",
          "| leg 回看窗 | leg 阈值 | reversal 列精确率 | LR | 判定 |", "|---|---|---|---|---|"]
    b2 = True
    for w in (40, 20):
        for k in (1.5, 2.0):
            r = evaluate(rows_b2[w][k], "REVERSAL")
            ok = r["prec"] >= 0.25
            b2 = b2 and ok
            L.append(f"| {w} | {k} | {r['prec']:.1%} | {r['lr']:.2f} | "
                     f"{'✅' if ok else '❌'} |")
    L += ["", f"- 判定：{'✅ PASS' if b2 else '❌ FAIL（→ 回滚 A2，保留 A1 退役）'}", ""]

    r3r = evaluate(rows_b3, "RANGE")
    r3b = evaluate(rows_b3, "BREAKOUT")
    r3r_ref = evaluate(rows_b3_ref, "RANGE")
    r3b_ref = evaluate(rows_b3_ref, "BREAKOUT")
    b3 = r3r["prec"] >= 0.19 and r3r["share"] >= 0.08 and r3b["prec"] >= 0.318
    L += ["## B3 非退化（GT v1.1；对照=v1 tags 同网格）", "",
          "| 列 | v2 tags | v1 tags（锚） | 判定 |", "|---|---|---|---|",
          f"| RANGE 列精确率 | {r3r['prec']:.1%}（触发 {r3r['share']:.1%}） | "
          f"{r3r_ref['prec']:.1%}（触发 {r3r_ref['share']:.1%}） | "
          f"{'✅' if r3r['prec'] >= 0.19 and r3r['share'] >= 0.08 else '❌'} |",
          f"| BREAKOUT 列精确率 | {r3b['prec']:.1%} | {r3b_ref['prec']:.1%} | "
          f"{'✅' if r3b['prec'] >= 0.318 else '❌'} |", "",
          f"- 判定：{'✅ PASS' if b3 else '❌ FAIL'}", ""]

    overall = b1 and b2 and b3
    L += ["## 总判定（机械）", "",
          f"- B1 {'PASS' if b1 else 'FAIL'} / B2 {'PASS' if b2 else 'FAIL'} / "
          f"B3 {'PASS' if b3 else 'FAIL'} → **HO004 验收 "
          f"{'✅ 通过' if overall else '❌ 未通过'}**",
          "- B2 失败处置（预注册）：回滚 A2（新 reversal 分支），保留 A1（旧规则退役）。"]

    out = OUT / "ho004_acceptance.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    print(f"B1={b1} B2={b2} B3={b3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
