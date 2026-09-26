"""多年历史数据评估（仅分析用；主连跳空已知，不进主逻辑）。

5m 作为最小分析周期驱动完整选品流水线（15m 聚合/MA/RR），
跨年 as_of 扫描 -> RR 分布分位 -> min_rr 证据门槛 + 原因分布报告。
"""

from __future__ import annotations

import glob
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from vnpy.trader.constant import Exchange, Interval  # noqa: E402
from vnpy.trader.object import BarData  # noqa: E402

DATA = os.environ.get("TRADEPLAY_DATA", r"D:/AIprj/tradereplay/data")
QUANT_REPO = os.environ.get("QUANT_REPO_PATH", r"D:/AIprj/quant-repo")
SYMBOLS = [tuple(s.split("@")) for s in os.environ.get(
    "EVAL_SYMBOLS", "CU@SHFE,RB@SHFE,AG@SHFE,M@DCE,MA@CZCE,TA@CZCE").split(",")]
STEP_BARS = int(os.environ.get("EVAL_STEP_BARS", "48"))       # ≈4小时一个 as_of
START_YEAR = int(os.environ.get("EVAL_START_YEAR", "2019"))
OUT = os.path.join(os.path.dirname(__file__), "output")

sys.path.insert(0, QUANT_REPO)


def _find(interval: str, symbol: str) -> str:
    hits = glob.glob(rf"{DATA}/{interval}/*/{symbol}/{symbol}.csv")
    if not hits:
        raise FileNotFoundError(f"{interval}/{symbol}")
    return hits[0]


def load(interval: str, symbol: str) -> pd.DataFrame:
    df = pd.read_csv(_find(interval, symbol))
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.sort_values("datetime").reset_index(drop=True)


def to_bars(df: pd.DataFrame, symbol: str, exchange: str,
            interval: Interval) -> list[BarData]:
    from .market import canonical_symbol

    code = canonical_symbol(symbol, exchange)
    return [BarData(symbol=code, exchange=Exchange(exchange), datetime=r.datetime,
                    gateway_name="EVAL", interval=interval,
                    open_price=float(r.open), high_price=float(r.high),
                    low_price=float(r.low), close_price=float(r.close),
                    volume=float(r.volume))
            for r in df.itertuples(index=False)]


def daily_from_60m(df60: pd.DataFrame, symbol: str, exchange: str) -> list[BarData]:
    from .market import canonical_symbol

    code = canonical_symbol(symbol, exchange)
    rows = []
    for day, g in df60.groupby(df60["datetime"].dt.date):
        rows.append(BarData(symbol=code, exchange=Exchange(exchange), datetime=pd.Timestamp(day).to_pydatetime(),
                            gateway_name="EVAL", interval=Interval.DAILY,
                            open_price=float(g["open"].iloc[0]),
                            high_price=float(g["high"].max()),
                            low_price=float(g["low"].min()),
                            close_price=float(g["close"].iloc[-1]),
                            volume=float(g["volume"].sum())))
    return rows


def forward_outcome(df60: pd.DataFrame, as_of, direction: str,
                    support: float, resistance: float, horizon: int = 120):
    """前瞻标注：horizon 根内先到 T1 还是 SL（收盘价口径）。"""
    fwd = df60[df60["datetime"] > as_of].head(horizon)
    for i, r in enumerate(fwd.itertuples(index=False), start=1):
        if direction == "long":
            if r.close <= support:
                return "SL", i
            if r.close >= resistance:
                return "T1", i
        else:
            if r.close >= resistance:
                return "SL", i
            if r.close <= support:
                return "T1", i
    return "OPEN", None


class EvalFeed:
    """只暴露 as_of 之前历史的查询 feed（5m 作 minute 源）。"""

    def __init__(self, daily, hour, minute, as_of) -> None:
        self._data = {Interval.DAILY: daily, Interval.HOUR: hour,
                      Interval.MINUTE: minute}
        self.as_of = as_of

    def query_bar_history(self, req, output=None):
        end = min(req.end, self.as_of)
        return [b for b in self._data[req.interval]
                if req.start <= b.datetime <= end]


