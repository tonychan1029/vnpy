# RESEARCH ONLY - 未获用户批准不得正式运行
"""M-LV-002 等高低点扫损区（SMC 流动性池）操作化检验。

定义 v1 操作化（参数显式化）：
- 聚集：同侧最近 2 个已确认摆动点价差 <= 0.1×ATR（ATR 取第二点处）
- 刺穿：某根 high 超过聚集上沿 + 0.05×ATR（等高点；等低点镜像）
- 扫损：刺穿后 2 根内收盘收回聚集内侧
- 对照臂：刺穿后未收回（真突破，延续假说预期正）
前瞻 10/20 根。SMC 假说（扫损后反转）vs RS013 延续假说的直接对撞。
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
OUT = ROOT.parent / "assets" / "MLIB"

SYMBOLS = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
           "CU": DATA / "SHFE" / "CU" / "CU.csv",
           "AG": DATA / "SHFE" / "AG" / "AG.csv",
           "M": DATA / "DCE" / "M" / "M.csv",
           "MA": DATA / "CZCE" / "MA" / "MA.csv",
           "TA": DATA / "CZCE" / "TA" / "TA.csv"}
HORIZONS = (10, 20)


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
    res = defaultdict(lambda: defaultdict(list))   # arm -> hz -> [(sym, ret)]
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
        ls = [p for p in pivots if p.kind == "L"]

        def clusters(ps, side):
            """相邻同侧两点聚集 -> (level, ready_from_index)。"""
            out = []
            for a, b in zip(ps, ps[1:]):
                ia = a.index + 2           # 第二点确认需再等 k 根，保守用 b 确认后
                if b.index + 2 >= n or atr[b.index] in (None, 0):
                    continue
                if abs(b.price - a.price) <= 0.1 * atr[b.index]:
                    lvl = max(a.price, b.price) if side == "H" \
                        else min(a.price, b.price)
                    out.append((lvl, b.index + 2, side))
            return out

        events = []                        # (bar_index, type, level)
        for lvl, start, side in clusters(hs, "H") + clusters(ls, "L"):
            pierced = None
            for i in range(start, n):
                a = atr[i]
                if a in (None, 0):
                    continue
                if side == "H":
                    if pierced is None:
                        if h[i] > lvl + 0.05 * a:
                            pierced = i
                    else:
                        if c[i] < lvl:                       # 收回 -> 扫损
                            events.append((i, "sweep_" + side, lvl))
                            break
                        if i - pierced >= 2:                 # 未收回 -> 真突破
                            events.append((pierced, "break_" + side, lvl))
                            break
                else:
                    if pierced is None:
                        if l[i] < lvl - 0.05 * a:
                            pierced = i
                    else:
                        if c[i] > lvl:
                            events.append((i, "sweep_" + side, lvl))
                            break
                        if i - pierced >= 2:
                            events.append((pierced, "break_" + side, lvl))
                            break
        for bar_i, typ, _ in events:
            for hz in HORIZONS:
                if bar_i + hz < n:
                    res[typ][hz].append((sym, c[bar_i + hz] / c[bar_i] - 1))
    lines = ["# M-LV-002 等高低点扫损区检验（聚集0.1ATR/刺穿0.05ATR/2根收回）", "",
             "| 臂 | 前瞻 | n | 胜率 | 平均收益 | 扫损反转有效性 |",
             "|---|---|---|---|---|---|"]
    for arm in ("sweep_H", "break_H", "sweep_L", "break_L"):
        for hz in HORIZONS:
            xs = res[arm][hz]
            if not xs:
                continue
            rets = [r for _, r in xs]
            win = sum(1 for r in rets if r > 0) / len(rets)
            avg = sum(rets) / len(rets)
            if arm.startswith("sweep"):
                ok = (avg < 0) if arm.endswith("H") else (avg > 0)
                verdict = "✓ 反转成立" if ok else "✗ 反转不成立"
            else:
                ok = (avg > 0) if arm.endswith("H") else (avg < 0)
                verdict = "✓ 延续成立" if ok else "✗ 延续不成立"
            lines.append(f"| {arm} | {hz}根 | {len(rets)} | {win * 100:.1f}% | "
                         f"{avg * 100:.3f}% | {verdict} |")
    (OUT / "sweep_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("->", OUT / "sweep_check.md")


if __name__ == "__main__":
    main()
