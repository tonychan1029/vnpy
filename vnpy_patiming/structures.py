"""Point-in-time primitives: ATR, EMA, pivots, overlap, level manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from vnpy.trader.object import BarData


class ATR:
    """Wilder ATR; value available after `period` bars."""

    def __init__(self, period: int) -> None:
        self.period = period
        self.value: float | None = None
        self._prev_close: float | None = None
        self._trs: list[float] = []

    def update(self, bar: BarData) -> float | None:
        if self._prev_close is None:
            tr = bar.high_price - bar.low_price
        else:
            tr = max(
                bar.high_price - bar.low_price,
                abs(bar.high_price - self._prev_close),
                abs(bar.low_price - self._prev_close),
            )
        self._prev_close = bar.close_price
        self._trs.append(tr)
        if self.value is None:
            if len(self._trs) >= self.period:
                self.value = sum(self._trs) / self.period
        else:
            self.value = (self.value * (self.period - 1) + tr) / self.period
        return self.value


class EMA:
    def __init__(self, period: int) -> None:
        self.period = period
        self.alpha = 2.0 / (period + 1)
        self.value: float | None = None
        self.history: list[float] = []
        self._closes: list[float] = []

    def update(self, price: float) -> float | None:
        self._closes.append(price)
        if self.value is None:
            if len(self._closes) >= self.period:
                self.value = sum(self._closes[-self.period :]) / self.period
                self.history.append(self.value)
            return None
        self.value = price * self.alpha + self.value * (1 - self.alpha)
        self.history.append(self.value)
        return self.value

    def slope(self, lookback: int = 5) -> float:
        """EMA direction proxy for trend-side gating (trend_strong 只顺势)."""
        if len(self.history) <= lookback:
            return 0.0
        return self.history[-1] - self.history[-1 - lookback]

    def finalize_seed(self, prices: list[float]) -> None:
        """Seed with an SMA once `period` prices accumulated (call via runtime)."""
        if self.value is None and len(prices) >= self.period:
            self.value = sum(prices[-self.period :]) / self.period


@dataclass
class Pivot:
    kind: str          # "H" or "L"
    price: float
    pivot_bar_time: datetime
    confirmed_bar_time: datetime


class PivotDetector:
    """Fractal pivots confirmed k bars later (point-in-time, spec 6.2)."""

    def __init__(self, k: int) -> None:
        self.k = k
        self._bars: list[BarData] = []
        self.confirmed: list[Pivot] = []

    def update(self, bar: BarData) -> list[Pivot]:
        """Call on bar close; returns pivots confirmed by this close."""
        self._bars.append(bar)
        out: list[Pivot] = []
        i = len(self._bars) - 1 - self.k
        if i < self.k:
            return out
        cand = self._bars[i]
        left = self._bars[i - self.k : i]
        right = self._bars[i + 1 : i + 1 + self.k]
        if len(right) < self.k:
            return out
        if all(cand.high_price > b.high_price for b in left) and all(
            cand.high_price > b.high_price for b in right
        ):
            out.append(Pivot("H", cand.high_price, cand.datetime, bar.datetime))
        if all(cand.low_price < b.low_price for b in left) and all(
            cand.low_price < b.low_price for b in right
        ):
            out.append(Pivot("L", cand.low_price, cand.datetime, bar.datetime))
        self.confirmed.extend(out)
        return out

    def last(self, kind: str) -> Pivot | None:
        for p in reversed(self.confirmed):
            if p.kind == kind:
                return p
        return None


def body_ratio(bar: BarData) -> float:
    rng = bar.high_price - bar.low_price
    if rng <= 0:
        return 0.0
    return abs(bar.close_price - bar.open_price) / rng


def bar_length(bar: BarData) -> float:
    return bar.high_price - bar.low_price


def overlap_mean(bars: list[BarData], window: int) -> float:
    """Mean neighbor overlap ratio over the last `window` bars."""
    if len(bars) < 2:
        return 0.0
    ratios: list[float] = []
    pairs = list(zip(bars[-window - 1 :], bars[-window:]))
    for a, b in pairs:
        lo = max(a.low_price, b.low_price)
        hi = min(a.high_price, b.high_price)
        rng = max(a.high_price, b.high_price) - min(a.low_price, b.low_price)
        if rng <= 0:
            continue
        ratios.append(max(hi - lo, 0.0) / rng)
    if not ratios:
        return 0.0
    return sum(ratios) / len(ratios)


@dataclass
class LevelState:
    kind: str          # prior_high / prior_low / range_top / range_bottom / gap_edge
    price: float
    status: str = "fresh"   # fresh / tested / broken
    meta: dict = field(default_factory=dict)


LEVEL_BREAK_SIDE = {
    "prior_high": "up",
    "range_top": "up",
    "gap_edge": "down",   # gap edge breaks when price falls back through it
    "prior_low": "down",
    "range_bottom": "down",
}


class LevelManager:
    """Single source of truth for level validity (spec 6.2 item 2)."""

    def __init__(self) -> None:
        self.levels: list[LevelState] = []

    def seed_from_instruction(self, key_levels: dict | None) -> None:
        if not key_levels:
            return
        for kind, price in key_levels.items():
            if price is None:
                continue
            self.add(kind, float(price))

    def add(self, kind: str, price: float, meta: dict | None = None) -> LevelState:
        lvl = LevelState(kind=kind, price=float(price), meta=meta or {})
        self.levels.append(lvl)
        return lvl

    def by_kind(self, *kinds: str, statuses: tuple[str, ...] = ("fresh", "tested")) -> list[LevelState]:
        return [
            lv
            for lv in self.levels
            if lv.kind in kinds and lv.status in statuses
        ]

    def on_bar_close(self, bar: BarData, atr: float | None, touch_atr: float) -> None:
        """Touch marks tested; confirmed close-through marks broken (spec 6.2)."""
        tol = touch_atr * atr if atr else 0.0
        for lv in self.levels:
            if lv.status == "broken":
                continue
            side = LEVEL_BREAK_SIDE.get(lv.kind)
            if side == "up" and bar.close_price > lv.price:
                lv.status = "broken"
            elif side == "down" and bar.close_price < lv.price:
                lv.status = "broken"
            elif bar.low_price - tol <= lv.price <= bar.high_price + tol:
                if lv.status == "fresh":
                    lv.status = "tested"
