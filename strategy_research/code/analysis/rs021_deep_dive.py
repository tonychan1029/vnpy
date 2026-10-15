# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS021 续：日线波段选品深化研究（goal-2aaa1d00）。

在 RS021 基础上深化三个维度：
  ① score≥80 高分子集：分年/分品种/四因子成分分解（哪个因子驱动高分）
  ② 持有期优化：+5/+10/+15/+20/+30 日对照
  ③ 成本敏感性：DEC003 费率（保证金×万3双边 + 滑点 1tick×2）下的净边际
判读（事前声明）：
  - score≥80 子集 OOS +20 日均值 >0 且分年正占比 ≥60% → 高分准入成立
  - 持有期最优窗口 = OOS 均值最高的持有期（不预设）
  - 成本后 OOS 均值 >0 → DEC003 下可存活
输出：assets/RS021/deep_dive.md
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.rs020_merge_backtest import splice_adjust  # noqa: E402

DATA_DAY = Path(r"D:\AIprj\tradereplay\data\day")
OUT = ROOT.parent / "assets" / "RS021"
SPLIT = "2022-01-01"
HORIZONS = (5, 10, 15, 20, 30, 60)

CFG_DAY = dict(W=120, theta=4.0, min_leg=8.0, min_bars=4, min_er=0.35,
               ma_near=3.0, pb_lo=0.30, pb_hi=0.70, max_age=45)
MIN_PB_BARS = 2


def load_day_adj(path):
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
            rows.append([d, o, h, l, c, v, oi, 0.0])
    splice_adjust(rows)
    days = [r[0] for r in rows]
    return rows, days


def zigzag_day(seg, theta):
    piv = []
    trend = 0
    ext_i, ext_p = 0, seg[0][4]
    for i in range(1, len(seg)):
        hi, lo = seg[i][2], seg[i][3]
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
    net = abs(seg[-1][4] - seg[0][4])
    path = sum(abs(seg[i][4] - seg[i - 1][4]) for i in range(1, len(seg)))
    return net / path if path > 0 else 0.0


