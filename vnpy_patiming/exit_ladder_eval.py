"""出场阶梯 A/B 评估（真实 60m 多年数据）：选品级入场 + 多策略出场对比。

入场模型（选品级）：PABackgroundEngine 趋势定方向；聚类支撑/压力定结构；
回调触及 + 确认收盘 -> entry=确认收盘价；止损=位外侧 0.25×ATR。
出场策略：t1_1.0 / t1_2.0 / t1_3.0 目标阶梯；pivot_trail；counter_pivot（择时联动）；time_20。
"""

from __future__ import annotations

import glob
import os
import sys
from datetime import datetime

import pandas as pd

from vnpy.trader.constant import Exchange
from vnpy.trader.object import BarData

from vnpy_patiming.adapters import AkshareOneMinuteFeed

from vnpy_patiming.adapters import AkshareOneMinuteFeed

TRADEPLAY_DATA = os.environ.get("TRADEPLAY_DATA", r"D:/AIprj/tradereplay/data")
QUANT_REPO = os.environ.get("QUANT_REPO_PATH", r"D:/AIprj/quant-repo")
sys.path.insert(0, QUANT_REPO)

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
    prod = symbol.rstrip("0123456789")
    hits = glob.glob(rf"{TRADEPLAY_DATA}/60m/*/{prod}/{prod}.csv")
    if not hits:
        raise FileNotFoundError(f"60m/{symbol}")
    df = pd.read_csv(hits[0])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df[(df["datetime"].dt.year >= 2015) & (df["datetime"].dt.year <= 2025)]
    bars = [BarData(symbol=symbol, exchange=Exchange(exchange), datetime=r.datetime,
                    gateway_name="TRADEPLAY", open_price=float(r.open),
                    high_price=float(r.high), low_price=float(r.low),
                    close_price=float(r.close), volume=float(r.volume))
            for r in df.itertuples(index=False)]
    h = [b.high_price for b in bars]
    l = [b.low_price for b in bars]
    c = [b.close_price for b in bars]
    import numpy as np
    from talib import ATR

    atr = ATR(np.asarray(h, dtype=float), np.asarray(l, dtype=float),
              np.asarray(c, dtype=float), timeperiod=14)
    stats = {p: {"n": 0, "win": 0, "loss": 0, "open": 0,
                 "sum_r": 0.0, "sum_bars": 0} for p in POLICIES}

    sys.path.insert(0, QUANT_REPO)
    from pa.background import PABackgroundEngine

    pb = PABackgroundEngine()
    frame = pd.DataFrame({"high": h, "low": l, "close": c})

    for a in range(300, len(bars) - HORIZON - 2, 2):
        structure = pb.analyze_market_structure_and_zone(frame.iloc[a - 299 : a + 1])
        trend = structure["trend"]
        entry = c[a]
        if trend == "BULL_TREND":
            direction, support, resistance = 1.0, float(structure["nearest_support"]), float(structure["nearest_resistance"])
        elif trend == "BEAR_TREND":
            direction, support, resistance = -1.0, float(structure["nearest_resistance"]), float(structure["nearest_support"])
        else:
            continue
        stop = (support - 0.25 * atr[a]) if direction == 1.0 else (resistance + 0.25 * atr[a])
        risk = (entry - stop) * direction
        if risk <= 0:
            continue
        # v2 回调确认：上一根触及结构位、当前收盘收回位内侧（spec：二次测试确认）
        prev_lo, prev_hi = l[a - 1], h[a - 1]
        tol = 0.25 * atr[a]
        touched = (prev_lo <= support + tol) if direction == 1.0 else (prev_hi >= resistance - tol)
        confirmed = (c[a - 1] >= support) if direction == 1.0 else (c[a - 1] <= resistance)
        entry_zone_ok = (entry - support) * direction > 0
        if not (touched and confirmed and entry_zone_ok):
            continue
        best = entry
        trail = stop
        pivots = confirmed_pivots(h, l)
        fwd = [p for p in pivots if p[3] > a]
        res: dict[str, tuple[str, float, int]] = {}
        fi = 0
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
