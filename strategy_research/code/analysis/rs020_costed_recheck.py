# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS020 带成本复算（阶段0-2；ROADMAP §1A 0-2；双口径强制）。

管线=rs020_merge_backtest.py 修正版逐字复用（导入函数，双勘误后口径）：
  臂2（Hermes pullback 四因子+60m HH/HL 趋势过滤）、臂3（flats 箱体边缘）。
新增：事件收益按 analysis.cost（DEC003+1tick，阶段0-2 单一实现）扣减，
  同报 ①无成本 ②可交易 两列。

预注册判读：臂2/臂3 OOS(2022-) +20 日**可交易口径** >0 → "成立"维持；
  任一臂可交易口径 ≤0 → 该臂降级"未证实方向"，A1/A6 决策不得引用其无成本
  口径（ROADMAP 阶段0-2 约束）。
输出：assets/RS020/merge_backtest_costed.md
"""

from __future__ import annotations

import sys
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.cost import cost_return  # noqa: E402
from analysis.rs020_merge_backtest import (  # noqa: E402
    CFG5, FLAT, HORIZONS, SPLIT, SYMS, find_flats_v5, load_5m_adj,
    load_60m_raw, pullback_arm, trend_h1_60m, I_C, I_DT, I_DAY)

OUT = ROOT.parent / "assets" / "RS020"
TAIL60 = 300


def main():
    events = []          # {"arm","sym","td","entry","fwd":{h:gross}}
    for sym, exch in SYMS.items():
        rows, tdays, tclose, bad, bad_pts = load_5m_adj(sym, exch)
        h60 = load_60m_raw(sym, exch)
        dt5 = [r[I_DT] for r in rows]
        dt60 = [r[I_DT] for r in h60]
        by_day = defaultdict(list)
        for r in rows:
            by_day[r[I_DAY]].append(r)
        print(f"[load] {sym}: bars={len(rows)}")

        # ── 臂2（修正版：节点对齐过滤 + trend_h1 深拷贝平滑） ──
        for td in tdays:
            day_bars = by_day.get(td) or []
            if not day_bars:
                continue
            node = day_bars[-1]
            node_dt = node[I_DT]
            j5 = bisect_right(dt5, node_dt)
            tail5 = rows[max(0, j5 - 1500): j5]
            if len(tail5) < 500:
                continue
            j60 = bisect_right(dt60, node_dt)
            h60n = h60[max(0, j60 - TAIL60): j60]
            if len(h60n) < 60:
                continue
            th = trend_h1_60m(h60n)
            r = pullback_arm(tail5, CFG5)
            if r is None:
                continue
            if r["dir"] == "long" and th != "多头":
                continue
            if r["dir"] == "short" and th != "空头":
                continue
            events.append({"arm": "arm2", "sym": sym, "td": td,
                           "entry": node[I_C],
                           "d": 1 if r["dir"] == "long" else -1})

        # ── 臂3（flats 箱体边缘触碰，rs020 同款） ──
        flats = find_flats_v5(rows, window=FLAT["window"],
                              compress_thresh=FLAT["compress"],
                              gap_allow=FLAT["gap_allow"],
                              band_max_pct=FLAT["band_max"])
        for f in flats:
            e = f["end"]
            if e + 1 >= len(rows):
                continue
            brk = 0
            ok = True
            for j in range(e + 1, min(e + FLAT["tail_margin"] + 1, len(rows))):
                c = rows[j][I_C]
                if c > f["hi"] or c < f["lo"]:
                    brk += 1
                    if brk >= 2:
                        ok = False
                        break
                else:
                    brk = 0
            if not ok:
                continue
            node_bar = rows[min(e + FLAT["tail_margin"], len(rows) - 1)]
            c0 = node_bar[I_C]
            tol = 0.15 * (f["hi"] - f["lo"])
            d = "long" if c0 <= f["lo"] + tol else \
                "short" if c0 >= f["hi"] - tol else None
            if d is None:
                continue
            events.append({"arm": "arm3", "sym": sym,
                           "td": node_bar[I_DAY], "entry": c0,
                           "d": 1 if d == "long" else -1})

    # ── 前瞻（交易日映射，同 rs020） ──
    maps = {}
    for sym, exch in SYMS.items():
        _, tds, tcl, _, _ = load_5m_adj(sym, exch)
        maps[sym] = (tds, tcl)
    for e in events:
        tds, tcl = maps[e["sym"]]
        e["fwd"] = {}
        if e["td"] in tcl:
            i = tds.index(e["td"])
            for h in HORIZONS:
                j = i + h
                if j < len(tds):
                    e["fwd"][h] = (tcl[tds[j]] / e["entry"] - 1) * e["d"]

    # ── 报告 ──
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

    L = ["# RS020 带成本复算（阶段0-2 双口径；管线=修正版逐字复用）", "",
         "- 成本=analysis.cost（DEC003 佣金双边 + 1tick/边，往返名义比例）；",
         "- 预注册判读：OOS +20 日**可交易口径** >0 → 成立维持；否则降级"
         "“未证实方向”。", ""]
    verdict = {}
    for arm in ("arm2", "arm3"):
        sub_all = [e for e in events if e["arm"] == arm]
        L.append(f"## {arm}")
        L.append("| 口径 | 成本 | " + " | ".join(f"+{k}日胜率（均值）"
                 for k in HORIZONS) + " |")
        L.append("|---|---|" + "---|" * len(HORIZONS))
        for label, cond in (("全样本", lambda e: True),
                            ("in <2022", lambda e: e["td"] < SPLIT),
                            ("out ≥2022", lambda e: e["td"] >= SPLIT)):
            sub = [e for e in sub_all if cond(e)]
            for costed in (False, True):
                cells = []
                for h in HORIZONS:
                    a = agg(sub, h, costed)
                    cells.append(f"{a[1]:.1%}（{a[2]:+.2%}，n={a[0]}）"
                                 if a else "-")
                L.append(f"| {label} | {'可交易' if costed else '无成本'} | "
                         + " | ".join(cells) + " |")
        a20 = agg([e for e in sub_all if e["td"] >= SPLIT], 20, True)
        verdict[arm] = (a20[2] > 0) if a20 else None
        L.append(f"- **OOS +20 可交易口径判读**："
                 + (f"{a20[2]:+.2%}（n={a20[0]}）→ "
                    + ("**成立维持 ✅**" if verdict[arm] else
                       "**≤0 → 降级“未证实方向” ❌**")) if a20 else "- 无样本")
        L.append("")

    L += ["## 诚实声明", "",
          "- 管线与 rs020_merge_backtest.py 修正版同源（导入复用，双勘误后）；",
          "- 成本按事件收盘价折算（收盘口径非执行口径，滑点为近似）；",
          "- 本报告取代无成本口径作为 A1/A6 决策依据（ROADMAP 阶段0-2）。"]
    out = OUT / "merge_backtest_costed.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    for arm in ("arm2", "arm3"):
        sub = [e for e in events if e["arm"] == arm and e["td"] >= SPLIT]
        a = agg(sub, 20, True)
        if a:
            print(f"{arm} OOS+20 costed: n={a[0]} win={a[1]:.1%} avg={a[2]:+.2%}")


if __name__ == "__main__":
    main()
