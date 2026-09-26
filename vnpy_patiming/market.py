"""1m-driven bar synthesis with session-end wall-clock fallback (spec 4.2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from vnpy.trader.object import BarData

from .config import TIMEFRAME_MINUTES

EPOCH = datetime(1970, 1, 1)

UPPER_EXCHANGES = {"CZCE", "CFFEX", "GFEX"}


def canonical_symbol(base: str, exchange: str) -> str:
    """vnpy 惯例：SHFE/DCE/INE 小写基础代码，CZCE/CFFEX/GFEX 大写。"""
    base = base.strip()
    exch = exchange.strip().upper()
    return base if exch in UPPER_EXCHANGES else base.lower()


def window_index(dt: datetime, interval_minutes: int) -> int:
    return int((dt - EPOCH).total_seconds()) // (interval_minutes * 60)


def window_open(idx: int, interval_minutes: int) -> datetime:
    return EPOCH + timedelta(minutes=idx * interval_minutes)


class BarSynthesizer:
    """Synthesizes an N-minute bar from 1m bars.

    A window completes when the first 1m bar of a later window arrives
    (primary rule) or when its wall-clock end passes with data inside
    (session-end fallback). Windows without data produce no bar.
    """

    def __init__(self, timeframe: str) -> None:
        self.timeframe = timeframe
        self.interval = TIMEFRAME_MINUTES[timeframe]
        self._idx: int | None = None
        self._o = self._h = self._l = self._c = 0.0
        self._count = 0
        self._symbol = ""
        self._exchange = None

    def update(self, bar: BarData) -> BarData | None:
        idx = window_index(bar.datetime, self.interval)
        completed = None
        if self._idx is not None and idx != self._idx:
            completed = self._build()
        if self._idx is None or completed is not None:
            self._idx = idx
            self._symbol, self._exchange = bar.symbol, bar.exchange
            self._o, self._h = bar.open_price, bar.high_price
            self._l, self._c = bar.low_price, bar.close_price
            self._count = 1
        else:
            self._h = max(self._h, bar.high_price)
            self._l = min(self._l, bar.low_price)
            self._c = bar.close_price
            self._count += 1
        return completed

    def flush(self, now: datetime) -> BarData | None:
        """Complete the in-progress window if its wall-clock end has passed."""
        if self._idx is None or self._count == 0:
            return None
        end = window_open(self._idx, self.interval) + timedelta(minutes=self.interval)
        if now >= end:
            return self._build()
        return None

    def _build(self) -> BarData:
        bar = BarData(
            symbol=self._symbol,
            exchange=self._exchange,
            datetime=window_open(self._idx or 0, self.interval),
            gateway_name="PATIMING",
        )
        bar.open_price, bar.high_price = self._o, self._h
        bar.low_price, bar.close_price = self._l, self._c
        bar.volume = self._count
        self._idx, self._count = None, 0
        return bar


class MarketClock:
    """Per-symbol synthesis registry: exec and selection timeframes."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.synths: dict[str, BarSynthesizer] = {}
        self.last_seen: datetime | None = None

    def register(self, timeframe: str) -> BarSynthesizer:
        if timeframe not in self.synths:
            self.synths[timeframe] = BarSynthesizer(timeframe)
        return self.synths[timeframe]

    def on_1m(self, bar: BarData) -> dict[str, BarData]:
        """Feed one 1m bar; returns {timeframe: completed_bar} for closed windows."""
        self.last_seen = bar.datetime
        completed: dict[str, BarData] = {}
        for tf, synth in self.synths.items():
            done = synth.update(bar)
            if done is not None:
                completed[tf] = done
        return completed

    def flush_due(self, now: datetime) -> dict[str, BarData]:
        completed: dict[str, BarData] = {}
        for tf, synth in self.synths.items():
            done = synth.flush(now)
            if done is not None:
                completed[tf] = done
        return completed
