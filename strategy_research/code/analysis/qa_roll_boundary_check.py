# RESEARCH ONLY - 未获用户批准不得正式运行
"""QA 审计#1 裁决：tradereplay 60m 主连是否比率拼接（复权）。
方法：扫描 symbol 列换月边界，比较边界前后两根收盘的跳变幅度。
  比率拼接 → 边界收益率与普通相邻根同量级（无系统性大跳空）；
  未复权直拼 → 边界处出现大幅价差跳变（新旧合约价差一次到位）。
输出：各品种全部边界的边界收益分布 + 与普通根收益波动的对比。
"""
import csv
from pathlib import Path

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
SYMS = {"RB": "SHFE", "CU": "SHFE", "MA": "CZCE", "M": "DCE", "TA": "CZCE"}

for sym, exch in SYMS.items():
    rows = []
    with (DATA / exch / sym / f"{sym}.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((r["datetime"], r["symbol"], float(r["close"])))
    # 找换月边界：symbol 变化的前一根/后一根
    bounds = []
    rets = []          # 全部相邻根收益（普通根）
    b_rets = []        # 边界根收益
    for i in range(1, len(rows)):
        r = rows[i][2] / rows[i - 1][2] - 1
        rets.append(r)
        if rows[i][1] != rows[i - 1][1]:
            bounds.append((rows[i][0], rows[i - 1][1], rows[i][1], r))
            b_rets.append(r)
    base = [abs(x) for x in rets if abs(x) < 0.2]
    base_mean = sum(base) / len(base)
    big = [b for b in b_rets if abs(b) > 0.03]
    print(f"{sym}: bars={len(rows)} 换月边界={len(bounds)}")
    print(f"  边界收益: min={min(b_rets):+.3%} max={max(b_rets):+.3%} "
          f"abs均值={sum(abs(x) for x in b_rets)/len(b_rets):.3%}")
    print(f"  普通根 |收益| 均值={base_mean:.3%}（对照）；边界>3%跳变数={len(big)}")
    for dt, old, new, r in bounds[:4]:
        print(f"    {dt} {old}->{new}: {r:+.3%}")
    print()
