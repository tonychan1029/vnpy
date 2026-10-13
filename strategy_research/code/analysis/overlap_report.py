# RESEARCH ONLY - 未获用户批准不得正式运行
"""三族信号重叠度首报（MTG004 议程第 5 项）。

族映射（基线 9 detector → 三策略族，与 §5 判读草案一致）：
  突破族(S-001): BREAKOUT_KEY_LEVEL / H2L2_TREND / FAKE_BREAKOUT_REVERSE
  回调族(S-002): STRUCTURE_PULLBACK / EMA20_PULLBACK
  反转族(S-003): DOUBLE_BOTTOM / DOUBLE_TOP / WEDGE_THREE_PUSH / RANGE_EDGE_REVERSAL
重叠定义：同品种、方向相同、bar_time 相差 <=5 根(60m) 视为同窗。
输出：两两同窗对数与占比（以较少一方为分母），及三族同窗三元组计数。
附：方向一致性检查（同窗反方向=对冲噪音源）。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"

FAMILY = {
    "BREAKOUT_KEY_LEVEL": "突破", "H2L2_TREND": "突破",
    "FAKE_BREAKOUT_REVERSE": "突破",
    "STRUCTURE_PULLBACK": "回调", "EMA20_PULLBACK": "回调",
    "DOUBLE_BOTTOM": "反转", "DOUBLE_TOP": "反转",
    "WEDGE_THREE_PUSH": "反转", "RANGE_EDGE_REVERSAL": "反转",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sigs = []                      # (sym, fam, dir, dt)
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            fam = FAMILY.get(r["signal_id"])
            if fam is None:
                continue
            try:
                dt = datetime.strptime(r["bar_time"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            sigs.append((r["symbol"], fam, r["direction"], dt))
    by_key = defaultdict(list)     # (sym, fam) -> [(dt, dir)]
    for sym, fam, d, dt in sigs:
        by_key[(sym, fam)].append((dt, d))
    pairs = [("突破", "回调"), ("突破", "反转"), ("回调", "反转")]
    lines = ["# 三族信号重叠度首报（基线轮次 0，5.2 万草稿）", "",
             "同窗定义：同品种同方向、bar_time 相差 ≤5 根（60m）。", ""]
    for fa, fb in pairs:
        same = 0
        opp = 0
        na = nb = 0
        for (sym, fam), lst in by_key.items():
            if fam != fa:
                continue
            other = by_key.get((sym, fb), [])
            if not other:
                continue
            na += len(lst)
            nb += 0
            ots = [dt for dt, _ in other]
            odirs = [d for _, d in other]
            for dt, d in lst:
                hit = any(abs((ot - dt).total_seconds()) <= 5 * 3600
                          for ot in ots)
                if hit:
                    od = next(od for ot, od in zip(ots, odirs)
                              if abs((ot - dt).total_seconds()) <= 5 * 3600)
                    if od == d:
                        same += 1
                    else:
                        opp += 1
        lines.append(f"- **{fa}×{fb}**：{fa} 侧 n={na}，同窗同向 {same}、"
                     f"同窗反向 {opp}（同窗率 "
                     f"{(same + opp) / na * 100:.1f}%）" if na else
                     f"- **{fa}×{fb}**：无样本")
    # 三族同窗
    tri = 0
    for (sym, fam), lst in by_key.items():
        if fam != "突破":
            continue
        oth1 = by_key.get((sym, "回调"), [])
        oth2 = by_key.get((sym, "反转"), [])
        for dt, _ in lst:
            h1 = any(abs((ot - dt).total_seconds()) <= 5 * 3600
                     for ot, _ in oth1)
            h2 = any(abs((ot - dt).total_seconds()) <= 5 * 3600
                     for ot, _ in oth2)
            if h1 and h2:
                tri += 1
    lines.append(f"- **三族同窗（突破∩回调∩反转，同品种±5根）**：{tri}")
    lines += ["", "注：占比以族内信号数为分母的粗口径（未去重多对多匹配）；"
              "同窗反向对是编排去重/对冲的首要清理对象。"]
    (OUT / "overlap_report.md").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    print("->", OUT / "overlap_report.md")


if __name__ == "__main__":
    main()
