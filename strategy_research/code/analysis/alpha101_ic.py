# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS013 预备：Alpha101 纯时序代表因子 × 时序 IC × 真值阶段条件分解。

因子（RS005 口径期货改写）：
- alpha12 = sign(dV) * (-dC)          —— M-DV 族连续对照基线
- alpha9  = 条件动量（Delta(close,1) 的 ts_min/ts_max 条件符号）
- mom6    = close/close[-6] - 1       —— 经典动量 sanity 基线
IC = 因子值与 20 根前瞻收益的 Pearson 相关（时序口径，研究级粗筛）；
并按 RS012 GT 标签分解（检验"阶段门控是否增效"）。
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_parent = ROOT.parent
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
GT_DIR = ROOT.parent / "assets" / "RS012"
OUT = ROOT.parent / "assets" / "RS013"

SYMBOLS = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
           "CU": DATA / "SHFE" / "CU" / "CU.csv",
           "AG": DATA / "SHFE" / "AG" / "AG.csv",
           "M": DATA / "DCE" / "M" / "M.csv",
           "MA": DATA / "CZCE" / "MA" / "MA.csv",
           "TA": DATA / "CZCE" / "TA" / "TA.csv"}
H = 20
NON_OVLP = True   # True: IC 采样点间隔 H 根（前瞻窗不重叠，剔除显著性虚高）


def load(path: Path):
    dts, closes, vols, opens, highs, lows = [], [], [], [], [], []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dts.append(r["datetime"])
            opens.append(float(r["open"]))
            highs.append(float(r["high"]))
            lows.append(float(r["low"]))
            closes.append(float(r["close"]))
            vols.append(float(r["volume"]))
    return dts, opens, highs, lows, closes, vols


def sign(x):
    return (x > 0) - (x < 0)


