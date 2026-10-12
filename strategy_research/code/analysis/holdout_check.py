# RESEARCH ONLY - 未获用户批准不得正式运行
"""样本外保留段复测：三个头条结论在每品种最后 20% 时间段是否存活。

H1: mom6 在 BREAKOUT 段 IC 为正（RS013）
H2: absorption 多头（下跌背景+缩量+收盘上1/3）20根正收益（RS014）
H3: 等高点聚集真突破延续为正（M-LV-002 检验副产品）
每品种按时间 80/20 切分，仅用保留段样本。GT 标签沿用 RS012 全期产物
（标签由数据自身定义，切分只影响信号采样窗口）。
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from methods.pa_methods import m_pt_001_confirmed_pivots  # noqa: E402

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
GT_DIR = ROOT.parent / "assets" / "RS012"
OUT = ROOT.parent / "assets" / "MLIB"

SYMBOLS = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
           "CU": DATA / "SHFE" / "CU" / "CU.csv",
           "AG": DATA / "SHFE" / "AG" / "AG.csv",
           "M": DATA / "DCE" / "M" / "M.csv",
           "MA": DATA / "CZCE" / "MA" / "MA.csv",
           "TA": DATA / "CZCE" / "TA" / "TA.csv"}
H = 20


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


def pearson(xs, ys):
    n = len(xs)
    if n < 30:
        return None, n
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = sum((a - mx) ** 2 for a in xs) ** 0.5
    vy = sum((b - my) ** 2 for b in ys) ** 0.5
    return (cov / (vx * vy)) if vx and vy else None, n


def stats(rets):
    if not rets:
        return None
    return len(rets), sum(1 for r in rets if r > 0) / len(rets), \
        sum(rets) / len(rets)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# 样本外保留段复测（每品种时间后 20%，H1/H2/H3）", ""]
    # H1
    xs, ys = [], []
    for sym, path in SYMBOLS.items():
        dts, o, h, l, c, v = load(path)
        n = len(c)
        gtm = {}
        gp = GT_DIR / f"{sym}_gt_labels.csv"
        if gp.exists():
            with gp.open(newline="", encoding="utf-8") as f:
                gtm = {r["datetime"]: r["gt_label"] for r in csv.DictReader(f)}
        for i in range(int(n * 0.8), n - H, H):
            if i + H >= n or c[i - 6] <= 0:
                continue
            if gtm.get(dts[i]) != "BREAKOUT":
                continue
            m6 = c[i] / c[i - 6] - 1
            xs.append(m6)
            ys.append(c[i + H] / c[i] - 1)
    ic, n = pearson(xs, ys)
    lines.append(f"- **H1 mom6×BREAKOUT IC（保留段）**: "
                 f"{f'{ic:+.3f} (n={n})' if ic is not None else 'n 不足'}"
                 f"{' ✓ 存活' if ic and ic > 0.1 else ' ✗ 未存活/衰减'}")
    # H2
    rets2 = []
    for sym, path in SYMBOLS.items():
        dts, o, h, l, c, v = load(path)
        n = len(c)
        c20 = [None] * n
        v20 = [None] * n
        for i in range(19, n):
            c20[i] = sum(c[i - 19:i + 1]) / 20
            v20[i] = sum(v[i - 19:i + 1]) / 20
        for i in range(max(20, int(n * 0.8)), n - 20):
            if c20[i] in (None, 0) or v20[i] in (None, 0):
                continue
            rng = h[i] - l[i]
            if rng <= 0:
                continue
            rvol = v[i] / v20[i]
            close_pos = (c[i] - l[i]) / rng
            if c[i] < c20[i] and close_pos >= 0.66 and rvol <= 0.8:
                rets2.append(c[i + 20] / c[i] - 1)
    s = stats(rets2)
    lines.append(f"- **H2 absorption 多头（保留段）**: " +
                 (f"n={s[0]}, 胜率 {s[1] * 100:.1f}%, 均值 {s[2] * 100:.3f}%"
                  f"{' ✓ 存活' if s[2] > 0 else ' ✗ 未存活'}" if s else "n 不足"))
    # H3
    rets3 = []
    for sym, path in SYMBOLS.items():
        dts, o, h, l, c, v = load(path)
        n = len(c)
        tr = [h[i] - l[i] if i == 0 else
              max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
              for i in range(n)]
        atr = [None] * n
        for i in range(13, n):
            atr[i] = sum(tr[i - 13:i + 1]) / 14
        pivots = m_pt_001_confirmed_pivots(h, l, k=2)
        hs = [p for p in pivots if p.kind == "H"]
        for a, b in zip(hs, hs[1:]):
            if b.index + 2 >= n or atr[b.index] in (None, 0):
                continue
            if abs(b.price - a.price) > 0.1 * atr[b.index]:
                continue
            lvl = max(a.price, b.price)
            pierced = None
            for i in range(max(b.index + 2, int(n * 0.8)), n):
                if atr[i] in (None, 0):
                    continue
                if pierced is None:
                    if h[i] > lvl + 0.05 * atr[i]:
                        pierced = i
                else:
                    if c[i] < lvl:
                        break
                    if i - pierced >= 2:
                        if pierced + 20 < n:
                            rets3.append(c[pierced + 20] / c[pierced] - 1)
                        break
    s = stats(rets3)
    lines.append(f"- **H3 等高点聚集真突破（保留段）**: " +
                 (f"n={s[0]}, 胜率 {s[1] * 100:.1f}%, 均值 {s[2] * 100:.3f}%"
                  f"{' ✓ 存活' if s[2] > 0.002 else ' ✗ 未存活'}" if s else "n 不足"))
    lines += ["", "注：保留段样本量约为全样本 1/5，幅度衰减属正常；"
              "判定标准为方向与量级（H1 IC>0.1、H2>0、H3>0.2%）"]
    (OUT / "holdout_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", OUT / "holdout_check.md")


if __name__ == "__main__":
    main()
