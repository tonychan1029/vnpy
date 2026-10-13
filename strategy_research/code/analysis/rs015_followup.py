# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS015 追加执行（DEC005 批复）：方案 B 的 GT v2 重测 + 方案 B2 的 range 特征屏幕。

【方案 B：REVERSAL 真值 v2（锚定第一腿）——预注册定义，重测后才谈 tagger v2】
  在 v1.1 协议（TREND→RANGE→REVERSAL→BREAKOUT→UNDEFINED 优先级、TREND/RANGE/
  BREAKOUT/UNDEFINED 定义不变）基础上，仅 REVERSAL 替换为：
    REVERSAL_v2（第一腿 as_of 锚定）：
      回看 40 根（closes[i-40:i]，不含当前根）：H=max，tH=argmax，
        leg_up = H − min(back[:tH+1]) ≥ 1.5×ATR 且 tH ≤ i−1（极值非当前根）
      前瞻 20 根：min(fwd) ≤ H − 1.5×ATR（第二腿完成）
      往返收口：|fwd[-1] − c[i]| < 1.5×ATR
      （下行镜像对称）
  协议纯洁性损失（DEC005 已接受）：leg1 依赖 as_of 数据。
  判读（RS015 §2.3 预注册）：候选列精确率 ≥30% 才谈 tagger v2；
  全族 <30% → 方案 B 证伪，回退 A/C 再议。

【方案 B2：RANGE 新特征屏幕——预注册特征清单与晋升规则】
  单特征（GT v1.1 口径，同 stage-1 网格）：
    F1 波动收缩 ATR14/ATR56 ≤ 0.85
    F2 边缘触碰计数 ≥3（当前 40 根区间内 close 落在边缘 ±0.25×ATR 的根数）
    F3 ER40 ≤ 0.30
    F4 net40 < 1.5×ATR
    F5 40 根带宽 ≤ 6×ATR（v1 宽度条件单列）
    F6 中部位置 |close−mid40| ≤ 0.25×带宽
    F7 带宽分位 ≤ 0.5（(hi40−lo40)/ATR14 的 500 根滚动分位）
  组合（固定）：C1=NR4∧F1；C2=NR4∧F2；C3=F2∧F3（NR4=net20<1ATR∧ER20≤0.30∧内带15%）
  晋升规则（预注册）：out 段列精确率 ≥30% 且 LR ≥1.8 且触发 ≥8% 才进 v2 提案；
  否则屏幕归档（负/弱结果），range 维持 v1 宽口径+门控存疑降权。

