"""Monitoring task runtime: indicators, detectors, alert state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from vnpy.trader.object import BarData

from .config import TIMEFRAME_MINUTES
from .signals import (
    AlertDraft,
    SignalContext,
    passes_quality,
    targets_for,
)
from .signals.detectors import build_detectors
from .structures import (
    ATR,
    EMA,
    LevelManager,
    PivotDetector,
)

TRAILING_CATEGORIES = {"h2_l2"}


@dataclass
class Alert:
    alert_id: str
    instruction_keys: list[str]
    category: str
    signal_id: str
    family: str
    rank: int
    direction: str
    order_type: str
    trigger: dict
    stop: dict
    invalidation: dict
    targets: dict
    context_tag: str
    data_mode: str
    armed_bar_time: datetime
    expire_bars_left: int
    provisional: bool = False
    lifecycle: str = "ARMED"
    extra: dict = field(default_factory=dict)

    def tick_triggered(self, price: float) -> bool:
        t, lv = self.trigger, self.trigger["level"]
        if self.direction == "long":
            if t["type"] == "cross_above":
                return price >= lv
            if t["type"] == "touch_below":
                return price <= lv
        else:
            if t["type"] == "cross_below":
                return price <= lv
            if t["type"] == "touch_above":
                return price >= lv
        return False

    def invalid_crossed(self, price: float) -> bool:
        inv = self.invalidation
        if inv["type"] == "close_below":
            return price < inv["level"]
        if inv["type"] == "close_above":
            return price > inv["level"]
        return False


def _categories_enabled(row: dict, category: str) -> bool:
    cats = row["signal_categories"]
    return cats == "ALL" or category in cats


class MonitoringTask:
    """Per (symbol, exec_timeframe) runtime shared by instructions."""

    def __init__(self, engine, symbol: str, exec_tf: str, sel_tf: str) -> None:
        self.engine = engine
        self.cfg = engine.cfg
        self.symbol = symbol
        self.exec_tf = exec_tf
        self.sel_tf = sel_tf
        self.data_mode = engine.data_mode
        self.bars: list[BarData] = []
        self.atr = ATR(self.cfg["atr_period"])
        self.ema = EMA(self.cfg["ema_period"])
        self.pivots = PivotDetector(self.cfg["pivot_k"])
        self.levels = LevelManager()
        self.detectors = build_detectors()
        self.alerts: dict[str, Alert] = {}
        self.fake_log: list = []
        self.contributions: dict[tuple[str, str], dict] = {}
        self.warm_exec = 0
        self.exec_count = 0
        self.ready = False
        self.ever_received = False

    # ------------- contributions -------------

    def add_contribution(self, row: dict) -> None:
        self.contributions[(row["source"], row["instruction_id"])] = dict(row)
        self.reseed_levels()

    def remove_contribution(self, source: str, instruction_id: str) -> None:
        self.contributions.pop((source, instruction_id), None)
        self.reseed_levels()

    def reseed_levels(self) -> None:
        self.levels = LevelManager()
        seen: set[tuple[str, float]] = set()
        for row in self.contributions.values():
            for kind, price in (row.get("key_levels") or {}).items():
                if price is None:
                    continue
                key = (kind, float(price))
                if key not in seen:
                    seen.add(key)
                    self.levels.add(kind, float(price))

    def contribution_signature(self) -> tuple:
        return tuple(
            sorted((src, iid, row["content_hash"] or "") for (src, iid), row in self.contributions.items())
        )

    # ------------- market events -------------

    def on_exec_bar(self, bar: BarData) -> None:
        self.ever_received = True
        self.exec_count += 1
        self.bars.append(bar)
        if len(self.bars) > 200:
            self.bars = self.bars[-200:]
        self.atr.update(bar)
        self.ema.update(bar.close_price)

        if not self.ready:
            self.warm_exec += 1
            if self.warm_exec >= self.cfg["warmup_min_exec"] and self.atr.value:
                self.ready = True
                self.engine.on_task_ready(self)
            return

        self.pivots.update(bar)
        self._handle_gaps(bar)

        # 1) close-confirmed invalidation / provisional restore
        for alert in list(self.alerts.values()):
            if alert.lifecycle != "ARMED":
                continue
            crossed = self._close_crossed(bar, alert)
            if alert.provisional:
                if crossed:
                    self._transition(alert, "INVALIDATED", "signal.invalidated")
                else:
                    alert.provisional = False
                    self.engine.emit_alert(self, alert, "signal.restored", "ARMED")
            elif crossed:
                self._transition(alert, "INVALIDATED", "signal.invalidated")

        # 2) expiry countdown (exec clock)
        for alert in list(self.alerts.values()):
            if alert.lifecycle == "ARMED":
                alert.expire_bars_left -= 1
                if alert.expire_bars_left <= 0:
                    self._transition(alert, "EXPIRED", "signal.expired")

        # 3) detection & arming
        self._detect_and_arm()

        # 4) level validity update runs after detection: a breakout bar closes
        # through the level and must still be detected on that very close.
        self.levels.on_bar_close(bar, self.atr.value, self.cfg["level_touch_atr"])

    def _close_crossed(self, bar: BarData, alert: Alert) -> bool:
        inv = alert.invalidation
        if inv["type"] == "close_below":
            return bar.close_price < inv["level"]
        if inv["type"] == "close_above":
            return bar.close_price > inv["level"]
        return False

    def _handle_gaps(self, bar: BarData) -> None:
        prev = self.bars[-2] if len(self.bars) >= 2 else None
        if prev is not None and bar.open_price > prev.high_price:
            self.levels.add(
                "gap_edge",
                prev.high_price,
                meta={"deadline": self.exec_count + self.cfg["gap_fill_bars"]},
            )
        for lv in self.levels.levels:
            if lv.kind != "gap_edge" or lv.status == "broken":
                continue
            if bar.close_price < lv.price:
                lv.status = "broken"
                lv.meta["filled"] = True
            elif "deadline" in lv.meta and self.exec_count >= lv.meta["deadline"]:
                lv.status = "tested"

    def on_price(self, price: float) -> None:
        """Tick layer (ctp_tick) or 1m-close driver (akshare_poll, spec 5.1)."""
        for alert in list(self.alerts.values()):
            if alert.lifecycle != "ARMED":
                continue
            if not alert.provisional and alert.invalid_crossed(price):
                alert.provisional = True
                self.engine.emit_alert(self, alert, "signal.at_risk", "ARMED")
            if alert.tick_triggered(price):
                self._transition(alert, "TRIGGERED", "signal.triggered")

    def _transition(self, alert: Alert, lifecycle: str, event_type: str) -> None:
        from_lf = alert.lifecycle
        alert.lifecycle = lifecycle
        self.engine.emit_alert(self, alert, event_type, from_lf)

    # ------------- detection -------------

    def _detect_and_arm(self) -> None:
        merged: dict[tuple, AlertDraft] = {}
        for (source, iid), row in self.contributions.items():
            if row["status"] not in ("ACTIVE",):
                continue
            ctx = SignalContext(
                bars=list(self.bars),
                atr=self.atr.value,
                ema=self.ema,
                pivots=self.pivots,
                levels=self.levels,
                cfg=self.cfg,
                direction=row["direction"],
                context_tag=row["context_tag"] or self.cfg["default_context_tag"],
                now=self.bars[-1].datetime,
                price_tick=self.cfg["price_tick"],
                fake_log=self.fake_log,
            )
            for det in self.detectors:
                if det.category not in (row["signal_categories"] or set()) and row["signal_categories"] != "ALL":
                    continue
                if row["signal_categories"] == "ALL" and det.category not in {
                    "breakout", "fake_breakout", "second_breakout",
                    "ema_pullback", "structure_pullback", "range_edge",
                }:
                    continue
                for draft in det.detect(ctx):
                    key = (
                        draft.signal_id,
                        draft.direction,
                        round(draft.trigger["level"] / self.cfg["price_tick"]),
                    )
                    existing = merged.get(key)
                    if existing is None:
                        merged[key] = draft
                    existing_keys = existing.instruction_keys if existing else draft.instruction_keys
                    if existing is not None:
                        existing.instruction_keys = existing_keys | {(source, iid)}
                    else:
                        draft.instruction_keys = {(source, iid)}
        for draft in merged.values():
            self._arm_or_merge(draft)

    def _arm_or_merge(self, draft: AlertDraft) -> None:
        if not passes_quality(
            SignalContext(
                bars=list(self.bars), atr=self.atr.value, ema=self.ema,
                pivots=self.pivots, levels=self.levels, cfg=self.cfg,
                direction=draft.direction,
                context_tag=self.cfg["default_context_tag"],
                now=self.bars[-1].datetime,
                price_tick=self.cfg["price_tick"], fake_log=self.fake_log,
            ),
            draft,
        ):
            return
        for alert in self.alerts.values():
            if alert.lifecycle == "ARMED" and alert.signal_id == draft.signal_id and alert.direction == draft.direction:
                if draft.category in TRAILING_CATEGORIES:
                    # 挂单逐根刷新（spec 6.3）：trailing 触发价原地更新，不产生事件
                    alert.trigger["level"] = draft.trigger["level"]
                    alert.stop["level"] = draft.stop["level"]
                    return
                if draft.rank > alert.rank:
                    self._transition(alert, "REPLACED", "signal.replaced")
                    break
                return  # existing equal/stronger stays
        alert_id = self.engine.next_alert_id()
        entry = draft.trigger["level"]
        alert = Alert(
            alert_id=alert_id,
            instruction_keys=sorted(f"{s}|{i}" for s, i in draft.instruction_keys),
            category=draft.category,
            signal_id=draft.signal_id,
            family=draft.family,
            rank=draft.rank,
            direction=draft.direction,
            order_type=draft.order_type,
            trigger=draft.trigger,
            stop=draft.stop,
            invalidation=draft.invalidation,
            targets=targets_for(entry, draft.stop["level"], draft.direction),
            context_tag=self._row_context(draft),
            data_mode=self.data_mode,
            armed_bar_time=self.bars[-1].datetime,
            expire_bars_left=self.cfg["expire_bars_exec"],
        )
        self.alerts[alert_id] = alert
        self.engine.emit_alert(self, alert, "signal.armed", None)

    def _row_context(self, draft: AlertDraft) -> str:
        for key in draft.instruction_keys:
            row = self.contributions.get(key)
            if row and row["context_tag"]:
                return row["context_tag"]
        return self.cfg["default_context_tag"]

    # ------------- cancellation -------------

    def cancel_for_instruction(self, source: str, instruction_id: str) -> None:
        key = f"{source}|{instruction_id}"
        for alert in list(self.alerts.values()):
            if alert.lifecycle != "ARMED" or key not in alert.instruction_keys:
                continue
            alert.instruction_keys.remove(key)
            if not alert.instruction_keys:
                self._transition(alert, "CANCELLED", "signal.cancelled")

    def cancel_all(self, reason: str) -> None:
        for alert in list(self.alerts.values()):
            if alert.lifecycle == "ARMED":
                alert.extra["cancel_reason"] = reason
                self._transition(alert, "CANCELLED", "signal.cancelled")

    def interval_minutes(self) -> int:
        return TIMEFRAME_MINUTES[self.exec_tf]