def main() -> None:
    from poolscan import MarketPullbackScanner, _load_config

    scan_base = dict(_load_config().get("scan", {}) or {})
    scan_base.update({"market_min_rr": 0.01, "min_minute_bars_in_15": 2,
                      "minute_days": 30})  # 评估态：放行 RR 以采集分布
    os.makedirs(OUT, exist_ok=True)
    pool_report = {}
    pooled_rr: list[float] = []
    pooled_outcomes: list[dict] = []
    pooled_reason: dict[str, int] = {}
    for symbol, exchange in SYMBOLS:
        try:
            df5 = load("5m", symbol)
        except FileNotFoundError:
            print(f"[skip] {symbol}: 无 5m 数据")
            continue
        df5 = df5[df5["datetime"].dt.year >= START_YEAR]
        if len(df5) < 500:
            print(f"[skip] {symbol}: 5m 数据不足 {len(df5)}")
            continue
        df60 = load("60m", symbol)
        daily = daily_from_60m(df60, symbol, exchange)
        minute = to_bars(df5, symbol, exchange, Interval.MINUTE)
        hour = to_bars(df60, symbol, exchange, Interval.HOUR)
        daily_bars = daily
        scanner = MarketPullbackScanner(scan_base)
        rr_list: list[float] = []
        outcomes: list[dict] = []
        reasons: dict[str, int] = {}
        n = 0
        for i in range(60, len(minute), STEP_BARS):
            as_of = minute[i].datetime
            hist_feed = EvalFeed(daily_bars, hour, minute[:i], as_of)
            try:
                entry, reason = scanner._evaluate_symbol(
                    hist_feed, {"symbol": symbol.upper(), "exchange": exchange},
                    as_of=as_of)
            except Exception as exc:  # noqa: BLE001
                reasons[f"error:{type(exc).__name__}"] = reasons.get(
                    f"error:{type(exc).__name__}", 0) + 1
                continue
            reasons[reason] = reasons.get(reason, 0) + 1
            n += 1
            if entry is not None:
                rr_list.append(float(entry.rr_ratio))
                sup, res = float(entry.support), float(entry.resistance)
                result, bars_used = forward_outcome(df60, as_of,
                                                    entry.direction, sup, res)
                outcomes.append({"rr": round(float(entry.rr_ratio), 3),
                                 "outcome": result, "bars": bars_used})
        pooled_rr.extend(rr_list)
        pooled_outcomes.extend(outcomes)
        for k, v in reasons.items():
            pooled_reason[k] = pooled_reason.get(k, 0) + v
        pool_report[f"{symbol}.{exchange}"] = {
            "as_of_points": n, "reasons": reasons,
            "rr_p50_p70_p90": [round(float(np.percentile(rr_list, p)), 3)
                               for p in (50, 70, 90)] if rr_list else None,
        }
        pool_report[f"{symbol}.{exchange}"]["outcomes"] = outcomes
        print(f"{symbol}.{exchange}: as_of={n} entries={len(rr_list)} "
              f"rrP50/P70/P90={pool_report[f'{symbol}.{exchange}']['rr_p50_p70_p90']}")

    rr = np.array(pooled_rr)
    percentiles = {f"P{p}": round(float(np.percentile(rr, p)), 3)
                   for p in (25, 50, 60, 70, 75, 80, 90)} if len(rr) else {}
    gate_table = {str(g): round(float((rr >= g).mean()), 4)
                  for g in (0.8, 1.0, 1.2, 1.5, 2.0)} if len(rr) else {}
    gate_ab: dict = {}
    for g in (1.0, 1.2, 1.5, 2.0):
        sel = [o for o in pooled_outcomes if o["rr"] >= g]
        decided = [o for o in sel if o["outcome"] in ("T1", "SL")]
        wins = sum(1 for o in decided if o["outcome"] == "T1")
        gate_ab[str(g)] = {
            "entries": len(sel), "decided": len(decided),
            "win_rate": round(wins / len(decided), 4) if decided else None,
            "avg_bars": round(sum(o["bars"] or 0 for o in decided)
                              / len(decided), 1) if decided else None,
        }
    report = {
        "as_of_points": n, "entries": int(len(rr)),
        "reason_distribution": pooled_reason,
        "rr_percentiles": percentiles,
        "pass_rate_at_gate": gate_table,
        "gate_ab": gate_ab,
        "recommended_min_rr": percentiles.get("P70"),
        "per_symbol": pool_report,
    }
    with open(os.path.join(OUT, "eval_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "eval_report.md"), "w", encoding="utf-8") as f:
        f.write("# 多年历史校准报告（5m 全流水线）\n\n```json\n")
        f.write(json.dumps(report, ensure_ascii=False, indent=2))
        f.write("\n```\n")
    if len(rr):
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(np.clip(rr, 0, 6), bins=60, color="#1f77b4")
        for g, c in ((0.8, "#ff7f0e"), (1.0, "#2ca02c"), (1.5, "#d62728"), (2.0, "#7f7f7f")):
            ax.axvline(g, color=c, ls="--", lw=1)
            ax.text(g, ax.get_ylim()[1] * 0.95, str(g), color=c, fontsize=8)
        ax.set_title("RR distribution on multi-year real data (5m pipeline)")
        ax.set_xlabel("rr_ratio (capped 6)")
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, "rr_distribution.png"), dpi=130)
        plt.close(fig)
    print(json.dumps({k: report[k] for k in ("as_of_points", "entries",
          "rr_percentiles", "pass_rate_at_gate", "recommended_min_rr")},
          ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
