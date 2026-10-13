# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS016 RER strict_range 正式实验（DEC005 批准执行；预注册于 20_research/RS016）。

臂矩阵（固定，不得临场增删）：
  C 主臂   strict_range==1 ∩ 形态（摆动沿触及±0.25ATR + pin/吞没；摆动点
           2根分形、确认滞后 p<=i-2、近 60 根内）
  A 对照   v1 宽口径 range 标签 ∩ 形态
  B 对照   裸形态（无标签）
  锚       基线轮次0 RANGE_EDGE_REVERSAL：n=133、avg_net_r +0.215（tier=p1，
           S-003 §5.2 / MTG004 §2）——口径不同，仅作量级参照

口径（RS016 §3 预注册）：
  1) 臂间对照口径：前瞻 20 根 close-to-close、方向调整、扣 0.06%（与
     rer_expand 可比；只用于臂间比较）
  2) 可交易性口径（主判据，G1-G4 全部以此为准）：信号K确认后下一根开盘
     入场；止损=信号K对侧极值±0.25×ATR（忠实 RangeEdgeDetector：多头
     stop=bar.low-0.25ATR）；T1=2R；horizon=40 根；同根双触先计止损
     （保守）；滑点 1 tick/侧；佣金=DEC003 保证金×万3 双边
     （fee_pts = 2×0.0003×margin_rate×entry）

判读（预注册，机械执行）：G1 in/out 净R均>0 且 out≥0.5×in；G2 n≥300 且
≥2×133；G3 ≥4/6 品种正 且 负年≤4/12；G4 TA 单列并列报告；空头仅记录。

输出：assets/RS016/rer_formal.md
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
TAGS = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\context_tags")
OUT = Path(__file__).resolve().parents[2] / "assets" / "RS016"
COST_FLAT = 0.0006          # 臂间口径：名义额双边万3近似
SPLIT = "2022-01-01"
HZ_CMP = 20                 # 臂间口径前瞻
HZ_TRD = 40                 # 可交易性口径 horizon
TOL_K = 0.25                # 触沿容差 / 止损偏移（同 engine level_touch_atr）
T1_R = 2.0                  # T1=2R

META = {  # 与 vnpy_patiming/baseline_backtest.py 权威 meta 一致
    "RB": ("SHFE", 10.0, 1.0, 0.10),
    "CU": ("SHFE", 5.0, 10.0, 0.10),
    "AG": ("SHFE", 15.0, 1.0, 0.12),
    "M": ("DCE", 10.0, 0.5, 0.08),
    "MA": ("CZCE", 10.0, 1.0, 0.09),
    "TA": ("CZCE", 5.0, 2.0, 0.09),
}
ANCHOR_N, ANCHOR_R = 133, 0.215


def pin(h, l, o, c, bull):
    body = abs(c - o)
    rng = h - l
    if rng <= 0 or body <= 0:
        return False
    lower = min(o, c) - l
    upper = h - max(o, c)
    if bull:
        return lower >= 2 * body and c >= l + rng / 3
    return upper >= 2 * body and c <= h - rng / 3


def engulf(o, c, po, pc, bull):
    if (pc > po) == bull:
        return False
    return min(o, c) <= min(po, pc) and max(o, c) >= max(po, pc)


