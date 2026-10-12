# RESEARCH ONLY - 未获用户批准不得正式运行
"""衰竭双假说 head-to-head：climax（CAND-001 放量+长影）vs absorption（M-EX-003 缩量）。

统一口径：下跌背景（close < sma20）+ 收盘位于当根区间上 1/3（多头反转侧），
差异只在量能方向：climax 要求 rvol>=2.0，absorption 要求 rvol<=0.8。
前瞻 5/10/20 根收益，6 品种合并。诊断性实验，非策略回测。
"""

from __future__ import annotations

import csv
from pathlib import Path

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "CAND-001"

SYMBOLS = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
           "CU": DATA / "SHFE" / "CU" / "CU.csv",
           "AG": DATA / "SHFE" / "AG" / "AG.csv",
           "M": DATA / "DCE" / "M" / "M.csv",
           "MA": DATA / "CZCE" / "MA" / "MA.csv",
           "TA": DATA / "CZCE" / "TA" / "TA.csv"}
HORIZONS = (5, 10, 20)


def load(path):
    dts, o, h, l, c, v = [], [], [], [], [], []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dts.append(r["datetime"])
            o.append(float(r["open"]))
            h.append(float(r["high"]))
            l.append(float(r["low"]))
            c.append(float(r["close"]))
            v.append(float(r["volume"]))
    return dts, o, h, l, c, v


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # GT 阶段标签（RS012 真值侧产物）
    gt_all = {}
    for sym in SYMBOLS:
        gp = OUT.parent / "RS012" / f"{sym}_gt_labels.csv"
        if gp.exists():
            with gp.open(newline="", encoding="utf-8") as f:
                gt_all[sym] = {r["datetime"]: r["gt_label"]
                               for r in csv.DictReader(f)}
    res = {"climax": defaultdict(list), "absorption": defaultdict(list),
           "climax_bear": defaultdict(list), "absorption_bear": defaultdict(list)}
    stage_res = defaultdict(lambda: defaultdict(list))   # stage -> hz -> [ret]
    for sym, path in SYMBOLS.items():
        dts, o, h, l, c, v = load(path)
        gtm = gt_all.get(sym, {})
        n = len(c)
        c20 = [None] * n
        v20 = [None] * n
        for i in range(19, n):
            c20[i] = sum(c[i - 19:i + 1]) / 20
            v20[i] = sum(v[i - 19:i + 1]) / 20
        for i in range(20, n - max(HORIZONS)):
            if c20[i] is None or v20[i] in (None, 0):
                continue
            rng = h[i] - l[i]
            if rng <= 0:
                continue
            body = abs(c[i] - o[i])
            uw = h[i] - max(o[i], c[i])            # 上影
            lw = min(o[i], c[i]) - l[i]            # 下影
            rvol = v[i] / v20[i]
            close_pos = (c[i] - l[i]) / rng
            # ---- 多头侧：下跌背景 + 收盘上 1/3 ----
            if c[i] < c20[i] and close_pos >= 0.66:
                tag = "climax" if (rvol >= 2.0 and lw >= 2 * max(body, 1e-9)) \
                    else ("absorption" if rvol <= 0.8 else None)
                if tag:
                    for hz in HORIZONS:
                        res[tag][hz].append((sym, c[i + hz] / c[i] - 1))
                    # absorption × 因果上下文（信号时刻过去20根收益分桶；
                    # 注意：不能用 GT 标签——前瞻标签给前瞻收益分桶是循环论证）
                    if tag == "absorption":
                        prior = c[i] / c[i - 20] - 1
                        pb = "deep_dn(<-5%)" if prior < -0.05 else \
                            ("mild_dn(-5~0)" if prior < 0 else "up(>0)")
                        for hz in (10, 20):
                            stage_res[pb][hz].append(c[i + hz] / c[i] - 1)
            # ---- 空头侧（镜像）：上涨背景 + 收盘下 1/3 ----
            if c[i] > c20[i] and close_pos <= 0.34:
                tag = "climax_bear" if (rvol >= 2.0 and uw >= 2 * max(body, 1e-9)) \
                    else ("absorption_bear" if rvol <= 0.8 else None)
                if tag:
                    for hz in HORIZONS:
                        res[tag][hz].append((sym, c[i + hz] / c[i] - 1))
    lines = ["# 衰竭双假说 head-to-head（下跌背景+收盘上1/3，多头方向）", "",
             "climax=rvol>=2.0 且 下影>=2x实体；absorption=rvol<=0.8（M-EX-003 口径）", ""]
    for tag in ("climax", "absorption", "climax_bear", "absorption_bear"):
        title = {"climax": "climax（多头）", "absorption": "absorption（多头）",
                 "climax_bear": "climax 空头镜像（上涨背景+收盘下1/3）",
                 "absorption_bear": "absorption 空头镜像"}[tag]
        lines.append(f"## {title}")
        lines.append("| 前瞻期 | n | 胜率 | 平均收益 | 中位收益 |")
        lines.append("|---|---|---|---|---|")
        for hz in HORIZONS:
            xs = res[tag][hz]
            if not xs:
                continue
            rets = [r for _, r in xs]
            rets_s = sorted(rets)
            win = sum(1 for r in rets if r > 0) / len(rets)
            avg = sum(rets) / len(rets)
            med = rets_s[len(rets) // 2]
            lines.append(f"| {hz}根 | {len(rets)} | {win * 100:.1f}% | "
                         f"{avg * 100:.3f}% | {med * 100:.3f}% |")
        lines.append("")
    # 分品种 20 根
    lines.append("## 分品种（20 根前瞻，多头侧）")
    lines.append("| 品种 | climax n | climax 均值 | absorption n | absorption 均值 |")
    lines.append("|---|---|---|---|---|")
    for sym in SYMBOLS:
        row = [sym]
        for tag in ("climax", "absorption"):
            xs = [r for s, r in res[tag][20] if s == sym]
            row.append(f"{len(xs)}")
            row.append(f"{sum(xs) / len(xs) * 100:.3f}%" if xs else "-")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## 分品种（20 根前瞻，空头镜像；负均值=空头有效）")
    lines.append("| 品种 | climax_bear n | 均值 | absorption_bear n | 均值 |")
    lines.append("|---|---|---|---|---|")
    for sym in SYMBOLS:
        row = [sym]
        for tag in ("climax_bear", "absorption_bear"):
            xs = [r for s, r in res[tag][20] if s == sym]
            row.append(f"{len(xs)}")
            row.append(f"{sum(xs) / len(xs) * 100:.3f}%" if xs else "-")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## absorption 多头信号 × 因果上下文（信号时刻过去20根收益分桶）")
    lines.append("| 上下文 | 10根 n/均值 | 20根 n/均值 | 20根胜率 |")
    lines.append("|---|---|---|---|")
    for lab in ("deep_dn(<-5%)", "mild_dn(-5~0)", "up(>0)"):
        xs10 = stage_res[lab][10]
        xs20 = stage_res[lab][20]
        if not xs20:
            continue
        m10 = f"{sum(xs10) / len(xs10) * 100:.3f}%/{len(xs10)}" if xs10 else "-"
        m20 = f"{sum(xs20) / len(xs20) * 100:.3f}%/{len(xs20)}"
        win = f"{sum(1 for r in xs20 if r > 0) / len(xs20) * 100:.1f}%"
        lines.append(f"| {lab} | {m10} | {m20} | {win} |")
    (OUT / "h2h_exhaustion.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", OUT / "h2h_exhaustion.md")


if __name__ == "__main__":
    from collections import defaultdict
    main()
