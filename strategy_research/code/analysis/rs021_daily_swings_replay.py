# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS021：全市场日线波段选品历史回撤评估（goal-fdc6db7f）。

判据移植：Hermes pullback_screen.py analyze() 日线档（CFG['day'] 原参数）：
  窗口 W=120 根日线；zigzag θ=4.0%（h/l 极值比例确认）；最显著腿
  幅≥8.0%、≥4根、ER≥0.35、腿龄 2~45 根；回踩比例 pb∈[0.30,0.70]；
  MA 贴近 min(|c−SMA20|,|c−SMA60|)/c ≤3.0%；方向：升腿→long、降腿→short。
全市场：day/{EXCH}.{SYM}.csv 全量 91 品种（2005-2026 不等）；
后复权：DEC006 D-2（_detect_and_splice 同款移植+坏点护栏，逐品种）。

度量（选品质量口径，无成本无执行建模）：
  - 事件后 +5/+20/+60 日方向调整收益；分品种/分年/in-out(2022)/score 分桶；
  - 回撤：事件序 20 日收益累加曲线的最大回撤（重叠口径，如实标注）；
预注册判读（事前声明）：OOS(2022-) +20 日均值 >0 且胜率 >50% → 日线级
  波段选品有初步价值（进入扫描试点提案）；否则 → **不新增日线级选品**
  （负结果入档）。

行布局：8 元素 [day, dt, o, h, l, c, v, oi]，常量 I_* 自 rs020 模块复用。
输出：assets/RS021/daily_swings_drawdown.md
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.rs020_merge_backtest import (  # noqa: E402
    I_C, I_H, I_L, I_O, splice_adjust)

DATA_DAY = Path(r"D:\AIprj\tradereplay\data\day")
OUT = ROOT.parent / "assets" / "RS021"
SPLIT = "2022-01-01"
HORIZONS = (5, 20, 60)

CFG_DAY = dict(W=120, theta=4.0, min_leg=8.0, min_bars=4, min_er=0.35,
               ma_near=3.0, pb_lo=0.30, pb_hi=0.70, max_age=45)
MIN_PB_BARS = 2


def load_day_adj(path: Path):
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = (r.get("datetime") or r.get("date") or "")[:10]
            if d[:4] < "2005":
                continue
            try:
                o, h, l, c = (float(r["open"]), float(r["high"]),
                              float(r["low"]), float(r["close"]))
                v = float(r.get("volume") or 0)
                oi = float(r.get("position") or 0)
            except (ValueError, TypeError):
                continue
            if min(o, h, l, c) <= 0 or h / max(l, 1e-9) > 50:
                continue
            rows.append([d, d, o, h, l, c, v, oi])
    splice_adjust(rows)
    days = [r[0] for r in rows]
    return rows, days


def zigzag_day(seg, theta):
    """pullback_screen 同款 zigzag（h/l 极值比例确认）。"""
    piv = []
    trend = 0
    ext_i, ext_p = 0, seg[0][I_C]
    for i in range(1, len(seg)):
        hi, lo = seg[i][I_H], seg[i][I_L]
        if trend >= 0:
            if hi > ext_p:
                ext_i, ext_p = i, hi
            elif lo < ext_p * (1 - theta):
                piv.append((ext_i, "H"))
                trend = -1
                ext_i, ext_p = i, lo
        if trend <= 0:
            if lo < ext_p:
                ext_i, ext_p = i, lo
            elif hi > ext_p * (1 + theta):
                piv.append((ext_i, "L"))
                trend = 1
                ext_i, ext_p = i, hi
    return piv


def er_of(seg):
    if len(seg) < 2:
        return 0.0
    net = abs(seg[-1][I_C] - seg[0][I_C])
    path = sum(abs(seg[i][I_C] - seg[i - 1][I_C]) for i in range(1, len(seg)))
    return net / path if path > 0 else 0.0


