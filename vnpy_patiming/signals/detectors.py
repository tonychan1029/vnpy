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
    order_type = "stop"

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        bar, atr = ctx.bar, ctx.atr
        out: list[AlertDraft] = []
        tol = ctx.cfg["level_touch_atr"] * atr
        window = ctx.cfg["pb_retest_window"]
        cooldown = ctx.cfg["pb_cooldown_bars"]
        for lv in ctx.levels.by_kind("prior_low", "prior_high", "gap_edge"):
            long_side = lv.kind in ("prior_low", "gap_edge")
            direction = "long" if long_side else "short"
            if not ctx.allowed(direction):
                continue
            # 冷却：该位最近失效后 pb_cooldown_bars 根内不再武装（PK R3 共识）
            recent = [e for e in ctx.invalid_log
                      if e.get("level") == lv.price
                      and ctx.now - e["bar_time"] <= _dt.timedelta(minutes=cooldown)]
            if recent:
                continue
            touched = bar.low_price <= lv.price + tol if long_side else bar.high_price >= lv.price - tol
            held = bar.close_price >= lv.price if long_side else bar.close_price <= lv.price
            confirmed = held and bar.close_price >= (bar.high_price + bar.low_price) / 2
            if not (lv.status == "tested" and touched and confirmed):
                continue
            buf = ctx.buffer()
            ref = f"level:{lv.kind}"
            if long_side:
                retest_low = bar.low_price
                out.append(_mk_draft(self, ctx, direction, "cross_above",
                                     bar.high_price + buf, "confirm_bar_high",
                                     retest_low - 0.25 * atr, f"retest_low:{lv.kind}",
                                     ("close_below", retest_low)))
            else:
                retest_high = bar.high_price
                out.append(_mk_draft(self, ctx, direction, "cross_below",
                                     bar.low_price - buf, "confirm_bar_low",
                                     retest_high + 0.25 * atr, f"retest_high:{lv.kind}",
                                     ("close_above", retest_high)))
                ref = ref
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


class WedgeThreePushDetector(BaseDetector):
    """楔形三推（spec 6.3 #9，实验）：三推幅度递减 + 第三推动能衰减。"""

    category = "wedge"
    signal_id = "WEDGE_THREE_PUSH"
    family = "wedge"
    rank = 17

    @staticmethod
    def _avg_body_since(ctx: SignalContext, since) -> float:
        from ..structures import body_ratio

        push_bars = [b for b in ctx.bars if b.datetime >= since]
        if not push_bars:
            return 1.0
        return sum(body_ratio(b) for b in push_bars) / len(push_bars)

    @staticmethod
    def _low_between(lows, t1, t2):
        inside = [p for p in lows if t1 < p.pivot_bar_time < t2]
        return min(inside, key=lambda p: p.price) if inside else None

    @staticmethod
    def _high_between(highs, t1, t2):
        inside = [p for p in highs if t1 < p.pivot_bar_time < t2]
        return max(inside, key=lambda p: p.price) if inside else None

    @staticmethod
    def _low_before(lows, t):
        before = [p for p in lows if p.pivot_bar_time < t]
        return min(before, key=lambda p: p.price) if before else None

    @staticmethod
    def _high_before(highs, t):
        before = [p for p in highs if p.pivot_bar_time < t]
        return max(before, key=lambda p: p.price) if before else None

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        out: list[AlertDraft] = []
        if ctx.context_tag != "reversal":
            return out
        atr = ctx.atr
        highs = [p for p in ctx.pivots.confirmed if p.kind == "H"]
        lows = [p for p in ctx.pivots.confirmed if p.kind == "L"]
        buf = ctx.buffer()
        ratio = ctx.cfg["wedge_decay_ratio"]
        body_max = ctx.cfg["wedge_body_max"]

        if len(highs) >= 3 and len(lows) >= 2:
            h1, h2, h3 = highs[-3], highs[-2], highs[-1]
            l1 = self._low_between(lows, h1.pivot_bar_time, h2.pivot_bar_time)
            l2 = self._low_between(lows, h2.pivot_bar_time, h3.pivot_bar_time)
            l0 = self._low_before(lows, h1.pivot_bar_time)
            if l0 and l1 and l2:
                a1 = h1.price - l0.price
                a2 = h2.price - l1.price
                a3 = h3.price - l2.price
                decay = self._avg_body_since(ctx, l2.pivot_bar_time)
                if (0 < a3 < a2 < a1 and a3 <= a1 * ratio
                        and decay <= body_max and ctx.allowed("short")):
                    out.append(_mk_draft(self, ctx, "short", "cross_below",
                                         ctx.bar.low_price - buf, "signal_bar_low",
                                         h3.price + 0.25 * atr, "wedge_high_offset",
                                         ("close_above", h3.price)))

        if len(lows) >= 3 and len(highs) >= 2:
            l1, l2, l3 = lows[-3], lows[-2], lows[-1]
            h1 = self._high_between(highs, l1.pivot_bar_time, l2.pivot_bar_time)
            h2 = self._high_between(highs, l2.pivot_bar_time, l3.pivot_bar_time)
            h0 = self._high_before(highs, l1.pivot_bar_time)
            if h0 and h1 and h2:
                a1 = h0.price - l1.price
                a2 = h1.price - l2.price
                a3 = h2.price - l3.price
                decay = self._avg_body_since(ctx, l3.pivot_bar_time)
                if (0 < a3 < a2 < a1 and a3 <= a1 * ratio
                        and decay <= body_max and ctx.allowed("long")):
                    out.append(_mk_draft(self, ctx, "long", "cross_above",
                                         ctx.bar.high_price + buf, "signal_bar_high",
                                         l3.price - 0.25 * atr, "wedge_low_offset",
                                         ("close_below", l3.price)))
        return out


