"""多品种真实数据批量回放 runner（对比工具共享）。"""

import os
import tempfile

SYMBOLS = [("RB0", "SHFE"), ("CU0", "SHFE"), ("AG0", "SHFE"),
           ("M0", "DCE"), ("MA0", "CZCE"), ("TA0", "CZCE")]
OVERRIDES = {"warmup_min_exec": 10, "atr_period": 5, "price_tick": 1.0,
             "buffer_ticks": 2, "expire_bars_exec": 30, "min_stop_atr": 0.05,
             "max_stop_atr": 50.0, "bar_min_atr": 0.05, "bar_max_atr": 50.0,
             "overlap_max": 1.0}
ALL_CATEGORIES = ["breakout", "fake_breakout", "second_breakout",
                  "ema_pullback", "structure_pullback", "range_edge",
                  "h2_l2", "double_top_bottom", "wedge"]


def run_symbol(feed, symbol: str, exchange: str) -> dict:
    from vnpy_patiming.engine import PatimingEngine

    code = symbol.lower() if exchange == "SHFE" else symbol
    vt = f"{code}.{exchange}"
    bars = feed.fetch_minutes(symbol, exchange, period="1")
    if len(bars) < 60:
        return {"error": f"bars={len(bars)}"}
    lows100 = min(b.low_price for b in bars[:100])
    highs100 = max(b.high_price for b in bars[:100])
    level = round((lows100 + highs100) / 2, 2)
    clock = {"t": bars[0].datetime}
    eng = PatimingEngine(os.path.join(tempfile.mkdtemp(), "b.db"),
                         dict(OVERRIDES), clock=lambda: clock["t"])
    r = eng.submit_instruction("strategy:probe", {
        "instruction_id": "BATCH-1", "producer_revision": 1,
        "symbol": vt, "selection_timeframe": "1m", "exec_timeframe": "1m",
        "context_tag": "breakout", "signal_categories": ALL_CATEGORIES,
        "key_levels": {"prior_high": level,
                       "prior_low": round(level - (highs100 - lows100) / 2, 2)},
        "reason_code": "BREAKOUT_WATCH", "reason_note": "batch probe"})
    if not r.get("ok"):
        return {"error": str(r)}
    eng.reconcile()
    for bar in bars:
        clock["t"] = bar.datetime
        eng.on_1m_bar(bar)
    eng.flush_due(bars[-1].datetime)
    task = eng.tasks.get((vt, "1m"))
    counts: dict[str, int] = {}
    for alert in (task.alerts.values() if task else []):
        counts[f"{alert.signal_id}/{alert.lifecycle}"] = counts.get(
            f"{alert.signal_id}/{alert.lifecycle}", 0) + 1
    triggered = sum(1 for a in (task.alerts.values() if task else [])
                    if a.lifecycle == "TRIGGERED")
    pivots = len(task.pivots.confirmed) if task else 0
    eng.close()
    return {"bars": len(bars), "alerts": counts, "triggered": triggered,
            "pivots": pivots}
