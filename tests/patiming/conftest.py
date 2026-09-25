from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from vnpy.trader.constant import Exchange
from vnpy.trader.object import BarData

from vnpy_patiming import PatimingEngine

BASE = datetime(2026, 9, 21, 9, 0)  # Monday 09:00, exchange-local naive


class ManualClock:
    def __init__(self, start: datetime = BASE) -> None:
        self.now = start

    def advance(self, minutes: float = 1) -> datetime:
        self.now += timedelta(minutes=minutes)
        return self.now

    def __call__(self) -> datetime:
        return self.now


def make_engine(tmp_path, clock: ManualClock, data_mode: str = "ctp_tick", **overrides):
    cfg = {
        "atr_period": 5,
        "ema_period": 5,
        "warmup_min_exec": 8,
        "price_tick": 0.2,
        "buffer_ticks": 2,
        # permissive quality gate by default; boundary tests override back
        "min_stop_atr": 0.05,
        "max_stop_atr": 50.0,
        "bar_min_atr": 0.05,
        "bar_max_atr": 50.0,
        "overlap_max": 1.0,
    }
    cfg.update(overrides)
    db = os.path.join(str(tmp_path), "patiming.db")
    return PatimingEngine(db, cfg, clock=clock, data_mode=data_mode)


def make_bar(dt: datetime, o: float, h: float, l: float, c: float,
             symbol: str = "rb2501", interval=None) -> BarData:
    return BarData(
        symbol=symbol, exchange=Exchange.SHFE, datetime=dt, gateway_name="SIM",
        open_price=o, high_price=h, low_price=l, close_price=c, interval=interval,
    )


def submit_ok(engine: PatimingEngine, source: str = "strategy:demo",
              iid: str = "INS-1", rev: int = 1, **kw) -> dict:
    payload = {
        "instruction_id": iid,
        "producer_revision": rev,
        "symbol": kw.pop("symbol", "rb2501.SHFE"),
        "selection_timeframe": kw.pop("selection_timeframe", "1m"),
        "exec_timeframe": kw.pop("exec_timeframe", "1m"),
        "context_tag": kw.pop("context_tag", "breakout"),
        "signal_categories": kw.pop("signal_categories", ["breakout"]),
        "key_levels": kw.pop("key_levels", {"prior_high": 100.0}),
        "reason_code": kw.pop("reason_code", "BREAKOUT_WATCH"),
        "reason_note": kw.pop("reason_note", "unit test"),
    }
    payload.update(kw)
    result = engine.submit_instruction(source, payload)
    assert result["ok"], result
    engine.reconcile()
    return result


def feed_bars(engine: PatimingEngine, clock: ManualClock, n: int,
              o=99.0, h=99.6, l=98.6, c=99.2) -> None:
    for _ in range(n):
        dt = clock.advance(1)
        engine.on_1m_bar(make_bar(dt, o, h, l, c))


def flush_window(engine: PatimingEngine, clock: ManualClock) -> None:
    """Complete the just-fed bar via the wall-clock fallback (spec 4.2)."""
    clock.advance(1)
    engine.flush_due(clock())


def alert_events(engine: PatimingEngine, alert_id: str | None = None) -> list[dict]:
    if alert_id is None:
        return engine.db.query("SELECT * FROM timing_alert_event ORDER BY id")
    return engine.db.query(
        "SELECT * FROM timing_alert_event WHERE alert_id=? ORDER BY id", (alert_id,)
    )


@pytest.fixture()
def clock() -> ManualClock:
    return ManualClock()
