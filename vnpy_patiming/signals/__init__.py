"""Phase-1 detector registry (spec 6.3): signals 1/2/3/4/5-simple/10."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vnpy.trader.object import BarData

from ..structures import LevelManager, PivotDetector

SIGNAL_CATEGORIES = {
    "breakout",
    "fake_breakout",
    "second_breakout",
    "ema_pullback",
    "structure_pullback",
    "range_edge",
}


@dataclass
class FakeBreakEvent:
    side: str            # "top" poked above, "bottom" broke below
    level_kind: str
    level_price: float
    bar_time: Any
    extreme: float


@dataclass
class AlertDraft:
    category: str
    signal_id: str
    family: str
    rank: int
    order_type: str
    direction: str
    trigger: dict
    stop: dict
    invalidation: dict
    note: str = ""
    instruction_keys: set = field(default_factory=set)


class SignalContext:
    """Read-only view over one monitoring task's closed-bar state."""

    def __init__(
        self,
        bars: list[BarData],
        atr: float | None,
        ema: Any,
        pivots: PivotDetector,
        levels: LevelManager,
        cfg: dict,
        direction: str,
        context_tag: str,
        now: Any,
        price_tick: float,
        fake_log: list[FakeBreakEvent],
        invalid_log: list | None = None,
    ) -> None:
        self.bars = bars
        self.atr = atr or 0.0
        self.ema = ema
        self.pivots = pivots
        self.levels = levels
        self.cfg = cfg
        self.direction = direction
        self.context_tag = context_tag
        self.now = now
        self.price_tick = price_tick
        self.fake_log = fake_log
        self.invalid_log = invalid_log if invalid_log is not None else []

    @property
    def bar(self) -> BarData:
        return self.bars[-1]

    @property
    def prev(self) -> BarData | None:
        return self.bars[-2] if len(self.bars) >= 2 else None

    def ema_slope(self) -> float:
        return self.ema.slope()

    def buffer(self) -> float:
        return self.cfg["buffer_ticks"] * self.price_tick

    def allowed(self, direction: str) -> bool:
        """Instruction direction + trend-side gate (trend_strong 只顺势)."""
        if self.direction not in ("both", direction):
            return False
        if self.context_tag == "trend_strong":
            slope = self.ema_slope()
            if slope > 0:
                return direction == "long"
            if slope < 0:
                return direction == "short"
            return False
        return True


class BaseDetector:
    category: str = ""
    signal_id: str = ""
    family: str = ""
    rank: int = 0
    order_type: str = "stop"

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        raise NotImplementedError


def targets_for(entry: float, stop: float, direction: str) -> dict:
    risk = abs(entry - stop)
    sign = 1.0 if direction == "long" else -1.0
    return {
        "t1": {"price": round(entry + sign * risk, 6), "ref": "risk_multiple:1.0R"},
        "t2": {"price": round(entry + sign * 2.0 * risk, 6), "ref": "risk_multiple:2.0R"},
    }


def passes_quality(ctx: SignalContext, draft: AlertDraft) -> bool:
    from ..structures import bar_length, overlap_mean

    cfg = ctx.cfg
    if ctx.atr <= 0:
        return False
    if not (cfg["bar_min_atr"] * ctx.atr <= bar_length(ctx.bar) <= cfg["bar_max_atr"] * ctx.atr):
        return False
    stop_dist = abs(draft.trigger["level"] - draft.stop["level"])
    if stop_dist < cfg["min_stop_atr"] * ctx.atr:
        return False
    if stop_dist > cfg["max_stop_atr"] * ctx.atr:
        return False
    if overlap_mean(ctx.bars, cfg["overlap_window"]) > cfg["overlap_max"]:
        return False
    return True
