# RESEARCH ONLY - 未获用户批准不得正式运行
"""CAND-005 基准对照预跑：经典日内策略（日级粗口径）vs 零基准。

口径说明（诚实边界）：
- 60m 聚合为日级 OHLC（主连连续序列，拼接缺口未剔除——与未来 PA 回测同源）
- 信号在 T 日收盘确认，收益取 T→T+1 收盘（非日内进出，粗口径代理）
- 成本：双边万3（0.0006）从每笔扣除
- 这是"信号是否有边际"的诊断，不是正式回测；正式对照等 HO001 管道
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from methods.benchmark_intraday import (  # noqa: E402
    DayOHLC, dual_thrust_signal, fiali_signal, r_breaker_signal,
)

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = ROOT.parent / "assets" / "BENCH"
COST = 0.0006

SYMBOLS = {"RB": DATA / "SHFE" / "RB" / "RB.csv",
           "CU": DATA / "SHFE" / "CU" / "CU.csv",
           "AG": DATA / "SHFE" / "AG" / "AG.csv",
           "M": DATA / "DCE" / "M" / "M.csv",
           "MA": DATA / "CZCE" / "MA" / "MA.csv",
           "TA": DATA / "CZCE" / "TA" / "TA.csv"}

STRATS = {"dual_thrust": dual_thrust_signal,
          "fiali": fiali_signal,
          "r_breaker": r_breaker_signal}


def daily_bars(path: Path):
    days = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            days[r["datetime"][:10]].append(
                (float(r["open"]), float(r["high"]),
                 float(r["low"]), float(r["close"])))
    out = []
    for d in sorted(days):
        bars = days[d]
        if len(bars) < 4:            # 半日/异常日剔除
            continue
        out.append((d, DayOHLC(bars[0][0], max(b[1] for b in bars),
                               min(b[2] for b in bars), bars[-1][3])))
    return out


def intraday_sim(path: Path):
    """原生模式仿真：日内 60m 逐根扫描，突破当根收盘入场，当日收盘平仓。

    fiali / dual_thrust 两本独立账；r_breaker 日内逻辑复杂，不在此批。
    触发判定用当根高低点（触及即视为突破），入场价取当根收盘（研究代理）。
    """
    days_map = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            days_map[r["datetime"][:10]].append(
                (float(r["open"]), float(r["high"]),
                 float(r["low"]), float(r["close"])))
    dates = sorted(days_map)
    out = defaultdict(lambda: [0, 0, 0.0])
    for t in range(1, len(dates)):
        pb = days_map[dates[t - 1]]
        if len(pb) < 4:
            continue
        prev = DayOHLC(pb[0][0], max(b[1] for b in pb),
                       min(b[2] for b in pb), pb[-1][3])
        bars = days_map[dates[t]]
        if len(bars) < 4:
            continue
        rng = max(prev.high - prev.low, prev.high - prev.close,
                  prev.close - prev.low)
        up_d = bars[0][0] + 0.5 * rng
        dn_d = bars[0][0] - 0.5 * rng
        f_state = d_state = None                  # (sign, entry_px)
        for o, h, l, c in bars:
            if f_state is None:
                if h > prev.high:
                    f_state = (1, c)
                elif l < prev.low:
                    f_state = (-1, c)
            if d_state is None:
                if h > up_d:
                    d_state = (1, c)
                elif l < dn_d:
                    d_state = (-1, c)
        day_close = bars[-1][3]
        for name, st in (("fiali_intraday", f_state),
                         ("dt_intraday", d_state)):
            if st is None:
                continue
            ret = st[0] * (day_close / st[1] - 1) - COST
            a = out[name]
            a[0] += 1
            a[1] += ret > 0
            a[2] += ret
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# CAND-005 基准对照预跑（日级粗口径，T→T+1 收盘，成本双边万3）", "",
             "| 策略 | 品种 | n | 胜率 | 平均净收益 | 累计 |", "|---|---|---|---|---|---|"]
    agg = defaultdict(lambda: [0, 0, 0.0])
    for sym, path in SYMBOLS.items():
        days = daily_bars(path)
        for name, fn in STRATS.items():
            for t in range(1, len(days) - 1):
                sig = fn(days[t][1], days[t - 1][1], days[t][1].open) \
                    if name == "dual_thrust" else fn(days[t][1], days[t - 1][1])
                if sig == 0:
                    continue
                ret = sig * (days[t + 1][1].close / days[t][1].close - 1) - COST
                a = agg[(name, sym)]
                a[0] += 1
                a[1] += ret > 0
                a[2] += ret
    for (name, sym), (n, w, s) in sorted(agg.items()):
        lines.append(f"| {name} | {sym} | {n} | {w / n * 100:.1f}% | "
                     f"{s / n * 100:.3f}% | {s * 100:.1f}% |")
    # 汇总行
    lines.append("")
    lines.append("| 策略 | 合计 n | 合计胜率 | 合计平均 |")
    lines.append("|---|---|---|---|")
    tot = defaultdict(lambda: [0, 0, 0.0])
    for (name, sym), (n, w, s) in agg.items():
        t = tot[name]
        t[0] += n
        t[1] += w
        t[2] += s
    for name, (n, w, s) in sorted(tot.items()):
        lines.append(f"| {name} | {n} | {w / n * 100:.1f}% | {s / n * 100:.3f}% |")
    # 日内原生模式仿真（fiali / dual_thrust，r_breaker 不在此批）
    lines += ["", "## 日内原生模式仿真（60m 逐根触发，当日收盘平仓，成本双边万3）", "",
              "| 策略 | 品种 | n | 胜率 | 平均净收益 |", "|---|---|---|---|---|"]
    tot2 = defaultdict(lambda: [0, 0, 0.0])
    for sym, path in SYMBOLS.items():
        res = intraday_sim(path)
        for name, (n, w, s) in sorted(res.items()):
            lines.append(f"| {name} | {sym} | {n} | {w / n * 100:.1f}% | "
                         f"{s / n * 100:.3f}% |")
            t = tot2[name]
            t[0] += n
            t[1] += w
            t[2] += s
    lines.append("")
    lines.append("| 策略 | 合计 n | 合计胜率 | 合计平均 |")
    lines.append("|---|---|---|---|")
    for name, (n, w, s) in sorted(tot2.items()):
        lines.append(f"| {name} | {n} | {w / n * 100:.1f}% | {s / n * 100:.3f}% |")
    # ORB（当日成立区间族，CAND-008 口径：首根 60m 高低=OR，
    # 首根收盘出界者入场，日末平仓；"收盘定方向"规则）
    lines += ["", "## ORB 开盘区间（60m 代理：首根=OR，收盘出界入场，日末平仓，双边万3）",
              "", "| 品种 | n | 胜率 | 平均净收益 |", "|---|---|---|---|"]
    orb_tot = [0, 0, 0.0]
    for sym, path in SYMBOLS.items():
        days_map2 = defaultdict(list)
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                days_map2[r["datetime"][:10]].append(
                    (float(r["open"]), float(r["high"]),
                     float(r["low"]), float(r["close"])))
        n = w = 0
        s = 0.0
        for d, bars in days_map2.items():
            if len(bars) < 3:
                continue
            or_hi, or_lo = bars[0][1], bars[0][2]
            entry = None
            for o_, h_, l_, c_ in bars[1:]:
                if entry is None:
                    if c_ > or_hi:
                        entry = (1, c_)
                        break
                    if c_ < or_lo:
                        entry = (-1, c_)
                        break
            if entry is None:
                continue
            ret = entry[0] * (bars[-1][3] / entry[1] - 1) - COST
            n += 1
            w += ret > 0
            s += ret
        if n:
            lines.append(f"| {sym} | {n} | {w / n * 100:.1f}% | {s / n * 100:.3f}% |")
            orb_tot[0] += n
            orb_tot[1] += w
            orb_tot[2] += s
    if orb_tot[0]:
        lines.append(f"| **合计** | {orb_tot[0]} | {orb_tot[1] / orb_tot[0] * 100:.1f}% | "
                     f"{orb_tot[2] / orb_tot[0] * 100:.3f}% |")
    (OUT / "benchmark_preliminary.md").write_text("\n".join(lines) + "\n",
                                                  encoding="utf-8")
    print("->", OUT / "benchmark_preliminary.md")


if __name__ == "__main__":
    main()