class PullbackOrdinalDetector(BaseDetector):
    """回调序数参数化（RS004 §1，HO002 M-PT-004）：n=1 即 H1/L1 首次回调。

    判据（多头 H1 为例，RS004 §1.2）：
    1. context ∈ {trend_strong, trend_channel} 且 EMA 斜率同向
    2. 首次回调：L1（最近已确认低点）之前 h1_lookback 根内无其他已确认低点
    3. 结构保持：L1 未跌破前一低点；浅回调：L1 >= EMA - h1_ema_tol x ATR
    4. 恢复确认：信号K收盘 > L1 后首个中间高点 H_mid
    触发 = 信号K高点 + buffer（与 h2_l2 同构）；止损 = L1 - 0.25xATR；
    失效 = 收盘跌破 L1。
    ordinal=2 预留 H2/L2 泛化（现网 h2_l2 由 HighTwoLowTwoDetector 承担，
    本类仅注册 n=1，避免信号重复）。
    默认关闭：cfg["enable_h1_l1"]=False 时不出信号（HO001 基线零回归）。
    """

    category = "h1_l1"
    signal_id = "H1_L1_TREND"
    family = "h1_l1"
    rank = 27

    def __init__(self, ordinal: int = 1) -> None:
        self.ordinal = ordinal

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        out: list[AlertDraft] = []
        if not ctx.cfg.get("enable_h1_l1", False):
            return out
        if ctx.context_tag not in ("trend_strong", "trend_channel"):
            return out
        ema, atr = ctx.ema.value, ctx.atr
        if ema is None or atr <= 0:
            return out
        index = {b.datetime: i for i, b in enumerate(ctx.bars)}
        lookback = ctx.cfg["h1_lookback"]
        tol = ctx.cfg["h1_ema_tol"] * atr
        buf = ctx.buffer()
        lows = [p for p in ctx.pivots.confirmed if p.kind == "L"]
        highs = [p for p in ctx.pivots.confirmed if p.kind == "H"]
        slope = ctx.ema_slope()

        if slope > 0 and lows:
            pull = lows[-1]
            prev_low = lows[-2] if len(lows) >= 2 else None
            gap_ok = True
            if prev_low is not None:
                g = self._gap(index, prev_low.pivot_bar_time, pull.pivot_bar_time)
                gap_ok = g is not None and g > lookback
            structure_ok = prev_low is None or pull.price >= prev_low.price
            has_h0 = any(p.pivot_bar_time < pull.pivot_bar_time for p in highs)
            mids = [p for p in highs if p.pivot_bar_time > pull.pivot_bar_time]
            if (gap_ok and structure_ok and has_h0 and mids
                    and pull.price >= ema - tol
                    and ctx.bar.close_price > mids[0].price
                    and ctx.allowed("long")):
                out.append(_mk_draft(self, ctx, "long", "cross_above",
                                     ctx.bar.high_price + buf, "signal_bar_high",
                                     pull.price - 0.25 * atr, "h1_low_offset",
                                     ("close_below", pull.price)))

        if slope < 0 and highs:
            pull = highs[-1]
            prev_high = highs[-2] if len(highs) >= 2 else None
            gap_ok = True
            if prev_high is not None:
                g = self._gap(index, prev_high.pivot_bar_time, pull.pivot_bar_time)
                gap_ok = g is not None and g > lookback
            structure_ok = prev_high is None or pull.price <= prev_high.price
            has_l0 = any(p.pivot_bar_time < pull.pivot_bar_time for p in lows)
            mids = [p for p in lows if p.pivot_bar_time > pull.pivot_bar_time]
            if (gap_ok and structure_ok and has_l0 and mids
                    and pull.price <= ema + tol
                    and ctx.bar.close_price < mids[0].price
                    and ctx.allowed("short")):
                out.append(_mk_draft(self, ctx, "short", "cross_below",
                                     ctx.bar.low_price - buf, "signal_bar_low",
                                     pull.price + 0.25 * atr, "h1_high_offset",
                                     ("close_above", pull.price)))
        return out

    @staticmethod
    def _gap(index: dict, t1, t2):
        a, b = index.get(t1), index.get(t2)
        if a is None or b is None:
            return None
        return abs(b - a)


