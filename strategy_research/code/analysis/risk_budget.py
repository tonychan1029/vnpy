# RESEARCH ONLY - 未获用户批准不得正式运行
"""DOUBLE_BOTTOM 风险预算规则回测（MTG004 §9 决议的具体化）。

规则（滞后降杠杆）：
  滚动累计净R（全部已触发 DB 逐笔，按时间序）：
    run_sum > 0 → 仓位 1.0
    run_sum ≤ −0.5 → 仓位 0.5（衰减档）
    之间 → 维持上一仓位
对照：恒定 1.0 仓位。
指标：总净R、最大回撤（R）、负年暴露（负年计入 R 占比）、OOS 段对比。
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

SRC = Path(r"D:\AIprj\vnpy\vnpy_patiming\output\baseline\signals_detail.csv")
OUT = Path(__file__).resolve().parents[2] / "assets" / "MTG004"
OOS_START = datetime(2022, 1, 1)
NEG_YEARS = {2015, 2018, 2023, 2024}


def max_dd(equity_curve):
    peak = 0.0
    dd = 0.0
    for x in equity_curve:
        peak = max(peak, x)
        dd = min(dd, x - peak)
    return dd


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    trades = []
    with SRC.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["signal_id"] != "DOUBLE_BOTTOM":
                continue
            net = r.get("p1_net_r")
            if net in ("", None):
                continue
            try:
                dt = datetime.strptime(r["bar_time"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            trades.append((dt, float(net)))
    trades.sort(key=lambda x: x[0])
    # 恒定仓位
    fixed_curve = []
    run = 0.0
    for _, net in trades:
        run += net
        fixed_curve.append(run)
    # 风险预算（滚动 20 笔窗口 run_sum——全期累计会被早期利润垫永久锁死触发器）
    rb_curve = []
    run = 0.0
    size = 1.0
    hist = []                              # 最近 20 笔净R
    for _, net in trades:
        hist.append(net)
        if len(hist) > 20:
            hist.pop(0)
        roll = sum(hist)
        if roll <= -0.5:
            size = 0.5
        elif roll > 0:
            size = 1.0
        run += net * size
        rb_curve.append(run)
    lines = ["# DOUBLE_BOTTOM 风险预算规则回测（滞后降杠杆：run_sum≤−0.5R 减半，>0 恢复）",
             "", f"- 样本：{len(trades)} 笔已触发 DB 逐笔（p1，2015–2026）", "",
             "| 方案 | 总净R | 最大回撤(R) | 末值 |", "|---|---|---|---|"]
    lines.append(f"| 恒定 1.0 | {fixed_curve[-1]:+.2f} | "
                 f"{max_dd(fixed_curve):.2f} | {fixed_curve[-1]:+.2f} |")
    lines.append(f"| 风险预算 | {rb_curve[-1]:+.2f} | "
                 f"{max_dd(rb_curve):.2f} | {rb_curve[-1]:+.2f} |")
    # 分段
    lines += ["", "## 分段（OOS 2022 起）", "",
              "| 方案 | 段内净R | 段内最大回撤(R) |", "|---|---|---|"]
    for name, curve in (("恒定", fixed_curve), ("风险预算", rb_curve)):
        seg = [curve[i] for i, (dt, _) in enumerate(trades)
               if dt >= OOS_START]
        pre = [curve[i] for i, (dt, _) in enumerate(trades)
               if dt < OOS_START]
        seg_d = seg[-1] - (pre[-1] if pre else 0)
        lines.append(f"| {name} | {seg_d:+.2f} | {max_dd(seg) if seg else 0:.2f} |")
    # 负年暴露（风险预算=滚动 20 笔窗口）
    lines += ["", "## 负年计入 R 对比（恒定 vs 风险预算）", "",
              "| 年 | 恒定 | 风险预算 |", "|---|---|---|"]
    run = 0.0
    size = 1.0
    hist = []
    year_fixed = defaultdict(float)
    year_rb = defaultdict(float)
    for dt, net in trades:
        hist.append(net)
        if len(hist) > 20:
            hist.pop(0)
        roll = sum(hist)
        if roll <= -0.5:
            size = 0.5
        elif roll > 0:
            size = 1.0
        year_fixed[dt.year] += net
        year_rb[dt.year] += net * size
        run += net * size
    for y in sorted(year_fixed):
        mark = " ❌" if y in NEG_YEARS else ""
        lines.append(f"| {y}{mark} | {year_fixed[y]:+.2f} | "
                     f"{year_rb[y]:+.2f} |")
    (OUT / "db_risk_budget.md").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    print("->", OUT / "db_risk_budget.md")


if __name__ == "__main__":
    from collections import defaultdict
    main()
