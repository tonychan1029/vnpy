"""Point-in-time 回放评估器（spec 10.1）：真实K线 -> 预警 -> 前瞻标注。"""

from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass

from vnpy.trader.object import BarData

from .config import build_config
from .engine import PatimingEngine


@dataclass
class AlertOutcome:
    alert_id: str
    signal_id: str
    family: str
    direction: str
    trigger: float
    stop: float
    target1: float
    lifecycle: str
    result: str = ""
    bars_to_outcome: int | None = None
    mfe: float | None = None
    mae: float | None = None


class ReplayEvaluator:
    """回放真实K线，对每条 ARMED 预警标注前瞻结果并输出分信号报告。"""

    def __init__(self, cfg_overrides: dict | None = None, horizon: int = 50) -> None:
        self.cfg = build_config(cfg_overrides)
        self.horizon = horizon

    def run(self, symbol: str, exchange: str, bars: list[BarData],
            instruction: dict, source: str = "strategy:replay") -> dict:
        outcomes: list[AlertOutcome] = []
        with tempfile.TemporaryDirectory() as tmp:
            engine = PatimingEngine(
                f"{tmp}/replay.db", {"warmup_min_exec": self.cfg["warmup_min_exec"]},
                clock=lambda: bars[-1].datetime if bars else datetime_now(),
            )
            engine.register_delivery_handler(lambda event: None)
            result = engine.submit_instruction(source, dict(instruction))
            if not result.get("ok"):
                raise ValueError(f"instruction rejected: {result}")
            engine.reconcile()
            for bar in bars:
                engine.on_1m_bar(bar)
            engine.flush_due(bars[-1].datetime)
            for task in engine.tasks.values():
                for alert in task.alerts.values():
                    outcomes.append(self._label(bars, alert))
            engine.db.close()
        return self._report(outcomes)

    def _label(self, bars: list[BarData], alert) -> AlertOutcome:
        armed_idx = next(
            (i for i, b in enumerate(bars) if b.datetime == alert.armed_bar_time), 0
        )
        forward = bars[armed_idx + 1 : armed_idx + 1 + self.horizon]
        sign = 1.0 if alert.direction == "long" else -1.0
        entry = alert.trigger["level"]
        mfe = mae = 0.0
        result, hit_bar = None, None
        for offset, bar in enumerate(forward, start=1):
            move = (bar.high_price - entry) * sign
            adverse = (entry - bar.low_price) * sign
            mfe, mae = max(mfe, move), max(mae, adverse)
            if alert.lifecycle == "TRIGGERED":
                if move >= risk(alert):
                    result, hit_bar = "T1", offset
                    break
                if adverse >= risk(alert):
                    result, hit_bar = "SL", offset
                    break
        if result is None:
            result = {"TRIGGERED": "TRIGGERED_OPEN", "ARMED": "EXPIRED_OPEN"}.get(
                alert.lifecycle, "EXPIRED_OPEN" if alert.lifecycle == "EXPIRED"
                else alert.lifecycle)
        outcome = AlertOutcome(
            alert_id=alert.alert_id, signal_id=alert.signal_id,
            family=alert.family, direction=alert.direction,
            trigger=entry, stop=alert.stop["level"],
            target1=alert.targets["t1"]["price"], lifecycle=alert.lifecycle,
            result=result or "OPEN",
            bars_to_outcome=hit_bar, mfe=round(mfe, 6), mae=round(mae, 6),
        )
        return outcome

    def _report(self, outcomes: list[AlertOutcome]) -> dict:
        summary: dict[str, dict] = {}
        for o in outcomes:
            bucket = summary.setdefault(o.signal_id, {"n": 0, "t1_first": 0,
                                                      "sl_first": 0, "open": 0})
            bucket["n"] += 1
            if o.result == "T1":
                bucket["t1_first"] += 1
            elif o.result == "SL":
                bucket["sl_first"] += 1
            else:
                bucket["open"] += 1
        for bucket in summary.values():
            decided = bucket["t1_first"] + bucket["sl_first"]
            bucket["win_rate"] = round(bucket["t1_first"] / decided, 4) if decided else None
        return {
            "alerts": [asdict(o) for o in outcomes],
            "summary": summary,
            "horizon": self.horizon,
        }


def risk(alert) -> float:
    return abs(alert.trigger["level"] - alert.stop["level"])


def datetime_now():
    from datetime import datetime

    return datetime.now()