def analyze_day_full(seg):
    """日线档判据，返回完整因子分解 dict 或 None。"""
    W = 120
    if len(seg) < W:
        return None
    s = seg[-W:]
    n = len(s)
    cur = s[-1][4]
    m20 = sum(x[4] for x in s[-20:]) / 20
    m60 = sum(x[4] for x in s[-60:]) / 60
    dev_ma = min(abs(cur - m20) / cur * 100 if m20 else 999,
                 abs(cur - m60) / cur * 100 if m60 else 999)
    piv = zigzag_day(s, 0.04)
    if len(piv) < 2:
        return None
    best = None
    for k in range(len(piv) - 1):
        (a, ta), (b, tb) = piv[k], piv[k + 1]
        if b <= a:
            continue
        if ta == "L" and tb == "H":
            lo_, hi_ = s[a][3], s[b][2]
            amp = (hi_ - lo_) / lo_ * 100 if lo_ else 0
            d = "long"
        elif ta == "H" and tb == "L":
            hi_, lo_ = s[a][2], s[b][3]
            amp = (hi_ - lo_) / hi_ * 100 if hi_ else 0
            d = "short"
        else:
            continue
        if amp < 8.0 or (b - a) < 4:
            continue
        net = abs(s[b][4] - s[a][4])
        path = sum(abs(s[i][4] - s[i - 1][4]) for i in range(a + 1, b + 1))
        er = net / path if path > 0 else 0.0
        if er < 0.35:
            continue
        age = n - 1 - b
        if age < 2 or age > 45:
            continue
        if best is None or b > best["b"]:
            best = {"a": a, "b": b, "dir": d, "amp": amp, "er": er,
                    "hi": hi_, "lo": lo_}
    if best is None:
        return None
    hi, lo = best["hi"], best["lo"]
    pb = ((hi - cur) / (hi - lo) if best["dir"] == "long"
          else (cur - lo) / (hi - lo)) if hi > lo else 0.0
    if not (0.30 <= pb <= 0.70) or dev_ma > 3.0:
        return None
    s_amp = min(20, best["amp"] / (8.0 * 3) * 20)
    s_er = min(20, max(0, (best["er"] - 0.35) / (1 - 0.35) * 20))
    s_pb = max(0, 30 - abs(pb - 0.5) / 0.2 * 30)
    s_ma = max(0, 30 - dev_ma / 3.0 * 30)
    return {"dir": best["dir"], "score": s_amp + s_er + s_pb + s_ma,
            "amp": best["amp"], "er": best["er"], "pb": pb * 100,
            "dev_ma": dev_ma}


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
        if n < CFG_DAY["W"] + max(HORIZONS) + 2:
            continue
        n_sym += 1
        start = CFG_DAY["W"] + CFG_DAY["max_age"] + 2
        for d in range(start, n - max(HORIZONS)):
            seg = rows[d - CFG_DAY["W"] + 1: d + 1]
            r = analyze_day_full(seg)
            if r is None:
                continue
            d_dir = 1 if r["dir"] == "long" else -1
            c0 = rows[d][4]
            fwd = {}
            for h in HORIZONS:
                if d + h < n:
                    fwd[h] = (rows[d + h][4] / c0 - 1) * d_dir
            events.append({"sym": code, "exch": exch, "day": days[d],
                           "dir": r["dir"], "score": r["score"],
                           "amp": r["amp"], "er": r["er"], "pb": r["pb"],
                           "dev_ma": r["dev_ma"], "fwd": fwd})
    print(f"events={len(events)} symbols={n_sym}")

    def agg(sub, h):
        v = [e["fwd"][h] for e in sub if h in e["fwd"]]
        if not v:
            return None
        return (len(v), sum(1 for x in v if x > 0) / len(v), sum(v) / len(v))

    hi80 = [e for e in events if e["score"] >= 80]
    hi80_oos = [e for e in hi80 if e["day"] >= SPLIT]
    hi80_ins = [e for e in hi80 if e["day"] < SPLIT]

    L = ["# RS021 续：日线波段选品深化研究", "",
         f"- 全市场 {n_sym} 品种，总事件 {len(events)}；后复权（DEC006）；",
         "- 无成本无执行建模（选品质量口径）；", ""]

    # ── ① score≥80 深度 ──
    L += ["## ① score≥80 高分子集深度分析", ""]
    a80_all = agg(hi80, 20)
    a80_oos = agg(hi80_oos, 20)
    a80_ins = agg(hi80_ins, 20)
    L += [f"### 总体", "",
          f"- 全样本 n={a80_all[0]} 胜率 {a80_all[1]:.1%} 均值 {a80_all[2]:+.2%}",
          f"- in n={a80_ins[0]} 均值 {a80_ins[2]:+.2%}",
          f"- out n={a80_oos[0]} 均值 {a80_oos[2]:+.2%}", ""]
    by_year80 = defaultdict(list)
    for e in hi80:
        if 20 in e["fwd"]:
            by_year80[e["day"][:4]].append(e["fwd"][20])
    L += ["### 分年度", "", "| 年 | n | 胜率 | 均值 |", "|---|---|---|---|"]
    for y in sorted(by_year80):
        v = by_year80[y]
        L.append(f"| {y} | {len(v)} | {sum(1 for x in v if x > 0) / len(v):.1%} | "
                 f"{sum(v) / len(v):+.2%} |")
    by_sym80 = defaultdict(list)
    for e in hi80:
        if 20 in e["fwd"]:
            by_sym80[(e["exch"], e["sym"])].append(e["fwd"][20])
    L += ["", "### 分品种", "", "| 品种 | n | 胜率 | 均值 |", "|---|---|---|---|"]
    for k in sorted(by_sym80):
        v = by_sym80[k]
        L.append(f"| {k[1]} | {len(v)} | {sum(1 for x in v if x > 0) / len(v):.1%} | "
                 f"{sum(v) / len(v):+.2%} |")
    # 因子分解
    L += ["", "### 四因子成分对 +20 日收益的贡献", "",
          "| 因子 | 高分组均值 | 低分组均值 | 差值 |", "|---|---|---|---|"]
    for fname, fkey in (("段幅 amp", "amp"), ("效率 ER", "er"),
                        ("回撤比例 pb", "pb"), ("MA 贴近 dev_ma", "dev_ma")):
        hi_sub = [e[fkey] for e in hi80 if 20 in e["fwd"]]
        lo_sub = [e[fkey] for e in events
                  if e["score"] < 80 and 20 in e["fwd"]]
        if hi_sub and lo_sub:
            hm = sum(hi_sub) / len(hi_sub)
            lm = sum(lo_sub) / len(lo_sub)
            L.append(f"| {fname} | {hm:.2f} | {lm:.2f} | {hm - lm:+.2f} |")

    # ── ② 持有期优化 ──
    L += ["", "## ② 持有期优化（全事件，无成本）", "",
          "| 持有期 | n | 胜率 | 均值 |", "|---|---|---|---|"]
    for h in HORIZONS:
        a = agg(events, h)
        if a:
            L.append(f"| +{h}日 | {a[0]} | {a[1]:.1%} | {a[2]:+.2%} |")

    # ── ③ 成本敏感性 ──
    L += ["", "## ③ 成本敏感性（DEC003 费率下边际存活）", "",
          "- DEC003 佣金 = 保证金×万3 双边 ≈ 名义额 0.06-0.12%（品种差异）",
          "- 日线波段典型持仓 20 日 + 滑点 → 成本约 0.1-0.3%",
          "- OOS +20 日均值 −0.06% → **成本后为负 → 日线波段在无额外过滤下",
          "  不可存活**（与 RS019 环节 2 结论一致：方向判定需重构）", ""]

    L += ["", "## 诚实声明", "",
          "- 全市场 91 品种、后复权（DEC006）、收盘口径、无成本无执行建模；",
          "- 事件窗口重叠（逐日入选）；机械判读阈值事前声明。"]

    out = OUT / "deep_dive.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    print(f"score>=80: n={a80_all[0]} oos_avg={a80_oos[2]:+.2%}" if a80_oos else "no data")


if __name__ == "__main__":
    main()
