"""按指定时间回放：选品(as_of) -> 择时契约 -> REPLAY 引擎盯后续K线。"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, HistoryRequest

from .adapters import AkshareOneMinuteFeed
from .engine import PatimingEngine


QUANT_REPO = os.environ.get("QUANT_REPO_PATH", r"D:/AIprj/quant-repo")


class HistoryFeed:
    """真实K线回放 feed：只暴露 as_of 之前的历史。"""

    def __init__(self, daily, hour, minute, as_of) -> None:
        self._data = {Interval.DAILY: daily, Interval.HOUR: hour,
                      Interval.MINUTE: minute}
        self.as_of = as_of

    def query_bar_history(self, req: HistoryRequest, output=None):
        return [b for b in self._data[req.interval]
                if req.start <= b.datetime <= min(req.end, self.as_of)]


def run(symbol: str = "RB0", exchange: str = "SHFE",
        as_of: str | None = None, watch: int = 60,
        min_rr: float = 1.0) -> dict:
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        scratch = os.path.join(out_dir, f"replay_runner.db{suffix}")
        if os.path.exists(scratch):
            os.remove(scratch)
    sys.path.insert(0, QUANT_REPO)
    from poolscan import MarketPullbackScanner, _load_config

    feed = AkshareOneMinuteFeed()
    bars1m = feed.fetch_1m(symbol, exchange)
    bars60 = feed.fetch_minutes(symbol, exchange, period="60")
    from .db import Database

    code = symbol.lower() if exchange == "SHFE" else symbol
    store = Database(os.path.join(out_dir, "bars_store.db"))
    for rows, itv in ((bars1m, "1m"), (bars60, "60m")):
        store.save_bars([{
            "symbol": code, "exchange": exchange, "interval": itv,
            "dt": b.datetime.strftime("%Y-%m-%d %H:%M:%S"),
            "open": b.open_price, "high": b.high_price,
            "low": b.low_price, "close": b.close_price,
            "volume": b.volume} for b in rows])
    bars1m = [BarData(symbol=code, exchange=Exchange(exchange),
                      datetime=datetime.strptime(r["dt"], "%Y-%m-%d %H:%M:%S"),
                      gateway_name="STORE", interval=Interval.MINUTE,
                      open_price=r["open"], high_price=r["high"],
                      low_price=r["low"], close_price=r["close"],
                      volume=r["volume"])
              for r in store.load_bars(code, exchange, "1m")]
    print(f"[落库累积] 本地 1m 深度: {len(bars1m)}")
    import akshare as ak

    daily_frame = ak.futures_zh_daily_sina(symbol=symbol.upper())
    daily = [BarData(symbol=symbol.upper(), exchange=Exchange(exchange),
                     datetime=datetime.strptime(str(r["date"]), "%Y-%m-%d"),
                     gateway_name="AKSHARE_REAL", interval=Interval.DAILY,
                     open_price=float(r["open"]), high_price=float(r["high"]),
                     low_price=float(r["low"]), close_price=float(r["close"]),
                     volume=float(r["volume"])) for r in daily_frame.to_dict("records")]
    anchor = datetime.strptime(as_of, "%Y-%m-%d %H:%M") if as_of else bars1m[-1].datetime
    hist = HistoryFeed(daily, bars60, [b for b in bars1m if b.datetime <= anchor], anchor)
    scan_cfg = dict(_load_config().get("scan", {}) or {}, market_min_rr=min_rr)
    scanner = MarketPullbackScanner(scan_cfg)
    item = {"symbol": symbol.upper(), "exchange": exchange}
    entry, reason = scanner._evaluate_symbol(hist, item, as_of=anchor)
    print(f"[选品@{anchor}] reason={reason} entry={'YES ' + entry.direction if entry else 'no'}")

    clock = {"t": anchor}
    eng = PatimingEngine(os.path.join(os.path.dirname(__file__), "output",
                                      "replay_runner.db"),
                         {"warmup_min_exec": 10, "atr_period": 5,
                          "price_tick": 1.0, "buffer_ticks": 2,
                          "expire_bars_exec": 30, "min_stop_atr": 0.05,
                          "max_stop_atr": 50.0, "bar_min_atr": 0.05,
                          "bar_max_atr": 50.0, "overlap_max": 1.0},
                         clock=lambda: clock["t"], run_mode="REPLAY")
    instruction = {
        "instruction_id": "REPLAY-SEL", "producer_revision": 1,
        "symbol": f"{symbol.lower()}.{exchange}",
        "selection_timeframe": "60m", "exec_timeframe": "1m",
        "context_tag": "breakout", "signal_categories": "ALL",
        "key_levels": dict(entry.key_levels) if entry else {},
        "reason_code": "BREAKOUT_WATCH",
        "reason_note": f"replay@{anchor} selection={reason}",
    }
    r = eng.submit_instruction("strategy:replay_runner", instruction)
    assert r["ok"], r
    eng.reconcile()
    future = [b for b in bars1m if anchor < b.datetime]
    for bar in future[:watch]:
        clock["t"] = bar.datetime
        eng.on_1m_bar(bar)
    eng.flush_due(future[watch - 1].datetime if future else anchor)
    task = eng.tasks.get((f"{symbol.lower()}.{exchange}", "1m"))
    alerts = [(a.signal_id, a.lifecycle) for a in task.alerts.values()] if task else []
    print(f"[择时回放] watch={min(watch, len(future))} bars alerts={alerts}")
    eng.close()
    return {"selection_reason": reason, "entry": bool(entry), "alerts": alerts}


if __name__ == "__main__":
    run()
