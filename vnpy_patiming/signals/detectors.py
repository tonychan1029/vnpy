"""Deterministic implementations of phase-1 signal rules (spec 6.3/6.4)."""

from __future__ import annotations

import datetime as _dt

from ..structures import body_ratio
from . import AlertDraft, BaseDetector, FakeBreakEvent, SignalContext


EPS = 1e-9


def _mk_draft(
    det: BaseDetector,
    ctx: SignalContext,
    direction: str,
    trigger_type: str,
    trigger: float,
    trigger_ref: str,
    stop: float,
    stop_ref: str,
    invalid: tuple,
) -> AlertDraft:
    return AlertDraft(
        category=det.category,
        signal_id=det.signal_id,
        family=det.family,
        rank=det.rank,
        order_type=det.order_type,
        direction=direction,
        trigger={
            "type": trigger_type,
            "level": round(trigger, 6),
            "ref": trigger_ref,
            "buffer_ticks": ctx.cfg["buffer_ticks"],
        },
        stop={"level": round(stop, 6), "ref": stop_ref},
        invalidation={"type": invalid[0], "level": invalid[1]},
    )


class BreakoutDetector(BaseDetector):
    category = "breakout"
    signal_id = "BREAKOUT_KEY_LEVEL"
    family = "breakout"
    rank = 30

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        bar, atr = ctx.bar, ctx.atr
        out: list[AlertDraft] = []
        if body_ratio(bar) + EPS < ctx.cfg["breakout_body_min"]:
            return out
        for lv in ctx.levels.by_kind("prior_high", "prior_low"):
            long_side = lv.kind == "prior_high"
            direction = "long" if long_side else "short"
            move = bar.close_price - lv.price
            if long_side:
                ok = (
                    bar.close_price > lv.price
                    and bar.close_price > bar.open_price
                    and move + EPS >= ctx.cfg["breakout_min_atr"] * atr
                )
            else:
                ok = (
                    bar.close_price < lv.price
                    and bar.close_price < bar.open_price
                    and -move + EPS >= ctx.cfg["breakout_min_atr"] * atr
                )
            if not ok or not ctx.allowed(direction):
                continue
            buf = ctx.buffer()
            if long_side:
                trigger = bar.high_price + buf
                stop = min(bar.low_price, lv.price - ctx.cfg["level_touch_atr"] * atr)
                out.append(_mk_draft(self, ctx, direction, "cross_above", trigger,
                                     "signal_bar_high", stop, "key_level_offset",
                                     ("close_below", lv.price)))
            else:
                trigger = bar.low_price - buf
                stop = max(bar.high_price, lv.price + ctx.cfg["level_touch_atr"] * atr)
                out.append(_mk_draft(self, ctx, direction, "cross_below", trigger,
                                     "signal_bar_low", stop, "key_level_offset",
                                     ("close_above", lv.price)))
        return out


class FakeBreakoutDetector(BaseDetector):
    category = "fake_breakout"
    signal_id = "FAKE_BREAKOUT_REVERSE"
    family = "fake_breakout"
    rank = 25

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        bar, atr = ctx.bar, ctx.atr
        out: list[AlertDraft] = []
        poke = ctx.cfg["fake_poke_atr"] * atr
        for lv in ctx.levels.by_kind("prior_high", "prior_low", "range_top", "range_bottom"):
            top_side = lv.kind in ("prior_high", "range_top")
            if top_side:
                poked = bar.high_price >= lv.price + poke
                closed_back = bar.close_price < lv.price
            else:
                poked = bar.low_price <= lv.price - poke
                closed_back = bar.close_price > lv.price
            if not (poked and closed_back):
                continue
            direction = "short" if top_side else "long"
            extreme = bar.high_price if top_side else bar.low_price
            prev = ctx.prev
            if prev is not None:
                prev_poked = (
                    prev.high_price >= lv.price + poke
                    if top_side
                    else prev.low_price <= lv.price - poke
                )
            else:
                prev_poked = False
            ctx.fake_log.append(
                FakeBreakEvent(
                    side="top" if top_side else "bottom",
                    level_kind=lv.kind,
                    level_price=lv.price,
                    bar_time=bar.datetime,
                    extreme=extreme,
                )
            )
            if prev_poked:
                continue
            if not ctx.allowed(direction):
                continue
            buf = ctx.buffer()
            if top_side:
                trigger = bar.low_price - buf
                stop = bar.high_price + ctx.cfg["fake_stop_atr"] * atr
                out.append(_mk_draft(self, ctx, direction, "cross_below", trigger,
                                     "signal_bar_low", stop, "poke_extreme_offset",
                                     ("close_above", lv.price)))
            else:
                trigger = bar.high_price + buf
                stop = bar.low_price - ctx.cfg["fake_stop_atr"] * atr
                out.append(_mk_draft(self, ctx, direction, "cross_above", trigger,
                                     "signal_bar_high", stop, "poke_extreme_offset",
                                     ("close_below", lv.price)))
        return out