class WmDetector(BaseDetector):
    """W 底 / M 顶（RS004 §2，HO002 M-PT-005）：两推 + 颈线 + 衰竭证据。

    与 M-PT-002（双顶底）的区别：额外要求中间反弹（颈线）的完整结构，
    且 |L2-L1| 容差更宽（wm_tol_atr=0.5 vs dbl 0.3），允许 L2<L1 扫损
    （wash & rinse）。第二推必须有衰竭证据（L2 摆动K上的针形或吞没）。
    触发 = 颈线 N ± buffer 突破单（RS004 §2.2 字面口径）；
    止损 = L2 - 0.25xATR；失效 = 收盘回落至颈线对侧。
    同信号同向时抑制双顶底重复通知（runtime 层处理，仅 w_m 开启时生效）。
    默认关闭：cfg["enable_w_m"]=False 时不出信号（HO001 基线零回归）。
    """

    category = "w_m"
    signal_id = "W_BOTTOM"
    family = "w_m"
    rank = 19

    def detect(self, ctx: SignalContext) -> list[AlertDraft]:
        out: list[AlertDraft] = []
        if not ctx.cfg.get("enable_w_m", False):
            return out
        if ctx.context_tag not in ("range", "reversal"):
            return out
        atr = ctx.atr
        if atr <= 0:
            return out
        lows = [p for p in ctx.pivots.confirmed if p.kind == "L"]
        highs = [p for p in ctx.pivots.confirmed if p.kind == "H"]
        index = {b.datetime: i for i, b in enumerate(ctx.bars)}
        min_sep = ctx.cfg["wm_min_sep_bars"]
        max_sep = ctx.cfg["wm_max_sep_bars"]
        tol = ctx.cfg["wm_tol_atr"] * atr
        neck_min = ctx.cfg["wm_neck_min_atr"] * atr
        buf = ctx.buffer()

        if len(lows) >= 2:
            l1, l2 = lows[-2], lows[-1]
            sep = self._gap(index, l1.pivot_bar_time, l2.pivot_bar_time)
            necks = [p for p in highs
                     if l1.pivot_bar_time < p.pivot_bar_time < l2.pivot_bar_time]
            neck = max(necks, key=lambda p: p.price) if necks else None
            if (sep is not None and min_sep <= sep <= max_sep
                    and abs(l2.price - l1.price) <= tol
                    and neck is not None
                    and neck.price - max(l1.price, l2.price) >= neck_min
                    and self._exhaustion(ctx, index, l2, bull=True)
                    and ctx.bar.close_price > neck.price
                    and ctx.allowed("long")):
                d = _mk_draft(self, ctx, "long", "cross_above",
                              neck.price + buf, "neck_level",
                              l2.price - 0.25 * atr, "wm_low_offset",
                              ("close_below", neck.price))
                d.signal_id = "W_BOTTOM"
                d.note = "wash" if l2.price < l1.price else ""
                out.append(d)

        if len(highs) >= 2:
            h1, h2 = highs[-2], highs[-1]
            sep = self._gap(index, h1.pivot_bar_time, h2.pivot_bar_time)
            necks = [p for p in lows
                     if h1.pivot_bar_time < p.pivot_bar_time < h2.pivot_bar_time]
            neck = min(necks, key=lambda p: p.price) if necks else None
            if (sep is not None and min_sep <= sep <= max_sep
                    and abs(h2.price - h1.price) <= tol
                    and neck is not None
                    and min(h1.price, h2.price) - neck.price >= neck_min
                    and self._exhaustion(ctx, index, h2, bull=False)
                    and ctx.bar.close_price < neck.price
                    and ctx.allowed("short")):
                d = _mk_draft(self, ctx, "short", "cross_below",
                              neck.price - buf, "neck_level",
                              h2.price + 0.25 * atr, "wm_high_offset",
                              ("close_above", neck.price))
                d.signal_id = "M_TOP"
                d.note = "wash" if h2.price > h1.price else ""
                out.append(d)
        return out

    @staticmethod
    def _exhaustion(ctx: SignalContext, index: dict, pivot, bull: bool) -> bool:
        """第二推衰竭证据：摆动K上的针形（M-KB-001）或吞没（M-KB-002）。"""
        i = index.get(pivot.pivot_bar_time)
        if i is None or i < 1:
            return False
        bar, prev = ctx.bars[i], ctx.bars[i - 1]
        return RangeEdgeDetector._pin(bar, bull) or RangeEdgeDetector._engulf(bar, prev, bull)

    @staticmethod
    def _gap(index: dict, t1, t2):
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
    WedgeThreePushDetector,
    PullbackOrdinalDetector,
    WmDetector,
]


def build_detectors() -> list[BaseDetector]:
    return [cls() for cls in DETECTOR_CLASSES]
