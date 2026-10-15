# RESEARCH ONLY - 视觉检验 demo：RB 60m 最近 120 根 K 线 + 量化函数标注叠加
"""生成 RB（螺纹钢）60m 最近数据的完整量化标注叠加图，验证：
  ① 摆动点检测是否跟肉眼一致
  ② 趋势判定是否正确
  ③ 区间边界是否贴近真实支撑/压力
  ④ 缺口检测是否准确
输出：assets/RS021/visual_check_RB60m.png
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quantlib.visual import plot_with_overlays
from quantlib.structure import (
    find_swing_points,
    detect_trend_zigzag,
    detect_trend_ema_slope,
    classify_trend,
    find_range_boundary,
    kline_density_zone,
)
from quantlib.gap import detect_gaps
from quantlib.pullback import retracement_fraction, near_ma

DATA60 = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = ROOT.parent / "assets" / "RS021"
SYMS = {"RB": "SHFE", "CU": "SHFE", "M": "DCE", "TA": "CZCE", "MA": "CZCE"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for sym, exch in list(SYMS.items())[:2]:  # 先做 RB 和 CU
        bars = []
        with (DATA60 / exch / sym / f"{sym}.csv").open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["datetime"][:4] < "2025":
                    continue
                bars.append([r["datetime"],
                             float(r["open"]), float(r["high"]),
                             float(r["low"]), float(r["close"]),
                             float(r["volume"]), float(r.get("position") or 0)])
        bars = bars[-120:]  # 最近 120 根 60m K 线
        if len(bars) < 60:
            continue

        overlays = {}

        # ① 摆动点
        swings = find_swing_points(bars, left=3, right=3)
        overlays["swing_H"] = [(s["index"], s["price"]) for s in swings if s["type"] == "H"]
        overlays["swing_L"] = [(s["index"], s["price"]) for s in swings if s["type"] == "L"]

        # ② 趋势判定（zigzag 和 ema_slope 双方案）
        tz = classify_trend(bars, method="zigzag")
        te = classify_trend(bars, method="ema_slope")
        overlays["trend_zones"] = [(0, len(bars), f"{tz}|{te}")]

        # ③ 区间边界
        support, resistance = find_range_boundary(bars, lookback=60, method="swing")
        if support and resistance:
            overlays["support_lines"] = [(0, len(bars) - 1, support)]
            overlays["resistance_lines"] = [(0, len(bars) - 1, resistance)]

        # ④ 缺口
        gaps = detect_gaps(bars, method="simple")
        overlays["gap_zones"] = [
            (g["index"], min(g["index"] + 5, len(bars) - 1),
             g["gap_top"], g["gap_bottom"]) for g in gaps
        ]

        title = f"{sym} 60m quantlib标注 | zigzag:{tz} ema_slope:{te} | swings:{len(swings)} gaps:{len(gaps)}"
        out_path = str(OUT / f"visual_check_{sym}60m.png")
        plot_with_overlays(bars, overlays, title, out_path)
        print(f"-> {out_path}")


import csv

if __name__ == "__main__":
    main()
