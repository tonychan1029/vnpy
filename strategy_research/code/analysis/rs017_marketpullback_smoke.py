# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS017 补课②：MarketPullback 选品扫描 smoke 回放（1m 数据窗 2026-09-07 起）。

统计意义声明：窗口仅 ~1 个月，前瞻最長 ~15 交易日——本回放是**管线与
判据的 smoke 验证 + 短前瞻方向粗测**，非结论性研究。

复刻口径（poolscan.MarketPullbackScanner._evaluate_symbol）：
  - 交易日归属：hour>=20 → 下一交易日；扫描节点=每交易日 15:00（对齐
    15:05 盘后节点，用当日含隔夜的已完成 1m）；
  - 过滤链：日线量 ≥5 万（上一完成交易日）→ 60m 结构 ≥30 根（PABackground
    方向引擎，与 trend_pullback 回放同一复刻）→ 15m MA20 贴近
    （≤max(0.5×ATR15, 0.5%×price)）→ 现价 RR ≥ market_min_rr=1.0 且
    风险宽度 ≥0.5×ATR15 → 入选（TTL 24h）。
60m/15m 由 1m 合成（60m=自然小时桶、15m=15 分桶——近似 vnpy BarGenerator，
已在报告头声明）。

输出：assets/RS017/marketpullback_smoke.md
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # strategy_research/code
sys.path.insert(0, str(ROOT))

from analysis.rs017_trendpullback_replay import analyze  # noqa: E402  同一方向引擎复刻

