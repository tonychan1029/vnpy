# RESEARCH ONLY - 未获用户批准不得正式运行
"""RS017 补课②：TrendPullback 选品扫描器离线回放（选品质量建档）。

忠实复刻（poolscan.TrendPullbackScanner.evaluate_product + pa.background）：
  - 日线窗 = 滚动 120 个交易日（lookback_days=120，逐日重算，与生产
    "每收盘节点全窗重扫"一致；摆动点右 5 根确认由滑动窗自然实现）；
  - 方向引擎：TradingView pivot(5,5) 严格确认 → CCI(20)±100 相位聚类
    （每相位同向只留极值）→ 同类合并取极值/同索引按收盘方向取舍 →
    ≥2 高点且 ≥2 低点 → BULL: close>EMA21 且 EMA21 上斜(3根) 且 低点抬高；
    BEAR 镜像；支撑/压力 = l_new / h_new；
  - 入选：direction 定后 entry=EMA20(日线，talib 口径 SMA 播种)，
    RR=(压−entry)/(entry−撑)（long）≥ min_rr=1.5。

度量（选品质量，非可交易回测——无执行/止损建模）：
  - 每个入选事件（逐日，池每日整体替换口径）记录后 20/60 个交易日方向
    调整收益（自入选日收盘）；另记 EMA20 限价 5 日内触碰率（限价参考口径）；
  - 连续同向入选按"episode 首日"去重复列一遍（防持续趋势重复计数）；
  - 累计曲线（事件序 20 日收益累加，重叠口径如实标注）的最大回撤。
子集声明：生产池 10 主连中本地 60m 历史仅覆盖 RB/CU/M/TA/MA（5/10；
AG 本地有但不在生产池；AL/Y/P/SR/IF 缺数据），结论仅适用该子集。

输出：assets/RS017/trendpullback_replay.md
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

DATA = Path(r"D:\AIprj\tradereplay\data\60m")
OUT = Path(__file__).resolve().parents[2] / "assets" / "RS017"
SYMS = {"RB": "SHFE", "CU": "SHFE", "M": "DCE", "TA": "CZCE", "MA": "CZCE"}
LOOKBACK = 120
MIN_RR = 1.5
PIVOT_L = PIVOT_R = 5
EMA_PERIOD = 21
EMA_SLOPE_BARS = 3
CCI_PERIOD = 20
CCI_TH = 100.0
SPLIT = "2022-01-01"


def load_daily(sym: str, exch: str):
    """60m → 工程同款后复权（exit_ladder_eval._detect_and_splice 口径）→ 日线合成。
    夜盘 ≥20:30 归属下一交易日；只取 2015-01-01 起（生产口径）。"""
    from datetime import date, timedelta
    rows = []
    bad_bars = 0
    with (DATA / exch / sym / f"{sym}.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["datetime"][:4] < "2015":
                continue
            d, t = r["datetime"].split(" ")
            hh = int(t[:2])
            day = d
            if hh >= 20:
                y, m, dd = map(int, d.split("-"))
                day = (date(y, m, dd) + timedelta(days=1)).isoformat()
            o, h, l, c = (float(r["open"]), float(r["high"]),
                          float(r["low"]), float(r["close"]))
            if min(o, h, l, c) <= 0 or h / max(l, 1e-9) > 50:
                bad_bars += 1                     # 坏点：非正价或离谱波幅
                continue
            rows.append((day, o, h, l, c,
                         float(r["volume"]), float(r["position"] or 0)))
    # ── 后复权（工程 _detect_and_splice 同款）─────────────────
    n = len(rows)
    if n >= 2:
        trs = [rows[0][3] - rows[0][4]]
        for i in range(1, n):
            trs.append(max(rows[i][3] - rows[i][4],
                           abs(rows[i][3] - rows[i - 1][5]),
                           abs(rows[i][4] - rows[i - 1][5])))
        atr = []
        for i in range(n):
            w = trs[max(0, i - 13): i + 1]
            atr.append(sum(w) / len(w))
        ratio = 1.0
        bad_points = 0
        for i in range(1, n):
            score = 0
            pc, op = rows[i - 1][5], rows[i][2]
            if pc > 0 and abs(op - pc) / pc > 0.008:
                score += 1
            if rows[i][6] > 0 and rows[i - 1][6] > 0 and \
                    rows[i][6] < rows[i - 1][6] * 0.85:
                score += 1
            rng = rows[i][3] - rows[i][4]
            if atr[i] > 0 and rng > atr[i] * 2.5:
                score += 1
            if score >= 2:
                pc2, op2 = rows[i - 1][5], rows[i][2]
                if pc2 > 0 and op2 > 0:
                    local = pc2 / op2
                    if local <= 0.5 or local >= 2.0:
                        bad_points += 1            # 复权点健壮性护栏：疑似坏点
                        continue
                    ratio *= local
                    for j in range(i, n):
                        rows[j] = rows[j][:2] + tuple(x * local for x in rows[j][2:6]) \
                            + (rows[j][6],)
        if bad_points:
            print(f"  [{sym}] 复权点护栏跳过 {bad_points} 处疑似坏点")
    # ── 日线合成 ──
    days = {}
    for day, _o, h, l, c, _v, _oi in rows:
        cur = days.get(day)
        if cur is None:
            days[day] = [h, l, c]
        else:
            cur[0] = max(cur[0], h)
            cur[1] = min(cur[1], l)
            cur[2] = c
    out = sorted(days.items())
    return [d for d, _ in out], [[h, l, c] for _, (h, l, c) in out]


def ema_series(values, period):
    """talib 口径 EMA：SMA 播种。返回与 values 等长列表（前 period-1 为 None）。"""
    out = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    e = sum(values[:period]) / period
    out[period - 1] = e
    for i in range(period, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def cci_series(highs, lows, closes, period=CCI_PERIOD):
    tps = [(h + l + c) / 3.0 for h, l, c in zip(highs, lows, closes)]
    out = [None] * len(tps)
    for i in range(period - 1, len(tps)):
        w = tps[i - period + 1: i + 1]
        ma = sum(w) / period
        md = sum(abs(x - ma) for x in w) / period
        out[i] = (tps[i] - ma) / (0.015 * md) if md > 0 else None
    return out


def find_pivot_swings(highs, lows, closes):
    """复刻 _find_pivot_swings：pivot(5,5) → CCI 聚类 → 同类合并 → 同索引取舍。"""
    n = len(closes)
    if n <= PIVOT_L + PIVOT_R:
        return []
    raw = []
    for i in range(PIVOT_L, n - PIVOT_R):
        is_high = all(highs[i] > highs[j] for j in range(i - PIVOT_L, i + PIVOT_R + 1) if j != i)
        is_low = all(lows[i] < lows[j] for j in range(i - PIVOT_L, i + PIVOT_R + 1) if j != i)
        if is_high:
            raw.append({"index": i, "type": "HIGH", "price": float(highs[i])})
        if is_low:
            raw.append({"index": i, "type": "LOW", "price": float(lows[i])})
    raw.sort(key=lambda it: (it["index"], 0 if it["type"] == "HIGH" else 1))

    # CCI 相位聚类
    cci = cci_series(highs, lows, closes)
    phases = []
    active, start = None, 0
    for i in range(CCI_PERIOD - 1, n):
        v = cci[i]
        if v is None:
            continue
        if v >= CCI_TH:
            if active != "HIGH":
                active, start = "HIGH", i
        elif v <= -CCI_TH:
            if active != "LOW":
                active, start = "LOW", i
        elif active is not None:
            phases.append({"kind": active, "start": start, "end": i})
            active = None
    clustered = []
    for ph in phases:
        kind, s, e = ph["kind"], ph["start"], ph["end"]
        cand = [p for p in raw if p["type"] == kind and s <= p["index"] < e]
        if cand:
            sel = (max if kind == "HIGH" else min)(
                cand, key=lambda it: (it["price"], it["index"]))
        else:
            win = highs[s:e] if kind == "HIGH" else lows[s:e]
            if len(win) == 0:
                continue
            off = (int(max(range(len(win)), key=lambda j: win[j])) if kind == "HIGH"
                   else int(min(range(len(win)), key=lambda j: win[j])))
            sel = {"index": s + off, "type": kind, "price": float(win[off])}
        clustered.append(dict(sel))
    clustered.sort(key=lambda it: (it["index"], 0 if it["type"] == "HIGH" else 1))

    merged = []
    for p in clustered:
        if merged and merged[-1]["type"] == p["type"]:
            prev = merged[-1]
            if p["type"] == "HIGH":
                if p["price"] >= prev["price"]:
                    merged[-1] = p
            else:
                if p["price"] <= prev["price"]:
                    merged[-1] = p
            continue
        merged.append(p)
    dedup = []
    for p in merged:
        if dedup and dedup[-1]["index"] == p["index"]:
            prev = dedup[-1]
            close = closes[p["index"]]
            mid = (highs[p["index"]] + lows[p["index"]]) / 2
            dedup[-1] = p if close >= mid else prev
            continue
        dedup.append(p)
    return dedup


def analyze(highs, lows, closes):
    swings = find_pivot_swings(highs, lows, closes)
    high_pts = [s["price"] for s in swings if s["type"] == "HIGH"]
    low_pts = [s["price"] for s in swings if s["type"] == "LOW"]
    if len(high_pts) < 2 or len(low_pts) < 2:
        return None, None, None, None
    h_prev, h_new = high_pts[-2], high_pts[-1]
    l_prev, l_new = low_pts[-2], low_pts[-1]
    ema = ema_series(closes, EMA_PERIOD)
    if ema[-1] is None or ema[-1 - EMA_SLOPE_BARS] is None:
        return None, None, None, None
    ema_now, ema_before = ema[-1], ema[-1 - EMA_SLOPE_BARS]
    c = closes[-1]
    if c > ema_now and ema_now > ema_before and l_new > l_prev:
        trend = "long"
    elif c < ema_now and ema_now < ema_before and h_new < h_prev:
        trend = "short"
    else:
        return None, None, None, None
    support, resistance = l_new, h_new
    entry = ema_series(closes, 20)[-1]
    if entry is None:
        return None, None, None, None
    return trend, entry, support, resistance


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    events = []   # (sym, date, dir, entry, close0, fwd20, fwd60, touched, episode_first)
    for sym, exch in SYMS.items():
        days, bars = load_daily(sym, exch)
        highs = [b[0] for b in bars]
        lows = [b[1] for b in bars]
        closes = [b[2] for b in bars]
        n = len(bars)
        start = LOOKBACK + PIVOT_R + EMA_PERIOD + 2
        prev_key = None
        for d in range(start, n - 60):
            w0 = d - LOOKBACK + 1
            trend, entry, support, resistance = analyze(
                highs[w0: d + 1], lows[w0: d + 1], closes[w0: d + 1])
            if trend is None:
                prev_key = None
                continue
            if trend == "long":
                reward, risk = resistance - entry, entry - support
            else:
                reward, risk = entry - support, resistance - entry
            rr = reward / risk if risk > 0 else 0.0
            if risk <= 0 or rr < MIN_RR:
                prev_key = None
                continue
            c0 = closes[d]
            f20 = (closes[d + 20] / c0 - 1) * (1 if trend == "long" else -1)
            f60 = (closes[d + 60] / c0 - 1) * (1 if trend == "long" else -1)
            touch = any((lows[j] <= entry <= highs[j]) for j in range(d + 1, min(d + 6, n)))
            key = (sym, trend)
            first = key != prev_key
            prev_key = key
            events.append((sym, days[d], trend, f20, f60, touch, first))

    def stats(sub, idx):
        xs = [e[idx] for e in sub]
        if not xs:
            return (0, None, None)
        return (len(xs), sum(1 for x in xs if x > 0) / len(xs),
                sum(xs) / len(xs))

    def rows(title, groups):
        L = ["", f"## {title}", "",
             "| 口径 | n | 20日胜率 | 20日均收益 | 60日胜率 | 60日均收益 |",
             "|---|---|---|---|---|---|"]
        for name, sub in groups:
            n20, w20, a20 = stats(sub, 3)
            n60, w60, a60 = stats(sub, 4)
            if not n20:
                L.append(f"| {name} | 0 | - | - | - | - |")
                continue
            L.append(f"| {name} | {n20} | {w20:.1%} | {a20:+.2%} | "
                     f"{w60:.1%} | {a60:+.2%} |")
        return L

    L = ["# RS017 补课②：TrendPullback 选品离线回放（选品质量建档）", "",
         "- 子集声明：生产池 10 主连中本地 60m 可覆盖 RB/CU/M/TA/MA（5/10；",
         "  AG 本地有但不在生产池）；日线由 60m 合成（近似 akshare 日线）；",
         "- 判据逐条复刻 poolscan/pa.background（pivot5,5+CCI 聚类+EMA21 斜率",
         "  +HH/HL；entry=EMA20；RR≥1.5）；逐日滚动 120 根窗全窗重算；",
         "- 收益=入选日收盘起、方向调整、无成本无执行建模（选品质量口径）。", ""]

    all_e = events
    ep_e = [e for e in events if e[6]]
    L += rows("1. 总体（逐日口径 / episode 首日口径）",
              [("逐日入选", all_e), ("episode 首日", ep_e)])

    L += rows("2. 分品种（逐日口径）",
              [(s, [e for e in all_e if e[0] == s]) for s in SYMS])

    years = sorted({e[1][:4] for e in all_e})
    L += rows("3. 分年度（逐日口径）",
              [(y, [e for e in all_e if e[1][:4] == y]) for y in years])

    L += rows("4. in/out（2022 切分，逐日口径）",
              [("in 2015-2021", [e for e in all_e if e[1] < SPLIT]),
               ("out 2022-", [e for e in all_e if e[1] >= SPLIT])])

    touch = sum(1 for e in all_e if e[5]) / len(all_e) if all_e else 0
    L += ["", f"EMA20 限价 5 日内触碰率：{touch:.1%}", ""]

    ext = sorted(all_e, key=lambda e: abs(e[3]), reverse=True)[:5]
    L += ["", "诊断：|20日收益| top5", ""]
    for e in ext:
        L.append(f"- {e[0]} {e[1]} {e[2]} f20={e[3]:+.3e}")

    # 累计曲线回撤（事件序 20 日收益累加；重叠口径）
    seq = sorted(all_e, key=lambda e: e[1])
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for e in seq:
        cum += e[3]
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    L += ["## 5. 累计曲线回撤（事件序 20 日收益累加；窗口重叠口径，仅作相对比较）", "",
          f"- 事件 {len(seq)}；累计收益（简单累加）{cum:+.1%}；**最大回撤 {mdd:.1%}"
          f"（同口径）**", "",
          "判读：方向引擎为趋势跟随（摆动点确认滞后），CHOP 不产出；",
          "本表回答\"入选后 20/60 日方向是否占优\"，用于选品质量建档与",
          "退役/保留判定的数据基线；非可交易回测。"]

    out = OUT / "trendpullback_replay.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("->", out)
    n20, w20, a20 = stats(all_e, 3)
    print(f"events={n20} f20 win={w20:.1%} avg={a20:+.2%} mdd={mdd:.1%}")


if __name__ == "__main__":
    main()