def trade(dir_, entry, stop, bars_hi, bars_lo, bars_close, j0, tick, mrate):
    """可交易性口径：T1=2R / 止损优先 / horizon 到期平仓。返回 net_R 或 None。"""
    risk = dir_ * (entry - stop)
    if risk <= 0:
        return None                      # 跳空越过止损，弃用并计数
    t1 = entry + dir_ * T1_R * risk
    fee = 2 * 0.0003 * mrate * entry     # 保证金×万3 双边（点位）
    slip = 2 * tick
    for j in range(j0, min(j0 + HZ_TRD, len(bars_hi))):
        if dir_ > 0 and bars_lo[j] <= stop:
            px = stop
            break
        if dir_ < 0 and bars_hi[j] >= stop:
            px = stop
            break
        if dir_ > 0 and bars_hi[j] >= t1:
            px = t1
            break
        if dir_ < 0 and bars_lo[j] <= t1:
            px = t1
            break
    else:
        j = min(j0 + HZ_TRD, len(bars_hi)) - 1
        px = bars_close[j]
    return (dir_ * (px - entry) - slip - fee) / risk


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    events = []   # (sym, dt, side, tag, strict, ret_cmp, net_r)
    gap_skip = 0
    for sym, (exch, mult, tick, mrate) in META.items():
        dpath = DATA / exch / sym / f"{sym}.csv"
        dts, o, h, l, c = [], [], [], [], []
        with dpath.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(r["datetime"])
                o.append(float(r["open"]))
                h.append(float(r["high"]))
                l.append(float(r["low"]))
                c.append(float(r["close"]))
        n = len(c)
        tr = [h[i] - l[i] if i == 0 else
              max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
              for i in range(n)]
        atr = [None] * n
        for i in range(13, n):
            atr[i] = sum(tr[i - 13:i + 1]) / 14
        tag = [None] * n
        strict = [0] * n
        idx = {d: i for i, d in enumerate(dts)}
        with (TAGS / f"{sym}_context_tags.csv").open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                i = idx.get(r["datetime"])
                if i is not None:
                    tag[i] = (r.get("context_tag") or "").strip().lower()
                    strict[i] = int(r.get("strict_range") or 0)
        pivL = [i for i in range(2, n - 2)
                if all(l[i] < l[j] for j in range(i - 2, i + 3) if j != i)]
        pivH = [i for i in range(2, n - 2)
                if all(h[i] > h[j] for j in range(i - 2, i + 3) if j != i)]
        for i in range(20, n - 1 - HZ_TRD):
            a = atr[i]
            if a in (None, 0) or tag[i] is None:
                continue
            tol = TOL_K * a
            for side, piv, bull in (("long", pivL, True), ("short", pivH, False)):
                dir_ = 1 if bull else -1
                hit = None
                for p in reversed(piv):
                    if i - p < 2 or i - p > 60:        # p<=i-2 可确认，近 60 根
                        continue
                    px = l[p] if bull else h[p]
                    if bull and l[i] <= px + tol:
                        hit = px
                        break
                    if not bull and h[i] >= px - tol:
                        hit = px
                        break
                if hit is None:
                    continue
                if not (pin(h[i], l[i], o[i], c[i], bull)
                        or engulf(o[i], c[i], o[i - 1], c[i - 1], bull)):
                    continue
                ret_cmp = dir_ * (c[i + HZ_CMP] / c[i] - 1) - COST_FLAT
                entry = o[i + 1]
                stop = (l[i] - TOL_K * a) if bull else (h[i] + TOL_K * a)
                net = trade(dir_, entry, stop, h, l, c, i + 1, tick, mrate)
                if net is None:
                    gap_skip += 1
                    continue
                events.append((sym, dts[i], side, tag[i], strict[i], ret_cmp, net))

    # ── 汇总 ──────────────────────────────────────────────
    def agg(rows, key=lambda e: e[6], pct=False):
        """pct=True 用于收益率口径（×100 显示）；R 单位不乘。"""
        if not rows:
            return (0, None, None)
        xs = [key(e) for e in rows]
        win = sum(1 for x in xs if x > 0) / len(xs) * 100
        mul = 100 if pct else 1
        return (len(xs), win, sum(xs) / len(xs) * mul)

    L = ["# RS016 RER strict_range 正式实验结果（DEC005 批准，预注册机械判读）", "",
         f"- 事件（信号K×方向）：{len(events)}；跳空弃用：{gap_skip}",
         "- 可交易性口径：下一根开盘入场 / 止损=信号K对侧极值±0.25ATR / T1=2R /",
         "  horizon=40 / 滑点 1tick×2 / 佣金=DEC003 保证金×万3 双边", ""]

    C_long = [e for e in events if e[4] == 1 and e[2] == "long"]
    C_short = [e for e in events if e[4] == 1 and e[2] == "short"]
    A_all = [e for e in events if e[3] == "range"]
    B_all = list(events)

    Lin = [e for e in C_long if e[1] < SPLIT]
    Lout = [e for e in C_long if e[1] >= SPLIT]

    # G1-G3 主判据（C 多头，可交易性口径）
    n_all, win_all, r_all = agg(C_long)
    n_in, win_in, r_in = agg(Lin)
    n_out, win_out, r_out = agg(Lout)
    g1 = (r_in is not None and r_in > 0 and r_out is not None and r_out > 0
          and r_out >= 0.5 * r_in)
    g2 = n_all >= 300 and n_all >= 2 * ANCHOR_N

    per_sym = {}
    for sym in META:
        rows = [e for e in C_long if e[0] == sym]
        n_s, w_s, r_s = agg(rows)
        per_sym[sym] = (n_s, w_s, r_s)
    pos_syms = sum(1 for s in per_sym.values() if s[2] is not None and s[2] > 0)

    by_year = defaultdict(list)
    for e in C_long:
        by_year[e[1][:4]].append(e[6])
    neg_years = sum(1 for y in sorted(by_year)
                    if sum(by_year[y]) / len(by_year[y]) < 0)

    g3 = pos_syms >= 4 and neg_years <= 4

    L += ["## 1. 主判据：C 臂（strict_range∩形态）多头 · 可交易性口径", "",
          "| 段 | n | 胜率 | 平均净R |", "|---|---|---|---|"]
    for name, (nn, ww, rr) in (("in(2015-2021)", (n_in, win_in, r_in)),
                               ("out(2022-)", (n_out, win_out, r_out)),
                               ("全样本", (n_all, win_all, r_all))):
        rr_s = f"{rr:+.3f}" if rr is not None else "-"
        ww_s = f"{ww:.1f}%" if ww is not None else "-"
        L.append(f"| {name} | {nn} | {ww_s} | {rr_s} |")
    L += ["", f"- 基线锚参照：n={ANCHOR_N}、+{ANCHOR_R}（tier=p1，v0 闸门口径，仅量级对照）", "",
          "## 2. 预注册四门判读（机械执行）", "",
          f"| 门 | 标准 | 实测 | 判定 |", "|---|---|---|---|",
          f"| G1 有效性 | in/out 净R均>0 且 out≥0.5×in | in {r_in:+.3f} / out {r_out:+.3f} | "
          f"{'✅ PASS' if g1 else '❌ FAIL'} |",
          f"| G2 扩样 | n≥300 且 ≥2×{ANCHOR_N} | n={n_all} | "
          f"{'✅ PASS' if g2 else '❌ FAIL'} |",
          f"| G3 稳健性 | ≥4/6 品种正 且 负年≤4 | {pos_syms}/6 品种正、{neg_years} 负年 | "
          f"{'✅ PASS' if g3 else '❌ FAIL'} |"]
    ta_n, ta_w, ta_r = per_sym["TA"]
    L += [f"| G4 弱环专项 | TA 单列（仅记录/并列报告） | n={ta_n}、胜率 "
          f"{ta_w:.1f}%、{ta_r:+.3f} | 报告 |"]
    verdict = "G1–G3 全过 → 起草 HO004-RER 报用户批准" if (g1 and g2 and g3) \
        else "任一门 FAIL → 实验终止：RER 维持研究发现，不放宽现网闸门，负结果入档"
    L += ["", f"**机械结论：{verdict}**"]

    L += ["", "## 3. C 臂多头分品种", "",
          "| 品种 | n | 胜率 | 平均净R |", "|---|---|---|---|"]
    for sym, (nn, ww, rr) in per_sym.items():
        rr_s = f"{rr:+.3f}" if rr is not None else "-"
        ww_s = f"{ww:.1f}%" if ww is not None else "-"
        L.append(f"| {sym} | {nn} | {ww_s} | {rr_s} |")

    L += ["", "## 4. C 臂多头分年度", "",
          "| 年 | n | 平均净R |", "|---|---|---|"]
    for y in sorted(by_year):
        xs = by_year[y]
        L.append(f"| {y} | {len(xs)} | {sum(xs) / len(xs):+.3f} |")

    n_s_, w_s_, r_s_ = agg(C_short)
    L += ["", "## 5. 空头侧（仅记录，预注册不设假说）", "",
          f"C 臂空头：n={n_s_}、胜率 "
          f"{w_s_:.1f}%、平均净R {r_s_:+.3f}" if n_s_ else "C 臂空头：无样本"]

    L += ["", "## 6. 臂间对照口径（前瞻20根收益率，与 rer_expand 可比）", "",
          "| 臂 | 方向 | n | 胜率 | 平均净收益 |", "|---|---|---|---|---|"]
    for arm, rows in (("A 宽range∩形态", A_all), ("C strict∩形态", events),
                      ("B 裸形态", B_all)):
        for side in ("long", "short"):
            sub = [e for e in rows if e[2] == side]
            nn, ww, rr = agg(sub, key=lambda e: e[5], pct=True)
            if not nn:
                L.append(f"| {arm} | {side} | 0 | - | - |")
            else:
                L.append(f"| {arm} | {side} | {nn} | {ww:.1f}% | {rr:+.3f}% |")

    L += ["", "---", "",
          "*脚本：`code/analysis/rer_formal.py`（RESEARCH ONLY）；判读标准",
          "预注册于 `20_research/RS016_RER_strict_range正式实验设计.md` §4，",
          "本文件为机械执行输出，未做临场修改。",
          "执行记录：首跑因汇总层 R/百分比单位混用作废，修正后重跑",
          "（成交模拟与门判定两跑一致，重跑值即上表）。*"]
    out = OUT / "rer_formal.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    print(f"C_long n={n_all} in={r_in} out={r_out} | G1={g1} G2={g2} G3={g3} "
          f"({pos_syms}/6 sym, {neg_years} neg years)")


if __name__ == "__main__":
    main()