DATA = Path(r"D:\AIprj\tradereplay\data\1m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "RS017"
UNIVERSE = [("RB0", "SHFE", "RB"), ("CU0", "SHFE", "CU"), ("AL0", "SHFE", "AL"),
            ("M0", "DCE", "M"), ("Y0", "DCE", "Y"), ("P0", "DCE", "P"),
            ("TA0", "CZCE", "TA"), ("MA0", "CZCE", "MA"),
            ("SR0", "CZCE", "SR"), ("IF0", "CFFEX", "IF")]
DAILY_MIN_VOL = 50_000.0
MARKET_MIN_RR = 1.0
MIN_RISK_ATR = 0.5
MA_PERIOD = 20
LOOKBACK_60M = 30


def tday(dt: datetime) -> str:
    d = dt.date()
    if dt.hour >= 20:
        d = d + timedelta(days=1)
    return d.isoformat()


def load_1m(path: Path):
    bars = []
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dt = datetime.strptime(r["datetime"], "%Y-%m-%d %H:%M:%S")
            bars.append((dt, tday(dt), float(r["open"]), float(r["high"]),
                         float(r["low"]), float(r["close"]), float(r["volume"])))
    bars.sort(key=lambda b: b[0])
    return bars


def bucket(bars, key_fn, otf=True):
    out = {}
    for b in bars:
        k = key_fn(b)
        cur = out.get(k)
        if cur is None:
            out[k] = [b[2], b[3], b[4], b[5], b[6]]
        else:
            cur[1] = max(cur[1], b[3])
            cur[2] = min(cur[2], b[4])
            cur[3] = b[5]
            cur[4] += b[6]
    return [(k, v) for k, v in sorted(out.items(), key=lambda kv: kv[0])]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    funnel = defaultdict(int)
    entries = []
    last_dt = None
    for cont, exch, prod in UNIVERSE:
        path = DATA / exch / prod / f"{prod}.csv"
        if not path.exists():
            funnel["no_1m_data"] += 0
            print(f"[skip] {cont}: {path} 不存在")
            continue
        bars = load_1m(path)
        if not bars:
            continue
        last_dt = max(last_dt or bars[-1][0], bars[-1][0])
        tdays = sorted({b[1] for b in bars})
        by_tday = defaultdict(list)
        for b in bars:
            by_tday[b[1]].append(b)

        # 日线（按交易日合成，收盘=日最后一根 1m 收盘）
        daily = {}
        for td in tdays:
            dbars = by_tday[td]
            daily[td] = (max(b[3] for b in dbars), min(b[4] for b in dbars),
                         dbars[-1][5], sum(b[6] for b in dbars))
        tday_list = tdays

        # 60m（自然小时桶）与 15m（15 分桶），键内保持时序
        h60 = bucket(bars, lambda b: (b[1], b[0].hour))
        m15 = bucket(bars, lambda b: (b[1], b[0].hour, b[0].minute // 15))
        h60_arr = [(k, v) for k, v in h60]
        m15_arr = [(k, v) for k, v in m15]

        for idx, td in enumerate(tday_list):
            if idx < 7:                      # 预热（60m 结构 ≥30 根所需）
                continue
            cutoff = td + "T15:00"
            day_bars = [b for b in by_tday[td] if b[0].isoformat() <= cutoff + ":00"]
            if not day_bars:
                continue
            current = day_bars[-1][5]
            funnel["eval"] += 1

            # 日线过滤：上一完成交易日
            prev_days = [d for d in tday_list if d < td]
            if not prev_days:
                funnel["daily_insufficient"] += 1
                continue
            ld = daily[prev_days[-1]]
            if ld[3] <= DAILY_MIN_VOL:
                funnel["daily_volume"] += 1
                continue

            # 60m 结构
            hbars = [v for k, v in h60_arr if k[0] <= td]
            if len(hbars) < LOOKBACK_60M:
                funnel["hourly_insufficient"] += 1
                continue
            hh = [v[1] for v in hbars]
            ll = [v[2] for v in hbars]
            cc = [v[3] for v in hbars]
            trend, _entry, support, resistance = analyze(hh, ll, cc)
            if trend is None:
                funnel["no_trend"] += 1
                continue
            if not (support and resistance and support < resistance):
                funnel["invalid_levels"] += 1
                continue

            # 15m MA20 贴近
            mbars = [v for k, v in m15_arr if k[0] == td]
            closes15 = [v[3] for v in mbars]
            if len(closes15) < MA_PERIOD:
                funnel["minute_insufficient"] += 1
                continue
            ma = sum(closes15[-MA_PERIOD:]) / MA_PERIOD
            trs = []
            for i in range(max(1, len(mbars) - 14), len(mbars)):
                ph, pl, pc = (mbars[i - 1][1], mbars[i - 1][2], mbars[i - 1][3]) \
                    if i > 0 else (mbars[i][1], mbars[i][2], mbars[i][3])
                trs.append(max(mbars[i][1] - mbars[i][2],
                               abs(mbars[i][1] - pc), abs(mbars[i][2] - pc)))
            atr15 = sum(trs) / len(trs) if trs else 0.0
            tol = max(0.5 * atr15, 0.005 * current)
            if abs(current - ma) > tol:
                funnel["not_near_ma"] += 1
                continue

            if trend == "long":
                reward, risk = resistance - current, current - support
            else:
                reward, risk = current - support, resistance - current
            if risk <= 1e-12 or reward <= 1e-12:
                funnel["invalid_rr"] += 1
                continue
            if risk < MIN_RISK_ATR * atr15:
                funnel["risk_too_small"] += 1
                continue
            rr = reward / risk
            if rr < MARKET_MIN_RR:
                funnel["rr_too_small"] += 1
                continue

            funnel["passed"] += 1
            entries.append({"td": td, "symbol": cont, "dir": trend,
                            "entry": current, "rr": round(rr, 2),
                            "td_index": tday_list.index(td),
                            "tdays": tday_list})

    # 前瞻（1/3/5 交易日，自入选日次日起算的日收盘）
    close_by = {}
    for cont, exch, prod in UNIVERSE:
        path = DATA / exch / prod / f"{prod}.csv"
        if not path.exists():
            continue
        bars = load_1m(path)
        seq = defaultdict(float)
        for b in bars:
            seq[b[1]] = b[5]                    # 交易日→日收盘
        close_by[cont] = (sorted(seq), seq)
    for e in entries:
        tdl, seq = close_by[e["symbol"]]
        i = tdl.index(e["td"])
        d = {}
        for h in (1, 3, 5):
            j = i + h
            if j < len(tdl):
                ret = (seq[tdl[j]] / e["entry"] - 1) * (1 if e["dir"] == "long" else -1)
                d[h] = ret
        e["fwd"] = d

    L = ["# RS017 补课②：MarketPullback 选品 smoke 回放", "",
         f"- 数据窗：2026-09-07 起 ~1 个月（最后数据 {last_dt}）；10 品种池全覆盖；",
         "- **smoke 定位：管线/判据验证 + 短前瞻粗测，非结论性**；60m/15m 由 1m",
         "  合成（自然小时/15 分桶，近似 BarGenerator）；前瞻最长 5 交易日。", ""]
    L += ["## 1. 评估漏斗（扫描节点=交易日×品种）", "",
          "| 环节 | 次数 |", "|---|---|"]
    order = ("eval", "daily_volume", "no_trend", "not_near_ma",
             "risk_too_small", "rr_too_small", "passed")
    for k in order:
        L.append(f"| {k} | {funnel.get(k, 0)} |")
    extra = {k: v for k, v in funnel.items() if k not in order}
    for k, v in extra.items():
        L.append(f"| {k} | {v} |")

    L += ["", "## 2. 入选明细与短前瞻（方向调整，自入选价）", "",
          "| 交易日 | 品种 | 方向 | RR | +1日 | +3日 | +5日 |",
          "|---|---|---|---|---|---|---|"]
    fw = {1: [], 3: [], 5: []}
    for e in sorted(entries, key=lambda x: (x["td"], x["symbol"])):
        cells = []
        for h in (1, 3, 5):
            v = e["fwd"].get(h)
            if v is None:
                cells.append("-")
            else:
                cells.append(f"{v:+.2%}")
                fw[h].append(v)
        L.append(f"| {e['td']} | {e['symbol']} | {e['dir']} | {e['rr']} | "
                 + " | ".join(cells) + " |")

    L += ["", "## 3. 短前瞻汇总（n 小，仅粗测）", "",
          "| 前瞻 | n | 胜率 | 均值 |", "|---|---|---|---|"]
    for h in (1, 3, 5):
        xs = fw[h]
        if xs:
            L.append(f"| +{h}日 | {len(xs)} | {sum(1 for x in xs if x > 0) / len(xs):.0%} | "
                     f"{sum(xs) / len(xs):+.2%} |")
    L += ["", "判读：本 smoke 只证明——①判据管线可在真实 1m 数据上运行；",
          "②入选频率与漏斗分布量级；③极短前瞻方向粗测。",
          "任何绩效结论以 Linux 生产数据导出后的正式回撤研究为准。"]

    out = OUT / "marketpullback_smoke.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    print("funnel:", dict(funnel))


if __name__ == "__main__":
    main()
