# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS021 带成本复算（阶段0-2；ROADMAP §1A 0-2；双口径强制）。

管线=rs021_daily_swings_replay.py 逐字复用（导入 analyze_day/load_day_adj），
新增：事件收益按 analysis.cost（DEC003+1tick）扣减，双列报告。
预注册判读（原口径 + 成本约束）：OOS(2022-) +20 日**可交易口径** >0 且胜率
>50% → 维持"通过初步门槛"；否则整体降级"未证实方向"；score≥80 子集同判。

输出：assets/RS021/daily_swings_costed.md
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.cost import cost_return  # noqa: E402
from analysis.rs021_daily_swings_replay import (  # noqa: E402
    CFG_DAY, HORIZONS, SPLIT, analyze_day, load_day_adj, I_C)

DATA_DAY = Path(r"D:\AIprj\tradereplay\data\day")
OUT = ROOT.parent / "assets" / "RS021"


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
                           "dir": r["dir"], "score": r["score"],
                           "entry": c0, "fwd": fwd})
    print(f"events={len(events)} symbols={n_sym}")

    def agg(sub, h, costed):
        v = []
        for e in sub:
            g = e["fwd"].get(h)
            if g is None:
                continue
            if costed:
                g = (1 + g) * (1 - cost_return(e["sym"], e["entry"])) - 1
            v.append(g)
        if not v:
            return None
        return (len(v), sum(1 for x in v if x > 0) / len(v), sum(v) / len(v))

    L = ["# RS021 带成本复算（阶段0-2 双口径；管线=原回放逐字复用）", "",
         f"- 全市场 {n_sym} 品种；成本=analysis.cost（DEC003+1tick）；",
         "- 预注册判读：OOS +20 日**可交易口径** >0 且胜率 >50% → 维持门槛；",
         "  否则整体降级“未证实方向”；score≥80 子集同判（重尾已标注）。", ""]

    groups = [("全样本", events, None),
              ("in <2022", [e for e in events if e["day"] < SPLIT], None),
              ("out ≥2022", [e for e in events if e["day"] >= SPLIT], None),
              ("score≥80 全", [e for e in events if e["score"] >= 80], None),
              ("score≥80 out", [e for e in events
                                if e["score"] >= 80 and e["day"] >= SPLIT],
               None)]
    L.append("| 组 | 成本 | +5日 | +20日 | +60日 |")
    L.append("|---|---|---|---|---|")
    for name, sub, _ in groups:
        for costed in (False, True):
            cells = []
            for h in (5, 20, 60):
                a = agg(sub, h, costed)
                cells.append(f"{a[1]:.1%}（{a[2]:+.2%}，n={a[0]}）"
                             if a else "-")
            L.append(f"| {name} | {'可交易' if costed else '无成本'} | "
                     + " | ".join(cells) + " |")

    L.append("")
    for name, sub in (("整体", [e for e in events if e["day"] >= SPLIT]),
                      ("score≥80", [e for e in events if e["score"] >= 80
                                    and e["day"] >= SPLIT])):
        a = agg(sub, 20, True)
        if a:
            ok = a[2] > 0 and a[1] > 0.5
            L.append(f"- **{name} OOS +20 可交易**：{a[2]:+.2%}"
                     f"（胜率 {a[1]:.1%}，n={a[0]}）→ "
                     + ("维持门槛 ✅" if ok else "**降级“未证实方向” ❌**"))

    L += ["", "## 诚实声明", "",
          "- 管线与 rs021_daily_swings_replay.py 同源（导入复用）；",
          "- 91 品种成本表仅 10 主连精确，其余按默认近似（cost.py 标注）；",
          "- 事件窗口重叠；收盘口径；score≥80 重尾（FB n=4）见 deep_dive。"]
    out = OUT / "daily_swings_costed.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    a = agg([e for e in events if e["day"] >= SPLIT], 20, True)
    if a:
        print(f"overall OOS+20 costed: n={a[0]} win={a[1]:.1%} avg={a[2]:+.2%}")


if __name__ == "__main__":
    main()
