"""实弹冒烟：真实行情 + 引擎全链路（默认关闭，防误跑）。

运行条件：LIVE_SMOKE=1 且处于交易时段（真实行情源可用）。
"""

from __future__ import annotations

import os
import time


def main() -> None:
    if os.environ.get("LIVE_SMOKE") != "1":
        raise SystemExit("LIVE_SMOKE=1 required")
    from .adapters import AkshareOneMinuteFeed, warmup_engine
    from .engine import PatimingEngine

    symbol = os.environ.get("LIVE_SMOKE_SYMBOL", "RB0")
    exchange = os.environ.get("LIVE_SMOKE_EXCHANGE", "SHFE")
    rounds = int(os.environ.get("LIVE_SMOKE_ROUNDS", "6"))
    engine = PatimingEngine(os.environ.get("PATIMING_DB", "live_smoke.db"))
    engine.register_delivery_handler(
        lambda event: print("[ALERT]", event["event_type"],
                            event["payload"]["signal_id"],
                            event["payload"]["lifecycle"]))
    engine.start()
    feed = AkshareOneMinuteFeed()
    warmup_engine(engine, feed.fetch_1m(symbol, exchange))
    engine.submit_instruction("strategy:live_smoke", {
        "instruction_id": "LIVE-SMOKE-1",
        "producer_revision": 1,
        "symbol": f"{symbol}.{exchange}",
        "selection_timeframe": "1m",
        "exec_timeframe": "1m",
        "reason_code": "BREAKOUT_WATCH",
        "reason_note": "live smoke rolling breakout",
        "signal_categories": ["breakout"],
    })
    for _ in range(rounds):
        time.sleep(30)
        for bar in feed.fetch_1m(symbol, exchange)[-2:]:
            engine.on_1m_bar(bar)
        engine.reconcile()
    engine.close()


if __name__ == "__main__":
    main()
