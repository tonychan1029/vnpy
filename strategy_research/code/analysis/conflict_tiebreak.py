# RESEARCH ONLY - 未获用户批准不得正式运行
"""编排冲突裁决实验：同窗反向信号对（突破 vs 回调）该听谁的。

样本：基线 signals_detail 中同品种、方向相反、bar_time 相差 ≤5 根的
（突破族, 回调族）信号对。
裁决指标：对窗口起点后 20 根的真实方向（c[t0+20]/c[t0]−1 符号），
统计「跟随突破」vs「跟随回调」各自的正确率与净 R（1R/笔名义）。
输出：S-004 编排的数据驱动 tie-break 规则。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"
HORIZON = 20
WIN = timedelta(hours=5)

FAMILY = {
    "BREAKOUT_KEY_LEVEL": "突破", "H2L2_TREND": "突破",
    "FAKE_BREAKOUT_REVERSE": "突破",
    "STRUCTURE_PULLBACK": "回调", "EMA20_PULLBACK": "回调",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    closes_map = {}
    for sym in ("RB", "CU", "AG", "M", "MA", "TA"):
        exch = {"RB": "SHFE", "CU": "SHFE", "AG": "SHFE",
                "M": "DCE", "MA": "CZCE", "TA": "CZCE"}[sym]
        p = DATA / exch / sym / f"{sym}.csv"
        dts, closes = [], []
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                dts.append(datetime.strptime(r["datetime"],
                                             "%Y-%m-%d %H:%M:%S"))
                closes.append(float(r["close"]))
        closes_map[sym] = (dts, closes)

    def fwd(sign_sym, dt):
        dts, closes = closes_map[sign_sym]
        # 找 >= dt 的最近根
        lo, hi = 0, len(dts) - 1
        if dt > dts[-1]:
            return None
        while lo < hi:
            mid = (lo + hi) // 2
            if dts[mid] < dt:
                lo = mid + 1
            else:
                hi = mid
        i = lo
        if i + HORIZON >= len(closes):
            return None
        return closes[i + HORIZON] / closes[i] - 1

    # 突破族与回调族逐笔（触发与否都算事件——冲突在信号层）
    ev = defaultdict(lambda: ([], []))   # sym -> (break_events, pull_events)
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            fam = FAMILY.get(r["signal_id"])
            if fam is None:
                continue
            try:
                dt = datetime.strptime(r["bar_time"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            lst, oth = ev[r["symbol"]]
            if fam == "突破":
                lst.append((dt, 1 if r["direction"] == "long" else -1))
            else:
                oth.append((dt, 1 if r["direction"] == "long" else -1))
    fol_b = [0, 0]      # 跟随突破 [对, 错]
    fol_p = [0, 0]
    n_pair = 0
    used_b = set()
    used_p = set()
    for sym, (b_events, p_events) in ev.items():
        b_events.sort()
        p_events.sort()
        for bt, bd in b_events:
            for pt, pd in p_events:
                if abs((pt - bt).total_seconds()) > WIN.total_seconds():
                    continue
                if pd == bd:
                    continue                    # 只看反向对
                key = (sym, bt, pt)
                if key in used_b or key in used_p:
                    continue
                used_b.add(key)
                used_p.add(key)
                fw = fwd(sym, min(bt, pt))
                if fw is None:
                    continue
                n_pair += 1
                true_dir = 1 if fw > 0 else -1
                if bd == true_dir:
                    fol_b[0] += 1
                else:
                    fol_b[1] += 1
                if pd == true_dir:
                    fol_p[0] += 1
                else:
                    fol_p[1] += 1
    lines = ["# 编排冲突裁决实验（突破 vs 回调 同窗反向对）", "",
             f"- 冲突对：{n_pair}（窗口 ±5 根，裁决=对窗口起点后 20 根真实方向）", ""]
    if n_pair:
        lines.append("| 跟随方 | 正确 | 错误 | 正确率 | 期望净R（±1R/笔） |")
        lines.append("|---|---|---|---|---|")
        for name, (ok, bad) in (("突破", fol_b), ("回调", fol_p)):
            lines.append(f"| {name} | {ok} | {bad} | {ok / n_pair * 100:.1f}% | "
                         f"{(ok - bad):+d}R |")
        lines += ["", "判读：正确率显著高于 50% 的一方获得编排优先权；"
                  "双方都 ≈50% 则冲突对按'双双降权'处理（同窗反向=互证无效）。"]
    (OUT / "conflict_tiebreak.md").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")
    print("->", OUT / "conflict_tiebreak.md")


if __name__ == "__main__":
    main()