class SecondBreakoutDetector(BaseDetector):
    category = "second_breakout"
    signal_id = "SECOND_BREAKOUT"
    family = "second_breakout"
    rank = 28

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        bar, atr = ctx.bar, ctx.atr
        out: list[AlertDraft] = []
        if body_ratio(bar) + EPS < ctx.cfg["breakout_body_min"]:
            return out
        window = _dt.timedelta(minutes=ctx.cfg["second_breakout_window"])
        recent = [e for e in ctx.fake_log if ctx.now - e.bar_time <= window]
        if not recent:
            return out
        for lv in ctx.levels.by_kind("prior_high", "prior_low"):
            long_side = lv.kind == "prior_high"
            direction = "long" if long_side else "short"
            side = "top" if long_side else "bottom"
            if not any(e.side == side and e.level_price == lv.price for e in recent):
                continue
            move = bar.close_price - lv.price
            if long_side:
                ok = (
                    bar.close_price > lv.price
                    and move + EPS >= ctx.cfg["breakout_min_atr"] * atr
                )
            else:
                ok = (
                    bar.close_price < lv.price
                    and -move + EPS >= ctx.cfg["breakout_min_atr"] * atr
                )
            if not ok or not ctx.allowed(direction):
                continue
            buf = ctx.buffer()
            if long_side:
                trigger = bar.high_price + buf
                stop = min(bar.low_price, lv.price - ctx.cfg["level_touch_atr"] * atr)
                out.append(_mk_draft(self, ctx, direction, "cross_above", trigger,
                                     "signal_bar_high", stop, "key_level_offset",
                                     ("close_below", lv.price)))
            else:
                trigger = bar.low_price - buf
                stop = max(bar.high_price, lv.price + ctx.cfg["level_touch_atr"] * atr)
                out.append(_mk_draft(self, ctx, direction, "cross_below", trigger,
                                     "signal_bar_low", stop, "key_level_offset",
                                     ("close_above", lv.price)))
        return out


class EmaPullbackDetector(BaseDetector):
    category = "ema_pullback"
    signal_id = "EMA20_PULLBACK"
    family = "ema_pullback"
    rank = 20
    order_type = "limit"

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        bar, atr = ctx.bar, ctx.atr
        out: list[AlertDraft] = []
        if ctx.context_tag not in ("trend_strong", "trend_channel"):
            return out
        ema = ctx.ema.value
        if ema is None:
            return out
        tol = ctx.cfg["level_touch_atr"] * atr
        touches = bar.low_price <= ema <= bar.high_price or abs(bar.close_price - ema) <= tol
        if not touches:
            return out
        slope = ctx.ema_slope()
        direction = "long" if slope > 0 else "short"
        if not ctx.allowed(direction):
            return out
        pivot = ctx.pivots.last("L" if direction == "long" else "H")
        if pivot is None:
            return out
        buf = ctx.buffer()
        if direction == "long":
            stop = pivot.price - ctx.cfg["level_touch_atr"] * atr
            level = ema - buf
            if ema - stop > ctx.cfg["max_stop_atr"] * atr:
                return out
            invalid = ("close_below", pivot.price)
            trig_type = "touch_below"
        else:
            stop = pivot.price + ctx.cfg["level_touch_atr"] * atr
            level = ema + buf
            if stop - ema > ctx.cfg["max_stop_atr"] * atr:
                return out
            invalid = ("close_above", pivot.price)
            trig_type = "touch_above"
        out.append(_mk_draft(self, ctx, direction, trig_type, level,
                             "ema_frozen", stop, "pivot_point", invalid))
        return out


class StructurePullbackDetector(BaseDetector):
    category = "structure_pullback"
    signal_id = "STRUCTURE_PULLBACK"
    family = "structure_pullback"
    rank = 22
    order_type = "limit"

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        bar, atr = ctx.bar, ctx.atr
        out: list[AlertDraft] = []
        tol = ctx.cfg["level_touch_atr"] * atr
        for lv in ctx.levels.by_kind("prior_low", "prior_high", "gap_edge"):
            long_side = lv.kind in ("prior_low", "gap_edge")
            direction = "long" if long_side else "short"
            touched = bar.low_price <= lv.price + tol if long_side else bar.high_price >= lv.price - tol
            held = bar.close_price >= lv.price if long_side else bar.close_price <= lv.price
            if not (touched and held) or not ctx.allowed(direction):
                continue
            buf = ctx.buffer()
            ref = f"level:{lv.kind}"
            if long_side:
                level = lv.price + buf
                stop = lv.price - ctx.cfg["level_touch_atr"] * atr
                out.append(_mk_draft(self, ctx, direction, "touch_below", level,
                                     ref, stop, ref, ("close_below", lv.price)))
            else:
                level = lv.price - buf
                stop = lv.price + ctx.cfg["level_touch_atr"] * atr
                out.append(_mk_draft(self, ctx, direction, "touch_above", level,
                                     ref, stop, ref, ("close_above", lv.price)))
        return out