def analyze_day(seg):
    """pullback_screen.analyze 日线档移植。返回 (dir, score) 或 None。"""
    W = CFG_DAY["W"]
    if len(seg) < W:
        return None
    s = seg[-W:]
    n = len(s)
    cur = s[-1][I_C]
    m20 = sum(x[I_C] for x in s[-20:]) / 20
    m60 = sum(x[I_C] for x in s[-60:]) / 60
    dev_ma = min(abs(cur - m20) / cur * 100 if m20 else 999,
                 abs(cur - m60) / cur * 100 if m60 else 999)
    piv = zigzag_day(s, CFG_DAY["theta"] / 100.0)
    if len(piv) < 2:
        return None
    best = None
    for k in range(len(piv) - 1):
        (a, ta), (b, tb) = piv[k], piv[k + 1]
        if b <= a:
            continue
        if ta == "L" and tb == "H":
            lo_, hi_ = s[a][I_L], s[b][I_H]
            amp = (hi_ - lo_) / lo_ * 100 if lo_ else 0
            d = "long"
        elif ta == "H" and tb == "L":
            hi_, lo_ = s[a][I_H], s[b][I_L]
            amp = (hi_ - lo_) / hi_ * 100 if hi_ else 0
            d = "short"
        else:
            continue
        if amp < CFG_DAY["min_leg"] or (b - a) < CFG_DAY["min_bars"]:
            continue
        if er_of(s[a:b + 1]) < CFG_DAY["min_er"]:
            continue
        age = n - 1 - b
        if age < MIN_PB_BARS or age > CFG_DAY["max_age"]:
            continue
        if best is None or b > best["b"]:
            best = {"a": a, "b": b, "dir": d, "amp": amp,
                    "er": er_of(s[a:b + 1]), "hi": hi_, "lo": lo_}
    if best is None:
        return None
    hi, lo = best["hi"], best["lo"]
    cur = s[-1][I_C]
    pb = ((hi - cur) / (hi - lo) if best["dir"] == "long"
          else (cur - lo) / (hi - lo)) if hi > lo else 0.0
    if not (CFG_DAY["pb_lo"] <= pb <= CFG_DAY["pb_hi"]) or \
            dev_ma > CFG_DAY["ma_near"]:
        return None
    s_amp = min(20, best["amp"] / (CFG_DAY["min_leg"] * 3) * 20)
    s_er = min(20, max(0, (best["er"] - CFG_DAY["min_er"]) /
                       (1 - CFG_DAY["min_er"]) * 20))
    s_pb = max(0, 30 - abs(pb - 0.5) / 0.2 * 30)
    s_ma = max(0, 30 - dev_ma / CFG_DAY["ma_near"] * 30)
    return {"dir": best["dir"], "score": s_amp + s_er + s_pb + s_ma}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(DATA_DAY.glob("*.csv"))
    events = []
    n_sym = 0
    print(f"universe: {len(files)} day csv")
    for path in files:
        base = path.stem
        exch, code = base.split(".", 1)
        rows, days = load_day_adj(path)
        n = len(rows)
        if n < CFG_DAY["W"] + 2:
            continue
        n_sym += 1
        start = CFG_DAY["W"] + CFG_DAY["max_age"] + 2
        for d in range(start, n - max(HORIZONS)):
            seg = rows[d - CFG_DAY["W"] + 1: d + 1]
            r = analyze_day(seg)
            if r is None:
                continue
            d_dir = 1 if r["dir"] == "long" else -1
            c0 = rows[d][I_C]
            fwd = {}
            for h in HORIZONS:
                if d + h < n:
                    fwd[h] = (rows[d + h][I_C] / c0 - 1) * d_dir
            events.append({"sym": code, "exch": exch, "day": days[d],
                           "dir": r["dir"], "score": r["score"], "fwd": fwd})
    print(f"events={len(events)} symbols={n_sym}")

    def agg(sub, h):
        v = [e["fwd"][h] for e in sub if h in e["fwd"]]
        if not v:
            return None
        return (len(v), sum(1 for x in v if x > 0) / len(v), sum(v) / len(v))

    def fmt(a):
        return f"{a[1]:.1%}（均值 {a[2]:+.2%}，n={a[0]}）" if a else "-"

    def multi_table(lines, title, groups):
        lines += [f"## {title}", "",
                  "| 口径 | " + " | ".join(f"+{k}日胜率（均值）" for k in HORIZONS)
                  + " |", "|---|" + "---|" * len(HORIZONS)]
        for name, sub in groups:
            cells = []
            for h in HORIZONS:
                a = agg(sub, h)
                cells.append(fmt(a) if a else "-")
            lines.append("| " + name + " | " + " | ".join(cells) + " |")

    L = ["# RS021 全市场日线波段选品历史回撤评估（判据=Hermes pullback 日线档）", "",
         f"- 全市场 {n_sym} 品种（day 91 CSV 中历史不足者自动剔除）；",
         "- 后复权（DEC006 同款）；事件=日线档判据入选日收盘；",
         "- 收益=方向调整收盘口径、无成本无执行建模（选品质量口径）；",
         "- 预注册判读：OOS +20 日均值 >0 且胜率 >50% → 有初步价值；",
         "  否则不新增日线级选品（负结果入档）。", ""]

    groups_all = [("全样本", events),
                  ("in <2022", [e for e in events if e["day"] < SPLIT]),
                  ("out ≥2022", [e for e in events if e["day"] >= SPLIT])]
    multi_table(L, "1. 总体与 in/out", groups_all)

    by_year = defaultdict(list)
    for e in events:
        if 20 in e["fwd"]:
            by_year[e["day"][:4]].append(e["fwd"][20])
    L += ["", "## 3. 分年度（+20 日）", "",
          "| 年 | n | 胜率 | 均值 |", "|---|---|---|---|"]
    neg_years = 0
    for y in sorted(by_year):
        v = by_year[y]
        m = sum(v) / len(v)
        if m < 0:
            neg_years += 1
        L.append(f"| {y} | {len(v)} | {sum(1 for x in v if x > 0) / len(v):.1%} | "
                 f"{m:+.2%} |")

    by_key = defaultdict(list)
    for e in events:
        if 20 in e["fwd"]:
            by_key[(e["exch"], e["sym"])].append(e["fwd"][20])
    sym_stats = sorted(((k, len(v), sum(v) / len(v)) for k, v in by_key.items()),
                       key=lambda x: x[2])
    n_pos = sum(1 for _, _, a in sym_stats if a > 0)
    L += ["", "## 4. 分品种（+20 日）", "",
          f"- 品种 {len(sym_stats)} 个，正收益 {n_pos} 个",
          "- 最差 5：" + ("；".join(f"{e}.{s} {a:+.2%}(n={n})"
                                    for (e, s), n, a in sym_stats[:5])
                          if sym_stats else "-"),
          "- 最好 5：" + ("；".join(f"{e}.{s} {a:+.2%}(n={n})"
                                    for (e, s), n, a in sym_stats[-5:])
                          if sym_stats else "-"), ""]

    seq = sorted([e for e in events if 20 in e["fwd"]], key=lambda x: x["day"])
    cumv = peak = mdd = 0.0
    for e in seq:
        cumv += e["fwd"][20]
        peak = max(peak, cumv)
        mdd = max(mdd, peak - cumv)
    consec = mx = 0
    for e in seq:
        if e["fwd"][20] < 0:
            consec += 1
            mx = max(mx, consec)
        else:
            consec = 0
    L += ["", "## 5. 回撤度量（事件序 20 日收益累加，窗口重叠口径）", "",
          f"- 事件 {len(seq)}；累计 {cumv:+.1%}；**最大回撤 {mdd:.1%}（同口径）**",
          f"- 最长连续亏损事件 {mx} 笔", ""]

    L += ["", "## 6. score 分桶（+20 日）", "",
          "| score 桶 | n | 胜率 | 均值 |", "|---|---|---|---|"]
    for lo_s, hi_s in ((0, 40), (40, 60), (60, 80), (80, 101)):
        v = [e["fwd"][20] for e in events
             if 20 in e["fwd"] and lo_s <= e["score"] < hi_s]
        if v:
            L.append(f"| [{lo_s},{hi_s}) | {len(v)} | "
                     f"{sum(1 for x in v if x > 0) / len(v):.1%} | "
                     f"{sum(v) / len(v):+.2%} |")
        else:
            L.append(f"| [{lo_s},{hi_s}) | 0 | - | - |")

    L += ["", "## 诚实声明", "",
          "- 全市场 91 品种、后复权（DEC006）、收盘口径、无成本无执行建模；",
          "- 事件窗口重叠（逐日入选）；日线下无 15m/5m 触发确认环节——",
          "  与生产接力链（选品→任务单→择时信号K）之间存在口径差距；",
          "- 机械判读为预注册阈值输出；启用/退役决定权在用户。"]

    out = OUT / "daily_swings_drawdown.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    s20 = [e["fwd"][20] for e in events if 20 in e["fwd"]]
    print(f"events={len(events)} +20d win={sum(1 for x in s20 if x>0)/len(s20):.1%} "
          f"avg={sum(s20)/len(s20):+.2%} neg_years={neg_years}")


if __name__ == "__main__":
    main()