输出：assets/RS015/rev2_retest_and_range_screen.md
"""

from __future__ import annotations

import csv
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # strategy_research/code
sys.path.insert(0, str(ROOT))

from analysis.context_v2_diagnostic import (   # noqa: E402  复用 stage-1 同一 harness
    DATA, SYMBOLS, adapt, atr_series, build_feats, chain_pred, ema_series,
    evaluate, fractal_pivots, load_bars, rng_v1, rev_v1, REV_RULES)

GT_DIR = ROOT.parent / "assets" / "RS012"
OUT = ROOT.parent / "assets" / "RS015"
STEP = 4
HORIZON = 20
REV2_ROWS: list = []     # (sym, dt, gt_v2, pred, candidate, placement)


# ── GT v2（仅 REVERSAL 替换；其余与 context_eval.ground_truth_label 一致）──
def gt_label_v2(closes, atr, as_of, horizon=HORIZON, consist=0.6):
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

    back = closes[max(0, as_of - 40): as_of]        # 不含当前根
    if back:
        tH = max(range(len(back)), key=lambda j: back[j])
        H = back[tH]
        leg_up = H - min(back[:tH + 1])
        tL = min(range(len(back)), key=lambda j: back[j])
        Lw = back[tL]
        leg_dn = max(back[:tL + 1]) - Lw
        # 极值非当前根：back 已不含 as_of，tH/tL ≤ i−1 自然满足
        rev_up = leg_up >= 1.5 * atr and min(fwd) <= H - 1.5 * atr \
            and abs(net) < 1.5 * atr
        rev_dn = leg_dn >= 1.5 * atr and max(fwd) >= Lw + 1.5 * atr \
            and abs(net) < 1.5 * atr
        if rev_up or rev_dn:
            return "REVERSAL"

    if max(fwd) > hi40 and max(fwd) - hi40 >= 2 * atr:
        return "BREAKOUT"
    if min(fwd) < lo40 and lo40 - min(fwd) >= 2 * atr:
        return "BREAKOUT"
    return "UNDEFINED"


# ── B2 特征（在 stage-1 Feats 上追加；as-of 可算，40 根窗不含当前根）──
class Feats2:
    __slots__ = ("base", "f1", "f2", "f3", "f4", "f5", "f6", "f7")

    def __init__(self, base) -> None:
        self.base = base
        self.f1 = self.f2 = self.f3 = False
        self.f4 = self.f5 = self.f6 = self.f7 = False

    def __getattr__(self, name):          # slots 未命中 → 委托 stage-1 特征
        return getattr(self.base, name)


def build_feats2(i, closes, highs, lows, emas, atr, pivL, pivH, a56):
    base = build_feats(i, closes, highs, lows, emas, atr, pivL, pivH)
    f = Feats2(base)
    c = closes[i]
    pre = closes[i - 40: i]
    hi40, lo40 = max(pre), min(pre)
    w = hi40 - lo40
    f.f1 = a56 is not None and a56 > 0 and atr / a56 <= 0.85
    tol = 0.25 * atr
    f.f2 = sum(1 for x in pre if x <= lo40 + tol or x >= hi40 - tol) >= 3
    net40 = abs(c - closes[i - 40])
    f.f4 = net40 < 1.5 * atr
    f.f5 = w <= 6 * atr
    f.f6 = abs(c - (hi40 + lo40) / 2) <= 0.25 * w
    return f


def nr4(f):
    b = f.base
    return b.net20 < 1.0 * b.atr and b.er20 <= 0.30 and b.inner


def mk_c1(f):
    return nr4(f) and f.f1


def mk_c2(f):
    return nr4(f) and f.f2


def mk_c3(f):
    return f.f2 and f.f3


def _rng_v1(f):
    return rng_v1(f.base)


SCREEN_RULES = (
    ("V1 宽口径(现行)", _rng_v1),
    ("F1 波动收缩≤0.85", lambda f: f.f1),
    ("F2 边缘触碰≥3", lambda f: f.f2),
    ("F3 ER40≤0.30", lambda f: f.f3),
    ("F4 net40<1.5ATR", lambda f: f.f4),
    ("F5 带宽≤6ATR", lambda f: f.f5),
    ("F6 中部位置", lambda f: f.f6),
    ("F7 带宽分位≤0.5", lambda f: f.f7),
    ("C1=NR4∧F1", mk_c1),
    ("C2=NR4∧F2", mk_c2),
    ("C3=F2∧F3", mk_c3),
)


def _rng_v1(f):
    from analysis.context_v2_diagnostic import rng_v1
    return rng_v1(f.base)


def breakout_hyst(closes, atrs, n):
    """复刻 ContextTaggerV1 breakout 迟滞（enter 2 / exit 5）。"""
    bo = [False] * n
    streak = nb = in_bo = 0
    for i in range(40, n):
        a = atrs[i]
        if a is None or a <= 0:
            bo[i] = in_bo
            continue
        pre = closes[i - 40: i]
        hi40, lo40 = max(pre), min(pre)
        raw = closes[i] > hi40 + 0.1 * a or closes[i] < lo40 - 0.1 * a
        if raw:
            streak += 1
            nb = 0
            if streak >= 2:
                in_bo = True
        else:
            nb += 1
            streak = 0
            if nb >= 5:
                in_bo = False
        bo[i] = in_bo
    return bo


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # ── Part 1：GT v2 重标 + reversal 候选重测 ──
    cnt: dict = {}
    for sym, exch in SYMBOLS.items():
        dts, highs, lows, closes = load_bars(DATA / exch / sym / f"{sym}.csv")
        atrs = atr_series(highs, lows, closes)
        emas = ema_series(closes)
        pivL, pivH = fractal_pivots(highs, lows)
        n = len(closes)
        labels = {}
        for as_of in range(40, n - HORIZON - 1, STEP):
            a = atrs[as_of]
            if a is None or a <= 0 or emas[as_of] is None or as_of < 45:
                continue
            lab = gt_label_v2(closes, a, as_of)
            if lab == "UNDEFINED":
                continue
            labels[dts[as_of]] = lab
            cnt[lab] = cnt.get(lab, 0) + 1
        with (OUT / f"{sym}_gt_rev2_labels.csv").open("w", newline="",
                                                      encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["datetime", "gt_label"])
            for d, lab in labels.items():
                w.writerow([d, lab])
        bo = breakout_hyst(closes, atrs, n)
        dt2i = {d: k for k, d in enumerate(dts)}
        for d, g in labels.items():
            i = dt2i.get(d)
            if i is None:
                continue
            ft = build_feats(i, closes, highs, lows, emas, atrs[i], pivL, pivH)
            for name, rule, plc in REV_RULES:
                p = adapt(chain_pred(ft, bo[i], rng_v1, rule, plc == "hi"), ft)
                REV2_ROWS.append((sym, d, g, p, name, plc))

    # ── Part 2：B2 特征屏幕（GT v1.1 网格）──
    rows_screen = {name: [] for name, _ in SCREEN_RULES}
    for sym, exch in SYMBOLS.items():
        dts, highs, lows, closes = load_bars(DATA / exch / sym / f"{sym}.csv")
        atrs = atr_series(highs, lows, closes)
        a56 = [None] * len(closes)
        trs = []
        for ii in range(1, len(closes)):
            tr = max(highs[ii] - lows[ii], abs(highs[ii] - closes[ii - 1]),
                     abs(lows[ii] - closes[ii - 1]))
            trs.append(tr)
            if len(trs) >= 56:
                a56[ii] = sum(trs[-56:]) / 56
        emas = ema_series(closes)
        pivL, pivH = fractal_pivots(highs, lows)
        n = len(closes)
        bo = breakout_hyst(closes, atrs, n)
        gtv1 = {}
        with (GT_DIR / f"{sym}_gt_labels.csv").open(newline="",
                                                    encoding="utf-8") as f:
            gtv1 = {r["datetime"]: r["gt_label"] for r in csv.DictReader(f)}
        dt2i = {d: k for k, d in enumerate(dts)}
        band_q: deque = deque()
        for d, g in gtv1.items():
            i = dt2i.get(d)
            if i is None or i < 60 or atrs[i] in (None, 0) or emas[i] is None:
                continue
            ft = build_feats2(i, closes, highs, lows, emas, atrs[i], pivL,
                              pivH, a56[i])
            b = ft.base
            net40 = abs(closes[i] - closes[i - 40])
            path40 = sum(abs(closes[j] - closes[j - 1])
                         for j in range(i - 39, i + 1))
            ft.f3 = path40 > 0 and net40 / path40 <= 0.30
            pre = closes[i - 40: i]
            w40 = (max(pre) - min(pre)) / atrs[i]
            band_q.append(w40)
            if len(band_q) > 500:
                band_q.popleft()
            sq = sorted(band_q)
            ft.f7 = sum(1 for x in sq if x <= w40) / len(sq) <= 0.5
            for name, rule in SCREEN_RULES:
                p = adapt(chain_pred(ft, bo[i], rule, rev_v1, False), ft)
                rows_screen[name].append((sym, d, g, p))

    # ── 报告 ──
    L = ["# RS015 追加执行：方案 B（GT v2 重测）+ 方案 B2（range 特征屏幕）", "",
         "- DEC005 批准（2026-10-13）；候选/晋升规则预注册于脚本头，未因结果增删。",
         "- 方案 B 网格：GT v2 重标（STEP=4/horizon=20/ATR14，REVERSAL 锚定替换）。",
         "- B2 屏幕：GT v1.1 网格（与 stage-1 诊断同点集）。", ""]

    L += ["## 1. GT v2 标签分布（v1.1 对照：REVERSAL 19.2% / RANGE 17.5%）", "",
          "| 标签 | 占比 |", "|---|---|"]
    tot = sum(cnt.values())
    for k in ("TREND_UP", "TREND_DN", "RANGE", "REVERSAL", "BREAKOUT"):
        L.append(f"| {k} | {cnt.get(k, 0) / tot:.1%} |")

    L += ["", "## 2. 方案 B：reversal 候选 × GT v2（预注册线：列精确率 ≥30%）", "",
          "| 候选 | 位置 | 触发 | 占比 | 列精确率 | LR | 召回 | in | out |",
          "|---|---|---|---|---|---|---|---|---|"]
    best, best_key = 0.0, None
    for name, plc in dict.fromkeys((nm, p) for nm, _, p in REV_RULES):
        rows = [(s, d, g, p) for s, d, g, p, nm, pc in REV2_ROWS
                if nm == name and pc == plc]
        r = evaluate(rows, "REVERSAL")
        if r["prec"] > best:
            best, best_key = r["prec"], (name, plc)
        io = r["io"]
        fins = f"{io['in'][0]:.1%}" if io["in"][0] is not None else "-"
        fouts = f"{io['out'][0]:.1%}" if io["out"][0] is not None else "-"
        L.append(f"| {name} | {plc} | {r['fires']} | {r['share']:.1%} | "
                 f"**{r['prec']:.1%}** | {r['lr']:.2f} | {r['recall']:.1%} | "
                 f"{fins} | {fouts} |")
    gate = best >= 0.30
    L += ["", f"**方案 B 判读（预注册线 30%）：最优 {best_key} 列精确率 "
          f"{best:.1%} → "
          f"{'达标，进入 tagger v2 议题' if gate else '未达标——方案 B 证伪，回退 A/C 再议'}**"]

    L += ["", "## 3. 方案 B2：range 特征屏幕（GT v1.1；晋升线：out 精确率 ≥30% 且 LR ≥1.8 且触发 ≥8%）",
          "", "| 规则 | 触发 | 占比 | 列精确率 | LR | top-pred | in | out |",
          "|---|---|---|---|---|---|---|---|"]
    promoted = []
    for name, _ in SCREEN_RULES:
        r = evaluate(rows_screen[name], "RANGE")
        io = r["io"]
        fins = f"{io['in'][0]:.1%}" if io["in"][0] is not None else "-"
        fouts = f"{io['out'][0]:.1%}" if io["out"][0] is not None else "-"
        ok = (io["out"][0] is not None and io["out"][0] >= 0.30
              and r["lr"] >= 1.8 and r["share"] >= 0.08)
        if ok:
            promoted.append(name)
        L.append(f"| {name} | {r['fires']} | {r['share']:.1%} | "
                 f"**{r['prec']:.1%}** | {r['lr']:.2f} | {r['top']:.1%} | "
                 f"{fins} | {fouts} |")
    if promoted:
        promo_txt = "：" + "、".join(promoted)
    else:
        promo_txt = "——无晋升，range 维持 v1 宽口径+门控存疑降权（B2 屏幕负/弱结果归档）"
    L += ["", f"**B2 判读：晋升 {len(promoted)} 条{promo_txt}**"]

    out = OUT / "rev2_retest_and_range_screen.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)


if __name__ == "__main__":
    main()