class RangeEdgeDetector(BaseDetector):
    category = "range_edge"
    signal_id = "RANGE_EDGE_REVERSAL"
    family = "range_edge"
    rank = 15

    @staticmethod
    def _pin(bar, bull: bool) -> bool:
        body = abs(bar.close_price - bar.open_price)
        rng = bar.high_price - bar.low_price
        if rng <= 0 or body <= 0:
            return False
        lower_wick = min(bar.open_price, bar.close_price) - bar.low_price
        upper_wick = bar.high_price - max(bar.open_price, bar.close_price)
        if bull:
            outer = bar.close_price >= bar.low_price + rng / 3
            return lower_wick >= 2 * body and outer
        outer = bar.close_price <= bar.high_price - rng / 3
        return upper_wick >= 2 * body and outer

    @staticmethod
    def _engulf(bar, prev, bull: bool) -> bool:
        if prev is None:
            return False
        prev_bull = prev.close_price > prev.open_price
        if bull == prev_bull:
            return False
        cur_lo = min(bar.open_price, bar.close_price)
        cur_hi = max(bar.open_price, bar.close_price)
        prev_lo = min(prev.open_price, prev.close_price)
        prev_hi = max(prev.open_price, prev.close_price)
        return cur_lo <= prev_lo and cur_hi >= prev_hi

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        bar, atr = ctx.bar, ctx.atr
        out: list[AlertDraft] = []
        if ctx.context_tag != "range":
            return out
        tol = ctx.cfg["level_touch_atr"] * atr
        buf = ctx.buffer()
        for bottom in ctx.levels.by_kind("range_bottom"):
            touched = bar.low_price <= bottom.price + tol
            reversal = self._pin(bar, True) or self._engulf(bar, ctx.prev, True)
            if touched and reversal and ctx.allowed("long"):
                out.append(_mk_draft(
                    self, ctx, "long", "cross_above", bar.high_price + buf,
                    "signal_bar_high", bar.low_price - ctx.cfg["level_touch_atr"] * atr,
                    "range_edge_offset", ("close_below", bottom.price)))
                break
        for top in ctx.levels.by_kind("range_top"):
            touched = bar.high_price >= top.price - tol
            reversal = self._pin(bar, False) or self._engulf(bar, ctx.prev, False)
            if touched and reversal and ctx.allowed("short"):
                out.append(_mk_draft(
                    self, ctx, "short", "cross_below", bar.low_price - buf,
                    "signal_bar_low", bar.high_price + ctx.cfg["level_touch_atr"] * atr,
                    "range_edge_offset", ("close_above", top.price)))
                break
        return out


class HighTwoLowTwoDetector(BaseDetector):
    """高2/低2（spec 6.3 #6）：趋势背景内相邻摆动点二次回调，trailing 突破单。"""

    category = "h2_l2"
    signal_id = "H2L2_TREND"
    family = "h2_l2"
    rank = 26

    @staticmethod
    def _bar_index(ctx: SignalContext) -> dict:
        return {b.datetime: i for i, b in enumerate(ctx.bars)}

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        out: list[AlertDraft] = []
        if ctx.context_tag not in ("trend_strong", "trend_channel"):
            return out
        ema, atr = ctx.ema.value, ctx.atr
        if ema is None:
            return out
        lows = [p for p in ctx.pivots.confirmed if p.kind == "L"]
        highs = [p for p in ctx.pivots.confirmed if p.kind == "H"]
        index = self._bar_index(ctx)
        window = ctx.cfg["h2_window_bars"]
        buf = ctx.buffer()
        slope = ctx.ema_slope()

        if len(lows) >= 2 and slope > 0:
            l2, l1 = lows[-1], lows[-2]
            gap = self._bar_gap(index, l1.pivot_bar_time, l2.pivot_bar_time)
            recent = self._recent(index, l2.pivot_bar_time, ctx)
            mid_high = any(
                p.kind == "H" and l1.pivot_bar_time <= p.pivot_bar_time <= l2.pivot_bar_time
                for p in ctx.pivots.confirmed
            )
            if (
                gap is not None and recent is not None
                and gap <= window and recent <= window
                and mid_high
                and l2.price >= l1.price - 0.1 * atr
                and min(l1.price, l2.price) >= ema
                and ctx.allowed("long")
            ):
                out.append(_mk_draft(self, ctx, "long", "cross_above",
                                     ctx.bar.high_price + buf, "signal_bar_high",
                                     l2.price, "pivot_point",
                                     ("close_below", l2.price)))
        if len(highs) >= 2 and slope < 0:
            h2, h1 = highs[-1], highs[-2]
            gap = self._bar_gap(index, h1.pivot_bar_time, h2.pivot_bar_time)
            recent = self._recent(index, h2.pivot_bar_time, ctx)
            mid_low = any(
                p.kind == "L" and h1.pivot_bar_time <= p.pivot_bar_time <= h2.pivot_bar_time
                for p in ctx.pivots.confirmed
            )
            if (
                gap is not None and recent is not None
                and gap <= window and recent <= window
                and mid_low
                and h2.price <= h1.price + 0.1 * atr
                and max(h1.price, h2.price) <= ema
                and ctx.allowed("short")
            ):
                out.append(_mk_draft(self, ctx, "short", "cross_below",
                                     ctx.bar.low_price - buf, "signal_bar_low",
                                     h2.price, "pivot_point",
                                     ("close_above", h2.price)))
        return out

    @staticmethod
    def _bar_gap(index: dict, t1, t2):
        a, b = index.get(t1), index.get(t2)
        if a is None or b is None:
            return None
        return abs(b - a)

    @staticmethod
    def _recent(index: dict, t, ctx: SignalContext):
        i = index.get(t)
        if i is None:
            return None
        return len(ctx.bars) - 1 - i


