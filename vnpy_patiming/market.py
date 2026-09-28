"""1m-driven bar synthesis with session-end wall-clock fallback (spec 4.2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from vnpy.trader.object import BarData

from .config import TIMEFRAME_MINUTES

EPOCH = datetime(1970, 1, 1)

UPPER_EXCHANGES = {"CZCE", "CFFEX", "GFEX"}

DAY_SESSIONS = ((9 * 60, 10 * 60 + 15),
                (10 * 60 + 30, 11 * 60 + 30),
                (13 * 60 + 30, 15 * 60))
CFFEX_SESSIONS = ((9 * 60 + 30, 11 * 60 + 30),
                  (13 * 60, 15 * 60))
NIGHT_TO_0100 = {"CU", "AL", "ZN", "PB", "NI", "SN", "SS", "AO"}
NIGHT_TO_0230 = {"AU", "AG", "SC", "LU", "NR", "BC"}


def canonical_symbol(base: str, exchange: str) -> str:
    """vnpy 惯例：SHFE/DCE/INE 小写基础代码，CZCE/CFFEX/GFEX 大写。"""
    base = base.strip()
    exch = exchange.strip().upper()
    return base if exch in UPPER_EXCHANGES else base.lower()


def window_index(dt: datetime, interval_minutes: int) -> int:
    return int((dt - EPOCH).total_seconds()) // (interval_minutes * 60)


def window_open(idx: int, interval_minutes: int) -> datetime:
    return EPOCH + timedelta(minutes=idx * interval_minutes)


def _exchange(value: str) -> str:
    return str(value or "").strip().upper()


def _product(symbol: str) -> str:
    return "".join(ch for ch in str(symbol or "").upper() if ch.isalpha())


def _minute_abs(day: datetime.date, minute_of_day: int) -> int:
    base = datetime.combine(day, datetime.min.time())
    return int((base - EPOCH).total_seconds() // 60) + minute_of_day


def _session_windows(day: datetime.date, exchange: str,
                     product: str) -> list[tuple[int, int]]:
    if exchange == "CFFEX":
        windows = list(CFFEX_SESSIONS)
    else:
        windows = list(DAY_SESSIONS)
        if product in NIGHT_TO_0230:
            windows.append((21 * 60, 26 * 60 + 30))
        elif product in NIGHT_TO_0100:
            windows.append((21 * 60, 25 * 60))
        elif exchange != "CFFEX":
            windows.append((21 * 60, 23 * 60))
    return [(_minute_abs(day, start), _minute_abs(day, end))
            for start, end in windows]


def trading_minutes_between(start: datetime, end: datetime, exchange: str,
                            symbol: str = "") -> float:
    """Elapsed tradable minutes, excluding known intraday/night breaks.

    The built-in table covers regular Chinese futures sessions. Holidays are
    intentionally left to the data-health gate: a closed holiday has no quote,
    so it surfaces as a data-source problem rather than being silently assumed.
    """
    if end <= start:
        return 0.0
    start_s = int((start - EPOCH).total_seconds())
    end_s = int((end - EPOCH).total_seconds())
    exchange_name = _exchange(exchange)
    product = _product(symbol)
    elapsed = 0.0
    day = start.date() - timedelta(days=1)
    last_day = end.date()
    while day <= last_day:
        if day.weekday() < 5:
            for window_start, window_end in _session_windows(
                    day, exchange_name, product):
                overlap_start = max(start_s, window_start * 60)
                overlap_end = min(end_s, window_end * 60)
                if overlap_end > overlap_start:
                    elapsed += (overlap_end - overlap_start) / 60
        day += timedelta(days=1)
    return elapsed


def is_trading_time(value: datetime, exchange: str, symbol: str = "") -> bool:
    return trading_minutes_between(
        value, value + timedelta(seconds=1), exchange, symbol
    ) > 0


def is_session_start(value: datetime, exchange: str, symbol: str = "") -> bool:
    value_s = int((value - EPOCH).total_seconds())
    exchange_name = _exchange(exchange)
    day = value.date()
    product = _product(symbol)
    return any(start * 60 == value_s
               for start, _end in _session_windows(day, exchange_name, product))


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