def factors(opens, highs, lows, closes, vols):
    """研究级近似移植（RS005 口径）：quesval/quesval2 语义未与 alpha 库逐字对拍，
    标注 `近似`；窗口/条件按公开论文口径。"""
    n = len(closes)
    out = {k: [None] * n for k in
           ("alpha6", "alpha9x", "alpha12", "alpha21", "alpha23", "alpha24",
            "alpha26", "alpha35", "alpha43", "mom6")}

    sum100_hist: list[float] = []
    ma8_hist: list[float] = []
    tr_hist = []                                    # delta(close,1) 历史
    vol_ratio_hist = []                             # volume/ma20 历史
    d7_hist = []                                    # -delta(close,7) 历史
    vol_ma20_hist = []
    high_ma20_hist = []
    tv5_hist: list[float] = []                      # ts_rank(volume,5)
    th5_hist: list[float] = []                      # ts_rank(high,5)
    corr_hist: list[float] = []                     # corr(tv5,th5,5)
    ret_hist: list[float] = []
    chl_hist: list[float] = []                      # close+high-low
    s100_prev = None
    for i in range(1, n):
        dv = vols[i] - vols[i - 1]
        dc = closes[i] - closes[i - 1]
        out["alpha12"][i] = sign(dv) * (-dc)
        if i >= 6:
            d7_hist.append(-(closes[i] - closes[i - 7]))
        if i >= 2:
            d1, d0 = dc, closes[i - 1] - closes[i - 2]
            # alpha9 近似（论文口径窗口=5，此处 2，先验已登记）
            if 0 < min(d1, d0) or 0 > max(d1, d0):
                out["alpha9x"][i] = d1
            else:
                out["alpha9x"][i] = -d1
        # alpha6: -ts_corr(open, volume, 10)
        if i >= 10:
            xs, ys = opens[i - 9:i + 1], vols[i - 9:i + 1]
            mx, my = sum(xs) / 10, sum(ys) / 10
            cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
            vx = sum((a - mx) ** 2 for a in xs) ** 0.5
            vy = sum((b - my) ** 2 for b in ys) ** 0.5
            out["alpha6"][i] = -(cov / (vx * vy)) if vx and vy else None
        # alpha23 近似: high > ma20(high) -> -delta(high,2) else 0
        high_ma20_hist.append(sum(highs[max(0, i - 19):i + 1]) /
                              len(highs[max(0, i - 19):i + 1]))
        if len(high_ma20_hist) >= 20:
            out["alpha23"][i] = (- (highs[i] - highs[i - 2])
                                 if highs[i] > high_ma20_hist[-1] else 0.0)
        # alpha21 近似: 布林带突破 fade + 量能条件
        w8 = closes[max(0, i - 7):i + 1]
        ma8 = sum(w8) / len(w8)
        std8 = (sum((c - ma8) ** 2 for c in w8) / len(w8)) ** 0.5
        ma2 = (closes[i - 1] + closes[i]) / 2
        ma20v = (sum(vols[max(0, i - 19):i + 1]) /
                 len(vols[max(0, i - 19):i + 1]))
        if len(w8) >= 8:
            if ma2 > ma8 + std8:
                out["alpha21"][i] = -1.0
            elif ma2 < ma8 - std8:
                out["alpha21"][i] = 1.0
            else:
                out["alpha21"][i] = 1.0 if ma20v > 0 and vols[i] / ma20v < 1 \
                    else -1.0
        # alpha24 近似: 100 日均线增速条件
        s100 = sum(closes[max(0, i - 99):i + 1])
        if s100_prev is not None and i >= 100:
            growth = (s100 / 100 - s100_prev / 100) / closes[i - 100]
            if growth < 0.05:
                out["alpha24"][i] = -(closes[i] - closes[i - 3])
            else:
                out["alpha24"][i] = -(closes[i] - min(closes[max(0, i - 99):i + 1]))
        s100_prev = s100
        # alpha26 近似: -ts_max(corr(ts_rank(vol,5), ts_rank(high,5), 5), 3)
        wv = vols[max(0, i - 4):i + 1]
        wh = highs[max(0, i - 4):i + 1]
        if len(wv) >= 5:
            rv = sum(1 for x in wv if x <= vols[i]) / 5
            rh = sum(1 for x in wh if x <= highs[i]) / 5
            tv5_hist.append(rv)
            th5_hist.append(rh)
            if len(tv5_hist) >= 5:
                xs = tv5_hist[-5:]
                ys = th5_hist[-5:]
                mx, my = sum(xs) / 5, sum(ys) / 5
                cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
                vx = sum((a - mx) ** 2 for a in xs) ** 0.5
                vy = sum((b - my) ** 2 for b in ys) ** 0.5
                c5 = cov / (vx * vy) if vx and vy else 0.0
                corr_hist.append(c5)
                if len(corr_hist) >= 3:
                    out["alpha26"][i] = -max(corr_hist[-3:])
        # alpha35 近似
        ret = closes[i] / closes[i - 1] - 1 if closes[i - 1] else None
        if ret is not None:
            ret_hist.append(ret)
        chl_hist.append(closes[i] + highs[i] - lows[i])
        w32v = vols[max(0, i - 31):i + 1]
        r32v = sum(1 for x in w32v if x <= vols[i]) / len(w32v) if len(w32v) >= 32 else None
        w16c = chl_hist[-15:] + [chl_hist[-1]]
        r16c = sum(1 for x in w16c if x <= chl_hist[-1]) / len(w16c) \
            if len(chl_hist) >= 16 else None
        w32r = ret_hist[-31:] + [ret_hist[-1]]
        r32r = sum(1 for x in w32r if x <= ret_hist[-1]) / len(w32r) \
            if len(w32r) >= 32 and ret_hist else None
        if None not in (r32v, r16c, r32r):
            out["alpha35"][i] = r32v * (1 - r16c) * (1 - r32r)
        # alpha43: ts_rank(vol/ma20vol, 20) * ts_rank(-delta7, 8)
        vol_ma20_hist.append(ma20v)
        if len(vol_ma20_hist) >= 20 and len(d7_hist) >= 8:
            vr = vols[i] / ma20v if ma20v else None
            if vr is not None:
                w1 = vol_ratio_hist[-19:] + [vr]
                lo1, hi1 = min(w1), max(w1)
                r1 = (w1.count(0) + sum(1 for x in w1 if x <= vr)) / len(w1) \
                    if hi1 > lo1 else 0.5
                w2 = d7_hist[-7:] + [d7_hist[-1]]
                lo2, hi2 = min(w2), max(w2)
                cur = d7_hist[-1]
                r2 = (w2.count(0) + sum(1 for x in w2 if x <= cur)) / len(w2) \
                    if hi2 > lo2 else 0.5
                out["alpha43"][i] = r1 * r2
            vol_ratio_hist.append(vr)
        if closes[i - 6] > 0:
            out["mom6"][i] = closes[i] / closes[i - 6] - 1
    return out


def pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 30:
        return None, len(pairs)
    xs, ys = zip(*pairs)
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs) ** 0.5
    vy = sum((b - my) ** 2 for b in ys) ** 0.5
    return (cov / (vx * vy) if vx and vy else None), len(pairs)


def pct_ranks(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [None] * len(vals)
    for rank, i in enumerate(order):
        out[i] = rank / max(len(vals) - 1, 1)
    return out


def pooled_stage_ic(per_sym, labels=("BREAKOUT", "RANGE", "REVERSAL",
                                     "TREND_DN", "TREND_UP")):
    """跨品种合并的非重叠条件 IC：品种内百分位秩后按阶段合并。"""

    pool = {(name, lab): ([], []) for name in
            ("alpha6", "alpha9x", "alpha12", "alpha21", "alpha23", "alpha24",
             "alpha26", "alpha35", "alpha43", "mom6")
            for lab in labels}
    for sym in per_sym:
        dts, series_by, fwd = per_sym[sym]["dts"], per_sym[sym]["fac"], per_sym[sym]["fwd"]
        gt = per_sym[sym]["gt"]
        idx_all = [i for i in range(40, len(dts) - H, H)]
        for name in series_by:
            series = series_by[name]
            valid = [i for i in idx_all if series[i] is not None and fwd[i] is not None]
            if len(valid) < 30:
                continue
            rk_f = pct_ranks([series[i] for i in valid])
            rk_r = pct_ranks([fwd[i] for i in valid])
            for pos, i in enumerate(valid):
                lab = gt.get(dts[i])
                if (name, lab) in pool:
                    pool[(name, lab)][0].append(rk_f[pos])
                    pool[(name, lab)][1].append(rk_r[pos])
    out = {}
    for key, (xs, ys) in pool.items():
        out[key] = pearson(xs, ys) if len(xs) >= 30 else (None, len(xs))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# RS013 预备结果：时序 IC（20 根前瞻收益）与真值阶段条件分解", ""]
    per_sym = {}
    for sym, path in SYMBOLS.items():
        dts, opens, highs, lows, closes, vols = load(path)
        fac = factors(opens, highs, lows, closes, vols)
        fwd = [None] * len(closes)
        for i in range(len(closes) - H):
            fwd[i] = closes[i + H] / closes[i] - 1
        gt = {}
        gt_path = GT_DIR / f"{sym}_gt_labels.csv"
        if gt_path.exists():
            with gt_path.open(newline="", encoding="utf-8") as f:
                gt = {r["datetime"]: r["gt_label"] for r in csv.DictReader(f)}
        per_sym[sym] = {"dts": dts, "fac": fac, "fwd": fwd, "gt": gt}
        lines.append(f"## {sym}")
        lines.append("| 因子 | 全样本 IC | n | " + " | ".join(
            ["BREAKOUT", "RANGE", "REVERSAL", "TREND_DN", "TREND_UP"]) + " |")
        lines.append("|" + "---|" * 9)
        for name in ("alpha6", "alpha9x", "alpha12", "alpha21", "alpha23",
                     "alpha24", "alpha26", "alpha35", "alpha43", "mom6"):
            series = fac[name]
            if NON_OVLP:
                idx_all = list(range(40, len(closes) - H, H))
            else:
                idx_all = list(range(len(closes)))
            ic, n = pearson([series[i] for i in idx_all],
                            [fwd[i] for i in idx_all])
            cells = []
            for lab in ("BREAKOUT", "RANGE", "REVERSAL", "TREND_DN", "TREND_UP"):
                idx = [i for i, d in enumerate(dts) if gt.get(d) == lab]
                ic_l, n_l = pearson([series[i] for i in idx],
                                    [fwd[i] for i in idx])
                cells.append(f"{ic_l:+.3f}({n_l})" if ic_l is not None else "-")
            lines.append(f"| {name} | {ic:+.3f} | {n} | " + " | ".join(cells) + " |")
        lines.append("")

    lines += ["## 跨品种合并（非重叠采样 + 品种内百分位秩）", ""]
    lines += ["| 因子 | " + " | ".join(["BREAKOUT", "RANGE", "REVERSAL",
                                        "TREND_DN", "TREND_UP"]) + " |",
              "|" + "---|" * 6]
    labels = ("BREAKOUT", "RANGE", "REVERSAL", "TREND_DN", "TREND_UP")
    pooled = pooled_stage_ic(per_sym)
    for name in ("alpha6", "alpha9x", "alpha12", "alpha21", "alpha23",
                 "alpha24", "alpha26", "alpha35", "alpha43", "mom6"):
        cells = []
        for lab in labels:
            ic, n = pooled[(name, lab)]
            cells.append(f"{ic:+.3f}({n})" if ic is not None else f"-({n})")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines.append("")

    # ---- CAND-007 设计参数：mom6 衰减曲线 + 阈值曲线（BREAKOUT 段，合并口径）----
    lines += ["## CAND-007 设计参数（mom6 × BREAKOUT，合并非重叠口径）", ""]

    # 统一重载：每个品种保留 closes 与 BREAKOUT 采样点（间隔 H，全 horizon 通用）
    sample = []           # (mom6, dts_i, closes_ref, i)  用 dict 按 sym 索引
    per_closes = {}
    for sym, path in SYMBOLS.items():
        dd, opens, highs, lows, closes, vols = load(path)
        fac = factors(opens, highs, lows, closes, vols)
        m6 = fac["mom6"]
        per_closes[sym] = closes
        gt_path = GT_DIR / f"{sym}_gt_labels.csv"
        with gt_path.open(newline="", encoding="utf-8") as f:
            gtm = {r["datetime"]: r["gt_label"] for r in csv.DictReader(f)}
        pts = [(i, m6[i]) for i in range(40, len(closes) - 40, H)
               if m6[i] is not None and gtm.get(dd[i]) == "BREAKOUT"]
        sample.append((sym, closes, pts))

    # 衰减曲线：不同前瞻期的 BREAKOUT 段 IC
    lines += ["### 衰减曲线（BREAKOUT 段 IC @ 前瞻期）", "",
              "| 前瞻期(根) | 5 | 10 | 20 | 40 |", "|---|---|---|---|---|"]
    row = []
    for hz in (5, 10, 20, 40):
        xs, ys = [], []
        for sym, closes, pts in sample:
            for i, v in pts:
                if i + hz < len(closes):
                    xs.append(v)
                    ys.append(closes[i + hz] / closes[i] - 1)
        ic, n = pearson(xs, ys)
        row.append(f"{ic:+.3f}(n={n})" if ic is not None else "-")
    lines.append("| IC | " + " | ".join(row) + " |")

    # 阈值曲线：mom6 品种内百分位分桶 -> 20 根前瞻均收益
    lines += ["", "### 阈值曲线（BREAKOUT 段，mom6 品种内百分位分桶 -> 20 根前瞻均收益）",
              "", "| mom6 分位桶 | 0-20% | 20-40% | 40-60% | 60-80% | 80-100% |",
              "|---|---|---|---|---|---|"]
    buckets = [[] for _ in range(5)]
    for sym, closes, pts in sample:
        vals = [v for _, v in pts]
        if len(vals) < 30:
            continue
        ranks = pct_ranks(vals)
        for (i, _), rk in zip(pts, ranks):
            if i + 20 < len(closes):
                buckets[min(int(rk * 5), 4)].append(closes[i + 20] / closes[i] - 1)
    lines.append("| 平均收益 | " + " | ".join(
        f"{sum(b) / len(b) * 100:.2f}%" if b else "-" for b in buckets) + " |")
    lines.append("| n | " + " | ".join(str(len(b)) for b in buckets) + " |")
    lines.append("")
    (OUT / "ic_preliminary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", OUT / "ic_preliminary.md")


if __name__ == "__main__":
    main()
