"""出场阶梯 A/B 评估（真实 60m 多年数据）：多策略同场对比。

入场模型：样本时点每 2 根收盘取一个，方向=最近确认摆动点方向，
止损=反向极值界，风险=risk=|entry-stop|。
出场策略：t1_0.5 / t1_1.0 / t1_2.0 目标阶梯；
pivot_trail=摆动点移动止损；counter_pivot=反向摆动点确认离场（择时信号联动）；
time_20=超时平仓。
"""

from __future__ import annotations

from vnpy_patiming.adapters import AkshareOneMinuteFeed

SYMBOLS = [("RB0", "SHFE"), ("CU0", "SHFE"), ("AG0", "SHFE"),
           ("M0", "DCE"), ("MA0", "CZCE"), ("TA0", "CZCE")]
POLICIES = ["t1_1.0", "t1_2.0", "t1_3.0", "pivot_trail",
            "counter_pivot", "time_20"]
HORIZON = 40


def confirmed_pivots(h: list, l: list, k: int = 2) -> list[tuple]:
    out = []
    n = len(h)
    for i in range(k, n - k):
        if all(h[i] > h[j] for j in range(i - k, i + k + 1) if j != i):
            out.append(("H", h[i], i, i + k))
        if all(l[i] < l[j] for j in range(i - k, i + k + 1) if j != i):
            out.append(("L", l[i], i, i + k))
    return out


def evaluate_symbol(symbol: str, exchange: str,
                    feed: AkshareOneMinuteFeed) -> dict:
    bars = feed.fetch_minutes(symbol, exchange, period="60")
    h = [b.high_price for b in bars]
    l = [b.low_price for b in bars]
    c = [b.close_price for b in bars]
    pivots = confirmed_pivots(h, l)
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
          if i else h[0] - l[0] for i in range(len(bars))]
    atr = [sum(tr[max(0, i - 13) : i + 1]) / len(tr[max(0, i - 13) : i + 1])
           for i in range(len(bars))]
    stats = {p: {"n": 0, "win": 0, "loss": 0, "open": 0,
                 "sum_r": 0.0, "sum_bars": 0} for p in POLICIES}

    for a in range(60, len(bars) - HORIZON - 2, 2):
        past = [p for p in pivots if p[2] <= a]
        if not past:
            continue
        last = past[-1]
        direction = 1.0 if last[0] == "H" else -1.0
        entry = c[a]
        stop = min(l[a - 20 : a + 1]) if direction == 1.0 else max(h[a - 20 : a + 1])
        risk = (entry - stop) * direction
        if risk <= 0:
            continue
        best = entry
        trail = stop
        res: dict[str, tuple[str, float, int]] = {}
        fi = 0
        fwd = [p for p in pivots if p[2] > a]
        for i in range(1, HORIZON + 1):
            bi = a + i
            best = max(best, h[bi]) if direction == 1.0 else min(best, l[bi])
            trail = (max(trail, best - 1.0 * risk) if direction == 1.0
                     else min(trail, best + 1.0 * risk))
            lo_t, hi_t = l[bi], h[bi]
            for name, mult in (("t1_1.0", 1.0), ("t1_2.0", 2.0), ("t1_3.0", 3.0)):
                if name in res:
                    continue
                level = entry + direction * mult * risk
                stop_touched = (lo_t <= stop) if direction == 1.0 else (hi_t >= stop)
                tgt_touched = (hi_t >= level) if direction == 1.0 else (lo_t <= level)
                if stop_touched:
                    res[name] = ("SL", stop, i)
                elif tgt_touched:
                    res[name] = ("T", level, i)
            if "pivot_trail" not in res:
                touched = lo_t <= trail if direction == 1.0 else hi_t >= trail
                if touched:
                    px = trail
                    res["pivot_trail"] = ("T", px, i)
            while fi < len(fwd) and fwd[fi][3] <= bi:
                kind, price, _pi, _ci = fwd[fi]
                if "counter_pivot" not in res and kind != ("H" if direction == 1.0 else "L"):
                    px = price if (price - entry) * direction > 0 else c[bi]
                    res["counter_pivot"] = ("T", px, i)
                fi += 1
            if "time_20" not in res and i >= 20:
                res["time_20"] = ("T", c[bi], i)
        for p in POLICIES:
            bucket = stats[p]
            bucket["n"] += 1
            if p in res:
                _state, price, i = res[p]
                r = (price - entry) * direction / risk
                bucket["sum_r"] += r
                bucket["sum_bars"] += i
                if r > 0:
                    bucket["win"] += 1
                else:
                    bucket["loss"] += 1
            else:
                bucket["open"] += 1
    return stats


def main() -> None:
    feed = AkshareOneMinuteFeed()
    total = {p: {"n": 0, "win": 0, "loss": 0, "open": 0,
                 "sum_r": 0.0, "sum_bars": 0} for p in POLICIES}
    for symbol, exchange in SYMBOLS:
        try:
            stats = evaluate_symbol(symbol, exchange, feed)
        except Exception as exc:  # noqa: BLE001
            print(symbol, "SKIP:", exc)
            continue
        for p, b in stats.items():
            for k in ("n", "win", "loss", "open", "sum_r", "sum_bars"):
                total[p][k] += b[k]
    print(f"{'policy':<16}{'n':>6}{'win%':>8}{'avgR':>8}{'avgBars':>9}")
    for p in POLICIES:
        b = total[p]
        decided = b["win"] + b["loss"]
        wr = round(100 * b["win"] / decided, 1) if decided else 0.0
        ar = round(b["sum_r"] / decided, 3) if decided else 0.0
        ab = round(b["sum_bars"] / max(b["n"], 1), 1)
        print(f"{p:<16}{b['n']:>6}{wr:>8}{ar:>8}{ab:>9}")


if __name__ == "__main__":
    main()
