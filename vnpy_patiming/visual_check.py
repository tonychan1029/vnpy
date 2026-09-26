"""视觉检查：真实数据回放与结构聚类绘图（量化效果人工核对）。

运行：python -m vnpy_patiming.visual_check
输出：vnpy_patiming/output/*.png（不入库）
"""

from __future__ import annotations

import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from vnpy.trader.constant import Interval  # noqa: E402

from .adapters import AkshareOneMinuteFeed  # noqa: E402
from .config import build_config  # noqa: E402
from .engine import PatimingEngine  # noqa: E402
from .structures import PivotDetector  # noqa: E402


QUANT_REPO = os.environ.get("QUANT_REPO_PATH", r"D:/AIprj/quant-repo")
OUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def _structure_chart(bars60) -> str:
    sys.path.insert(0, QUANT_REPO)
    from pa.background import PABackgroundEngine

    import pandas as pd

    frame = pd.DataFrame({
        "high": [b.high_price for b in bars60],
        "low": [b.low_price for b in bars60],
        "close": [b.close_price for b in bars60],
    })
    structure = PABackgroundEngine().analyze_market_structure_and_zone(frame)
    pivots = PivotDetector(2)
    for bar in bars60:
        pivots.update(bar)

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot([b.datetime for b in bars60], [b.close_price for b in bars60],
            color="#1f77b4", lw=1.2, label="close")
    ax.vlines([b.datetime for b in bars60],
              [b.low_price for b in bars60], [b.high_price for b in bars60],
              color="#bbbbbb", lw=0.6, alpha=0.7)
    for p in pivots.confirmed:
        if p.kind == "H":
            ax.scatter(p.pivot_bar_time, p.price, marker="v", color="#d62728", s=42, zorder=3)
        else:
            ax.scatter(p.pivot_bar_time, p.price, marker="^", color="#2ca02c", s=42, zorder=3)
    ax.axhline(float(structure["nearest_support"]), color="#2ca02c", ls="--", lw=1.2,
               label=f"support {float(structure['nearest_support']):g}")
    ax.axhline(float(structure["nearest_resistance"]), color="#d62728", ls="--", lw=1.2,
               label=f"resistance {float(structure['nearest_resistance']):g}")
    ax.set_title(f"PA structure clustering | {structure['trend']} | real 60m bars={len(bars60)}")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "structure_levels.png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def _replay_chart(bars, eng, task) -> str:
    idx = {b.datetime: i for i, b in enumerate(bars)}
    fig, ax = plt.subplots(figsize=(15, 7))
    ax.plot(range(len(bars)), [b.close_price for b in bars],
            color="#1f77b4", lw=1.0, label="close")
    ax.vlines(range(len(bars)), [b.low_price for b in bars],
              [b.high_price for b in bars], color="#cccccc", lw=0.5, alpha=0.6)
    for p in task.pivots.confirmed:
        i = idx.get(p.pivot_bar_time)
        if i is None:
            continue
        ax.scatter(i, p.price, marker="v" if p.kind == "H" else "^",
                   color="#999999", s=30, zorder=3)
    colors = {"long": "#2ca02c", "short": "#d62728"}
    for alert in task.alerts.values():
        i = idx.get(alert.armed_bar_time)
        if i is None:
            continue
        color = colors.get(alert.direction, "#7f7f7f")
        ax.axhline(alert.trigger["level"], color=color, ls=":", lw=0.8, alpha=0.6)
        ax.scatter(i, alert.trigger["level"], marker="o", s=60, facecolors="none",
                   edgecolors=color, lw=1.5, zorder=4)
        if alert.lifecycle == "TRIGGERED":
            ax.scatter(i, alert.trigger["level"], marker="*", color="#ff7f0e",
                       s=120, zorder=5)
        else:
            ax.annotate(alert.lifecycle[:4], (i, alert.trigger["level"]),
                        fontsize=7, color="#666666")
    ax.set_title(f"replay on real 1m | alerts={len(task.alerts)} "
                 f"(o=armed, *=triggered, gray=confirmed pivots)")
    fig.tight_layout()
    path = os.path.join(OUT_DIR, "replay_signals.png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        scratch = os.path.join(OUT_DIR, f"visual_replay.db{suffix}")
        if os.path.exists(scratch):
            os.remove(scratch)
    symbol = os.environ.get("VIS_SYMBOL", "RB0")
    exchange = os.environ.get("VIS_EXCHANGE", "SHFE")
    feed = AkshareOneMinuteFeed()
    bars60 = feed.fetch_minutes(symbol, exchange, period="60")
    bars1m = feed.fetch_1m(symbol, exchange)
    print(f"real bars: 60m={len(bars60)} 1m={len(bars1m)} "
          f"last={bars1m[-1].datetime}")

    print("structure chart:", _structure_chart(bars60))

    lows100 = min(b.low_price for b in bars1m[:100])
    highs100 = max(b.high_price for b in bars1m[:100])
    mid_level = round((lows100 + highs100) / 2, 2)

    clock_ref = {"t": bars1m[0].datetime}
    eng = PatimingEngine(
        os.path.join(OUT_DIR, "visual_replay.db"),
        {"warmup_min_exec": 10, "atr_period": 5, "price_tick": 1.0,
         "buffer_ticks": 2, "expire_bars_exec": 30, "min_stop_atr": 0.05,
         "max_stop_atr": 50.0, "bar_min_atr": 0.05, "bar_max_atr": 50.0,
         "overlap_max": 1.0},
        clock=lambda: clock_ref["t"],
    )
    submit_result = eng.submit_instruction("strategy:visual", {
        "instruction_id": "VIS-1", "producer_revision": 1,
        "symbol": f"{symbol.lower()}.{exchange}",
        "selection_timeframe": "1m", "exec_timeframe": "1m",
        "context_tag": "breakout", "signal_categories": "ALL",
        "key_levels": {"prior_high": mid_level},
        "reason_code": "BREAKOUT_WATCH", "reason_note": "visual check",
    })
    print("submit:", submit_result)
    eng.reconcile()
    for bar in bars1m:
        clock_ref["t"] = bar.datetime
        eng.on_1m_bar(bar)
    eng.flush_due(bars1m[-1].datetime)
    task = eng.tasks.get((f"{symbol.lower()}.{exchange}", "1m"))
    level = round((lows100 + highs100) / 2, 2)
    post = bars1m[100:]
    up = sum(1 for b in post if b.close_price > level and b.close_price > b.open_price
             and (b.close_price - b.open_price) >= 0.6 * (b.high_price - b.low_price))
    down = sum(1 for b in post if b.close_price < level
               and (b.open_price - b.close_price) >= 0.6 * (b.high_price - b.low_price))
    closes = [b.close_price for b in post]
    print(f"level={level} post_min={min(closes)} post_max={max(closes)} "
          f"strong_up_cross={up} strong_down_cross={down} "
          f"pivots={len(task.pivots.confirmed) if task else 0}")
    print("tasks:", list(eng.tasks))
    counts: dict[str, int] = {}
    if task:
        for alert in task.alerts.values():
            counts[f"{alert.signal_id}/{alert.lifecycle}"] = counts.get(
                f"{alert.signal_id}/{alert.lifecycle}", 0) + 1
    print("replay alerts:", counts)
    print("replay chart:", _replay_chart(bars1m, eng, task))
    eng.close()


if __name__ == "__main__":
    main()