class DoubleTopBottomDetector(BaseDetector):
    """双顶/双底（spec 6.3 #7）：摆动点聚类 + 颈线方向突破单。"""

    category = "double_top_bottom"
    signal_id = "DOUBLE_TOP_BOTTOM"
    family = "double_top_bottom"
    rank = 18

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        out: list[AlertDraft] = []
        if ctx.context_tag not in ("range", "reversal"):
            return out
        atr = ctx.atr
        tol = ctx.cfg["dbl_tol_atr"] * atr
        index = self._bar_index(ctx)
        highs = [p for p in ctx.pivots.confirmed if p.kind == "H"]
        lows = [p for p in ctx.pivots.confirmed if p.kind == "L"]
        buf = ctx.buffer()

        if len(highs) >= 2:
            p2, p1 = highs[-1], highs[-2]
            sep = self._sep(ctx, p1.pivot_bar_time, p2.pivot_bar_time)
            if (sep is not None and 3 <= sep <= ctx.cfg["dbl_max_sep_bars"]
                    and abs(p2.price - p1.price) <= tol):
                failure = ctx.bar.close_price < p2.price or (
                    RangeEdgeDetector._pin(ctx.bar, False)
                    or RangeEdgeDetector._engulf(ctx.bar, ctx.prev, False))
                if failure and ctx.allowed("short"):
                    top = max(p1.price, p2.price)
                    d = _mk_draft(self, ctx, "short", "cross_below",
                                  ctx.bar.low_price - buf, "signal_bar_low",
                                  top + 0.25 * atr, "double_top_offset",
                                  ("close_above", top))
                    d.signal_id = "DOUBLE_TOP"
                    out.append(d)

        if len(lows) >= 2:
            p2, p1 = lows[-1], lows[-2]
            sep = self._sep(ctx, p1.pivot_bar_time, p2.pivot_bar_time)
            if (sep is not None and 3 <= sep <= ctx.cfg["dbl_max_sep_bars"]
                    and abs(p2.price - p1.price) <= tol):
                failure = ctx.bar.close_price > p2.price or (
                    RangeEdgeDetector._pin(ctx.bar, True)
                    or RangeEdgeDetector._engulf(ctx.bar, ctx.prev, True))
                if failure and ctx.allowed("long"):
                    bottom = min(p1.price, p2.price)
                    d = _mk_draft(self, ctx, "long", "cross_above",
                                  ctx.bar.high_price + buf, "signal_bar_high",
                                  bottom - 0.25 * atr, "double_bottom_offset",
                                  ("close_below", bottom))
                    d.signal_id = "DOUBLE_BOTTOM"
                    out.append(d)
        return out

    @staticmethod
    def _bar_index(ctx: SignalContext) -> dict:
        return {b.datetime: i for i, b in enumerate(ctx.bars)}

    @staticmethod
    def _sep(ctx: SignalContext, t1, t2):
        index = DoubleTopBottomDetector._bar_index(ctx)
        a, b = index.get(t1), index.get(t2)
        if a is None or b is None:
            return None
        return abs(b - a)


DETECTOR_CLASSES = [
    BreakoutDetector,
    FakeBreakoutDetector,
    SecondBreakoutDetector,
    EmaPullbackDetector,
    StructurePullbackDetector,
    RangeEdgeDetector,
    HighTwoLowTwoDetector,
    DoubleTopBottomDetector,
]


def build_detectors() -> list[BaseDetector]:
    return [cls() for cls in DETECTOR_CLASSES]
