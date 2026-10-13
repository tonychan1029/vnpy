# RESEARCH ONLY - 未获用户批准不得正式运行
"""P2 tick 规格分层实验（验证队列）：基线信号 × RS011 附录 A 分层。

分层（RS011 附录 A，tick/价格比）：
  小 tick 组：MA(0.041%) TA(0.040%) RB(0.030%)
  大 tick 组：M(0.017%) AG(0.013%) CU(0.013%)
RS011 先验：小 tick 组突破/回调类信号更弱（信息被 HFT 吃掉 + 衰亡区）。
输出：三族 × 两层的 n/胜率/平均净R(p1)；单信号明细；与先验对照。
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
OUT = Path(__file__).resolve().parents[2] / "assets" / "RS011"

STRATUM = {"MA": "small", "TA": "small", "RB": "small",
           "M": "large", "AG": "large", "CU": "large"}
FAMILY = {
    "BREAKOUT_KEY_LEVEL": "突破", "H2L2_TREND": "突破",
    "FAKE_BREAKOUT_REVERSE": "突破",
    "STRUCTURE_PULLBACK": "回调", "EMA20_PULLBACK": "回调",
    "DOUBLE_BOTTOM": "反转", "DOUBLE_TOP": "反转",
    "WEDGE_THREE_PUSH": "反转", "RANGE_EDGE_REVERSAL": "反转",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cell = defaultdict(list)                        # (family,stratum) -> [net]
    sym_cell = defaultdict(list)                    # (signal,sym) -> [net]
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sig = r["signal_id"]
            if sig not in FAMILY:
                continue
            net = r.get("p1_net_r")
            if net in ("", None):
                continue
            net = float(net)
            st = STRATUM.get(r["symbol"])
            if st is None:
                continue
            fam = FAMILY[sig]
            cell[(fam, st)].append(net)
            sym_cell[(sig, r["symbol"])].append(net)
    lines = ["# P2 tick 规格分层实验（基线 p1 净R × RS011 附录 A 分层）", "",
             "小 tick：MA/TA/RB；大 tick：M/AG/CU。RS011 先验：小 tick 组更弱。", ""]
    lines.append("## 三族 × 两层")
    lines.append("| 族 | 层 | n | 胜率 | 平均净R | 差(小−大) |")
    lines.append("|---|---|---|---|---|---|")
    for fam in ("突破", "回调", "反转"):
        vals = {}
        for st in ("small", "large"):
            xs = cell[(fam, st)]
            if not xs:
                vals[st] = None
                continue
            win = sum(1 for x in xs if x > 0) / len(xs) * 100
            vals[st] = sum(xs) / len(xs)
            lines.append(f"| {fam} | {st} | {len(xs)} | {win:.1f}% | "
                         f"{vals[st]:+.3f} |" if st == "small" else
                         f"| {fam} | {st} | {len(xs)} | {win:.1f}% | "
                         f"{vals[st]:+.3f} |")
        if vals.get("small") is not None and vals.get("large") is not None:
            d = vals["small"] - vals["large"]
            verdict = "支持先验（小更弱）" if d < 0 else "不支持先验"
            lines.append(f"| **{fam} 差** | | | | **{d:+.3f}** | {verdict} |")
    lines += ["", "## 单信号 × 品种（avg p1_net_r）", ""]
    sigs = sorted({s for s, _ in sym_cell})
    lines.append("| 信号 | " + " | ".join(
        f"{s}({'小' if STRATUM[s]=='small' else '大'})" for s in
        ("RB", "MA", "TA", "M", "AG", "CU")) + " |")
    lines.append("|---|" + "---|" * 6)
    for sig in sigs:
        row = [sig]
        for s in ("RB", "MA", "TA", "M", "AG", "CU"):
            xs = sym_cell.get((sig, s))
            row.append(f"{sum(xs) / len(xs):+.3f}({len(xs)})" if xs else "-")
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "判读：差值为负=小 tick 组更弱（支持 RS011）；"
              "正值=小 tick 组反而强（RS011 衰亡区先验在该池不成立）。"
              "样本不平衡（n 不同）为一级 caution。"]
    (OUT / "p2_tick_strat.md").write_text("\n".join(lines) + "\n",
                                          encoding="utf-8")
    print("->", OUT / "p2_tick_strat.md")


if __name__ == "__main__":
    main()
