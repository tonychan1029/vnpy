"""PatimingEngine: sole DB writer, reconciliation, countdown, outbox dispatch."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta

from vnpy.trader.object import BarData, TickData

from .canonical import content_hash
from .config import (
    CONTEXT_TAGS,
    DIRECTIONS,
    REASON_CODES,
    SIGNAL_CATEGORIES,
    TIMEFRAME_MINUTES,
    build_config,
)
from .db import Database, now_str
from .market import MarketClock, window_open
from .market import trading_minutes_between
from .runtime import Alert, MonitoringTask

SYMBOL_RE = re.compile(r"^[A-Za-z0-9_]{1,20}\.[A-Za-z0-9_]{1,10}$")
LEVEL_KEYS = {"prior_high", "prior_low", "range_top", "range_bottom",
              "support", "resistance"}
META_KEYS = {"swing_points"}
LEVEL_ALIASES = {"support": "prior_low", "resistance": "prior_high"}
CONFIG_VERSION = "patiming-v1.2"
CONFIDENCE_BASE = {
    "breakout": 0.65,
    "second_breakout": 0.70,
    "fake_breakout": 0.60,
    "h2_l2": 0.60,
    "ema_pullback": 0.55,
    "structure_pullback": 0.55,
    "double_top_bottom": 0.55,
    "range_edge": 0.50,
}


def fail(error: str, **kw) -> dict:
    out = {"ok": False, "error": error}
    out.update(kw)
    return out


class PatimingEngine:
    def __init__(
        self,
        db_path: str,
        cfg_overrides: dict | None = None,
        clock=datetime.now,
        data_mode: str = "ctp_tick",
        run_mode: str = "LIVE",
    ) -> None:
        self.cfg = build_config(cfg_overrides)
        self.clock = clock
        self.data_mode = data_mode
        if run_mode not in ("LIVE", "REPLAY"):
            raise ValueError("run_mode must be LIVE or REPLAY")
        self.run_mode = run_mode
        self.db = Database(db_path)
        self.lock = threading.RLock()
        self.clocks: dict[str, MarketClock] = {}
        self.tasks: dict[tuple[str, str], MonitoringTask] = {}
        self._task_sig: dict[tuple[str, str], tuple] = {}
        self._alert_seq = 0
        self.last_prices: dict[str, float] = {}
        self._last_submit: dict[str, datetime] = {}
        self._summary_sig = None
        self._summary_seq = 0
        self.delivery_handlers: list = []
        self.tick_fallback_hooks: list = []  # fn(symbol) -> None：订阅 T口 tick
        self._running = False
        self._thread: threading.Thread | None = None

    def close(self) -> None:
        self.stop()
        self.db.close()

    # ================= write API (spec 3.1 / 8) =================

    def submit_instruction(self, caller_source: str, payload: dict) -> dict:
        with self.lock:
            return self._submit(caller_source, dict(payload or {}))

    def revoke(self, caller_source: str, instruction_id: str, producer_revision: int) -> dict:
        return self.submit_instruction(
            caller_source,
            {
                "instruction_id": instruction_id,
                "producer_revision": producer_revision,
                "desired_status": "REVOKED",
            },
        )

    def query(self, caller_source: str, instruction_id: str | None = None) -> dict:
        with self.lock:
            if instruction_id is not None:
                row = self.db.fetch_instruction(caller_source, instruction_id)
                if row is None:
                    return fail("not_found")
                row["instruction_events"] = self.db.fetch_instruction_events(
                    caller_source, instruction_id
                )
                row["alert_events"] = self.db.fetch_alert_events_for_instruction(
                    caller_source, instruction_id
                )
                return {"ok": True, "instruction": row}
        rows = self.db.query(
            "SELECT * FROM timing_instruction WHERE source=? ORDER BY rowid",
            (caller_source,),
        )
        return {"ok": True, "instructions": rows}

    def health_snapshot(self) -> dict:
        """Read-only runtime state for operations; never exposes tokens."""
        with self.lock:
            tasks = []
            for (symbol, exec_tf), task in sorted(self.tasks.items()):
                clock = self.clocks.get(symbol)
                alert_counts: dict[str, int] = {}
                for alert in task.alerts.values():
                    alert_counts[alert.lifecycle] = (
                        alert_counts.get(alert.lifecycle, 0) + 1
                    )
                last_bar = task.bars[-1] if task.bars else None
                tasks.append({
                    "symbol": symbol,
                    "exec_timeframe": exec_tf,
                    "data_mode": task.data_mode,
                    "ready": task.ready,
                    "warm_exec": task.warm_exec,
                    "exec_count": task.exec_count,
                    "instruction_count": len(task.contributions),
                    "last_price": self.last_prices.get(symbol),
                    "clock_last_seen": (
                        clock.last_seen.isoformat(timespec="seconds")
                        if clock and clock.last_seen else None
                    ),
                    "last_exec_bar": (
                        last_bar.datetime.isoformat(timespec="seconds")
                        if last_bar else None
                    ),
                    "alerts": alert_counts,
                })
            status_rows = self.db.query(
                "SELECT status, count(*) AS n FROM timing_instruction "
                "GROUP BY status ORDER BY status"
            )
            return {
                "ok": True,
                "generated_at": now_str(self.clock),
                "run_mode": self.run_mode,
                "data_mode": self.data_mode,
                "status_counts": {
                    row["status"]: row["n"] for row in status_rows
                },
                "tasks": tasks,
            }

    def _submit(self, caller_source: str, payload: dict) -> dict:
        now = self.clock()
        ts = now_str(self.clock)
        payload.pop("source", None)  # server-side identity injection (spec 8)
        if not caller_source or not (
            caller_source.startswith("strategy:") or caller_source.startswith("llm:")
        ):
            return fail("bad_source")
        if self._rate_limited(caller_source, now):
            return fail("rate_limited")
        iid = payload.get("instruction_id")
        rev = payload.get("producer_revision")
        if not isinstance(iid, str) or not iid or len(iid) > 64:
            return fail("bad_instruction_id")
        if not isinstance(rev, int) or rev <= 0:
            return fail("bad_revision")
        desired = payload.get("desired_status", "ACTIVE")
        if desired not in ("ACTIVE", "REVOKED"):
            return fail("bad_desired_status")

        existing = self.db.fetch_instruction(caller_source, iid)
        if existing and rev <= existing["producer_revision"]:
            self._audit(caller_source, iid, rev, "REJECTED",
                        existing["status"], existing["status"], ts, "stale_revision")
            self.db.commit()
            return fail("stale_revision")
        if existing and existing["status"] in ("REVOKED", "EXPIRED"):
            self._audit(caller_source, iid, rev, "REJECTED",
                        existing["status"], existing["status"], ts, "terminal_status")
            self.db.commit()
            return fail("terminal_status")

        if existing is None and desired == "ACTIVE":
            quota = self._quota_check(caller_source)
            if quota:
                return fail(quota)

        if desired == "REVOKED":
            # Revoke is a state request only: no business validation required.
            business = {"desired_status": "REVOKED", "producer_revision": rev}
            chash = content_hash(business)
            if existing is None:
                return fail("not_found")
            self.db.execute(
                "UPDATE timing_instruction SET producer_revision=?, desired_status=?,"
                " content_hash=?, updated_at=? WHERE source=? AND instruction_id=?",
                (rev, desired, chash, ts, caller_source, iid),
            )
            self._audit(caller_source, iid, rev, "UPDATED",
                        existing["status"], existing["status"], ts, snapshot=business)
            self.db.commit()
            return {"ok": True, "status": existing["status"], "content_hash": chash}

        err = self._validate_common(payload, now)
        if err:
            return fail(err)
        cleaned = self._clean(payload)
        deep_err = self._deep_validate(cleaned, now)
        if deep_err is None and self._llm_params_locked(caller_source, cleaned):
            return fail("params_locked")

        business = dict(cleaned)
        business["desired_status"] = desired
        business["producer_revision"] = rev
        chash = content_hash(business)

        if existing is None:
            pending = (
                self.cfg["require_approval"]
                and caller_source.startswith("llm:")
                and desired == "ACTIVE"
            )
            status = "INVALID" if deep_err else (
                "PENDING_APPROVAL" if pending
                else ("REVOKED" if desired == "REVOKED" else "ACTIVE")
            )
            feedback = deep_err or {
                "PENDING_APPROVAL": "AWAITING_APPROVAL",
                "REVOKED": "REVOKED_AT_WRITE",
            }.get(status, "ACCEPTED")
            self.db.execute(
                "INSERT INTO timing_instruction (source, instruction_id, producer_revision,"
                " desired_status, symbol, selection_timeframe, exec_timeframe, context_tag,"
                " signal_categories, direction, key_levels, params, priority, reason_code,"
                " reason_note, valid_bars, valid_until, content_hash, status, feedback,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    caller_source, iid, rev, desired, cleaned["symbol"],
                    cleaned["selection_timeframe"], cleaned["exec_timeframe"],
                    cleaned["context_tag"], json.dumps(cleaned["signal_categories"]),
                    cleaned["direction"], json.dumps(cleaned["key_levels"]),
                    json.dumps(cleaned["params"]), cleaned["priority"],
                    cleaned["reason_code"], cleaned["reason_note"],
                    cleaned["valid_bars"], cleaned["valid_until"], chash,
                    status, feedback, ts, ts,
                ),
            )
            self._audit(caller_source, iid, rev, "CREATED", None, status, ts,
                        snapshot=business)
        else:
            if existing["status"] == "INVALID":
                status = "INVALID" if deep_err else (
                    "REVOKED" if desired == "REVOKED" else "ACTIVE"
                )
                self.db.update_instruction_engine(
                    caller_source, iid, status, deep_err or "REVIVED"
                )
            else:
                status = existing["status"]
            self.db.execute(
                "UPDATE timing_instruction SET producer_revision=?, desired_status=?,"
                " symbol=?, selection_timeframe=?, exec_timeframe=?, context_tag=?,"
                " signal_categories=?, direction=?, key_levels=?, params=?, priority=?,"
                " reason_code=?, reason_note=?, valid_bars=?, valid_until=?,"
                " content_hash=?, updated_at=? WHERE source=? AND instruction_id=?",
                (
                    rev, desired, cleaned["symbol"], cleaned["selection_timeframe"],
                    cleaned["exec_timeframe"], cleaned["context_tag"],
                    json.dumps(cleaned["signal_categories"]), cleaned["direction"],
                    json.dumps(cleaned["key_levels"]), json.dumps(cleaned["params"]),
                    cleaned["priority"], cleaned["reason_code"], cleaned["reason_note"],
                    cleaned["valid_bars"], cleaned["valid_until"], chash, ts,
                    caller_source, iid,
                ),
            )
            self._audit(caller_source, iid, rev, "UPDATED",
                        existing["status"], existing["status"], ts, snapshot=business)
        self.db.commit()
        return {"ok": True, "status": status, "content_hash": chash}

    def _quota_check(self, source: str) -> str | None:
        if self.db.count_active_by_source(source) >= self.cfg["quota_per_source"]:
            return "quota_per_source_exceeded"
        if self.db.count_active_total() >= self.cfg["quota_total_active"]:
            return "quota_total_exceeded"
        return None

    def _validate_common(self, p: dict, now: datetime) -> str | None:
        for f in ("symbol", "selection_timeframe", "exec_timeframe", "reason_code", "reason_note"):
            if f not in p or p[f] in (None, ""):
                return f"missing:{f}"
        if not isinstance(p["symbol"], str) or not SYMBOL_RE.match(p["symbol"]):
            return "bad_symbol"
        if p["selection_timeframe"] not in TIMEFRAME_MINUTES:
            return "bad_selection_timeframe"
        if p["exec_timeframe"] not in TIMEFRAME_MINUTES:
            return "bad_exec_timeframe"
        if p["reason_code"] not in REASON_CODES:
            return "bad_reason_code"
        note = p["reason_note"]
        if not isinstance(note, str) or not note.strip() or len(note) > 500:
            return "bad_reason_note"
        if p.get("direction", "both") not in DIRECTIONS:
            return "bad_direction"
        cats = p.get("signal_categories", "ALL")
        if cats != "ALL":
            if not isinstance(cats, list) or any(c not in SIGNAL_CATEGORIES for c in cats):
                return "bad_signal_categories"
        kl = p.get("key_levels") or {}
        if not isinstance(kl, dict) or any(
            k not in LEVEL_KEYS and k not in META_KEYS for k in kl
        ):
            return "bad_key_levels"
        if any(
            k in LEVEL_KEYS and (v is None or not isinstance(v, (int, float)))
            for k, v in kl.items()
        ):
            return "bad_key_levels"
        if "swing_points" in kl and not isinstance(kl["swing_points"], list):
            return "bad_key_levels"
        params = p.get("params") or {}
        if not isinstance(params, dict):
            return "bad_params"
        vu = p.get("valid_until")
        if vu is not None:
            try:
                dt = datetime.fromisoformat(vu)
            except ValueError:
                return "bad_valid_until"
            if dt <= now + timedelta(minutes=self.cfg["min_survival_minutes"]):
                return "valid_until_too_soon"
        vb = p.get("valid_bars")
        if vb is not None and (not isinstance(vb, int) or vb <= 0):
            return "bad_valid_bars"
        if p.get("priority") is not None and not isinstance(p["priority"], int):
            return "bad_priority"
        return None

    def _clean(self, p: dict) -> dict:
        base, _, exch = p["symbol"].partition(".")
        from .market import canonical_symbol

        return {
            "symbol": f"{canonical_symbol(base, exch)}.{exch.upper()}",
            "selection_timeframe": p["selection_timeframe"],
            "exec_timeframe": p["exec_timeframe"],
            "context_tag": p.get("context_tag"),
            "signal_categories": p.get("signal_categories", "ALL"),
            "direction": p.get("direction", "both"),
            "key_levels": {
                k: float(v) for k, v in (p.get("key_levels") or {}).items()
                if k in LEVEL_KEYS and v is not None
            },
            "params": p.get("params") or {},
            "priority": p.get("priority", 0),
            "reason_code": p["reason_code"],
            "reason_note": p["reason_note"].strip(),
            "valid_bars": p.get("valid_bars"),
            "valid_until": p.get("valid_until"),
        }

    def _deep_validate(self, cleaned: dict, now: datetime) -> str | None:
        wl = self.cfg["symbol_whitelist"]
        if wl is not None and cleaned["symbol"] not in wl:
            return "symbol_not_in_whitelist"
        ctx_wl = self.cfg["context_whitelist"]
        ctx = cleaned["context_tag"]
        allowed_ctx = set(ctx_wl) if ctx_wl is not None else CONTEXT_TAGS
        if ctx is not None and ctx not in allowed_ctx:
            return "context_not_in_whitelist"
        sel_m = TIMEFRAME_MINUTES[cleaned["selection_timeframe"]]
        exec_m = TIMEFRAME_MINUTES[cleaned["exec_timeframe"]]
        if sel_m > exec_m:
            return "selection_gt_exec"
        valid_bars = cleaned["valid_bars"] or self.cfg["default_valid_bars"]
        if valid_bars * sel_m < 2 * exec_m:
            return "validity_shorter_than_two_exec_bars"
        price = self.last_prices.get(cleaned["symbol"])
        if price and cleaned["key_levels"]:
            band = float(self.cfg["key_level_pct_band"])
            for value in cleaned["key_levels"].values():
                if not (price * (1 - band) <= value <= price * (1 + band)):
                    return "key_levels_out_of_band"
        return None

    def _rate_limited(self, caller_source: str, now: datetime) -> bool:
        min_gap = float(self.cfg["request_min_interval_s"])
        if min_gap <= 0:
            return False
        last = self._last_submit.get(caller_source)
        self._last_submit[caller_source] = now
        return last is not None and (now - last).total_seconds() < min_gap

    def _llm_params_locked(self, caller_source: str, cleaned: dict) -> bool:
        return bool(
            self.cfg["llm_params_locked"]
            and caller_source.startswith("llm:")
            and cleaned["params"]
        )

    def _audit(self, source, iid, rev, event_type, from_st, to_st, ts,
               reason: str | None = None, snapshot: dict | None = None) -> None:
        snap = dict(snapshot or {})
        if reason:
            snap["reason"] = reason
        self.db.insert_instruction_event(
            source, iid, rev, event_type, from_st, to_st, "producer", ts, snapshot=snap
        )

    def approve_instruction(self, source: str, instruction_id: str) -> dict:
        """人工审批：PENDING_APPROVAL -> ACTIVE（spec 8 审批队列）。"""
        with self.lock:
            return self._approval(source, instruction_id, approve=True)

    def reject_instruction(self, source: str, instruction_id: str) -> dict:
        """人工审批：PENDING_APPROVAL -> REVOKED（终态）。"""
        with self.lock:
            return self._approval(source, instruction_id, approve=False)

    def _approval(self, source: str, instruction_id: str, approve: bool) -> dict:
        row = self.db.fetch_instruction(source, instruction_id)
        if row is None:
            return fail("not_found")
        if row["status"] != "PENDING_APPROVAL":
            return fail("not_pending")
        to_status = "ACTIVE" if approve else "REVOKED"
        ts = now_str(self.clock)
        self.db.update_instruction_engine(source, instruction_id, to_status,
                                          "APPROVED" if approve else "REJECTED")
        self.db.insert_instruction_event(
            source, instruction_id, row["producer_revision"], "STATUS_CHANGED",
            "PENDING_APPROVAL", to_status, "admin", ts, snapshot={"approval": approve},
        )
        self.db.commit()
        return {"ok": True, "status": to_status}

    # ================= feed routing =================

    def _clock_for(self, symbol: str) -> MarketClock:
        clock = self.clocks.get(symbol)
        if clock is None:
            clock = MarketClock(symbol)
            self.clocks[symbol] = clock
        return clock

    def _register_timeframes(self, symbol: str, exec_tf: str, sel_tf: str) -> None:
        clock = self._clock_for(symbol)
        clock.register(exec_tf)
        clock.register(sel_tf)

    def on_1m_bar(self, bar: BarData) -> None:
        with self.lock:
            vt_symbol = getattr(bar, "vt_symbol", None) or (
                f"{bar.symbol}.{bar.exchange.value}"
            )
            self.last_prices[vt_symbol] = bar.close_price
            clock = self._clock_for(vt_symbol)
            completed = clock.on_1m(bar)
            if self.data_mode == "akshare_poll":
                for (symbol, _tf), task in self.tasks.items():
                    if symbol == vt_symbol:
                        task.on_price(bar.close_price)
            self._route_completed(vt_symbol, completed)

    def on_tick(self, tick: TickData) -> None:
        with self.lock:
            price = tick.last_price
            if not price or price <= 0:
                return
            self.last_prices[tick.vt_symbol] = price
            vt_symbol = getattr(tick, "vt_symbol", None) or (
                f"{tick.symbol}.{tick.exchange.value}"
            )
            for (symbol, _tf), task in self.tasks.items():
                if symbol == vt_symbol:
                    task.on_price(price)

    def flush_due(self, now: datetime | None = None) -> None:
        with self.lock:
            now = now or self.clock()
            for symbol, clock in self.clocks.items():
                self._route_completed(symbol, clock.flush_due(now))

    def _route_completed(self, symbol: str, completed: dict[str, BarData]) -> None:
        for tf, bar in completed.items():
            task = self.tasks.get((symbol, tf))
            if task is not None:
                task.on_exec_bar(bar)
            self._on_selection_bar(symbol, tf, bar)

    # ================= reconciliation (spec 5.2) =================

    def reconcile(self) -> None:
        with self.lock:
            now = self.clock()
            self._expire_wall(now)
            self._apply_desired(now)
            self._sync_tasks()
            self._data_health(now)
            self.deliver_pending(now)
            self._emit_summary(now)

    def _armed_snapshot(self) -> list[tuple]:
        snapshot: list[tuple] = []
        for (symbol, _tf), task in self.tasks.items():
            for alert in task.alerts.values():
                if alert.lifecycle != "ARMED":
                    continue
                snapshot.append((symbol, alert.direction, alert.signal_id,
                                 round(alert.trigger["level"], 6), alert.alert_id))
        return sorted(snapshot)

    def _expiring_instructions(self) -> list[dict]:
        out: list[dict] = []
        for row in self.db.fetch_by_status(("ACTIVE",)):
            remaining = row["remaining_bars"]
            if remaining is not None and remaining <= self.cfg["expiring_soon_bars"]:
                out.append({"instruction_id": row["instruction_id"],
                            "source": row["source"],
                            "remaining_bars": remaining})
        return sorted(out, key=lambda item: item["instruction_id"])

    def _emit_summary(self, now: datetime) -> None:
        """决策 D1：明细照发；每标的×方向只聚合最高 confidence 的最佳机会。"""
        best: dict[tuple[str, str], dict] = {}
        for (symbol, _tf), task in self.tasks.items():
            for alert in task.alerts.values():
                if alert.lifecycle != "ARMED":
                    continue
                key = (symbol, alert.direction)
                score = self._rule_confidence(task, alert)
                current = best.get(key)
                if current is None or score > current["confidence"]:
                    best[key] = {"symbol": symbol, "direction": alert.direction,
                                 "signal_id": alert.signal_id,
                                 "confidence": score,
                                 "trigger": alert.trigger["level"],
                                 "alert_id": alert.alert_id}
        items = [best[k] for k in sorted(best)]
        expiring = self._expiring_instructions()
        signature = json.dumps({"items": items, "expiring": expiring},
                               ensure_ascii=False, sort_keys=True)
        if signature == self._summary_sig:
            return
        if not items and not expiring and self._summary_sig is None:
            self._summary_sig = signature
            return
        self._summary_sig = signature
        self._summary_seq += 1
        alert_id = f"SUM-{now.strftime('%Y%m%d')}-{self._summary_seq:04d}"
        payload = {
            "event_type": "signal.summary",
            "schema_version": "1.0",
            "event_time": now_str(self.clock),
            "payload": {
                "generated_at": now_str(self.clock),
                "items": items,
                "expiring_instructions": expiring,
            },
        }
        keys = ";".join(sorted(f"{row['source']}|{row['instruction_id']}"
                               for row in self.db.fetch_by_status(("ACTIVE",))))
        self.db.insert_alert_event(alert_id, "signal.summary", None, "SUMMARY",
                                   keys, payload, payload["event_time"])
        self.db.insert_outbox(alert_id, "signal.summary", payload,
                              payload["event_time"])
        self.db.commit()

    def _expire_wall(self, now: datetime) -> None:
        for row in self.db.fetch_by_status(("ACTIVE", "WARMING_UP", "PAUSED")):
            vu = row["valid_until"]
            if not vu:
                continue
            if now > datetime.fromisoformat(vu):
                self._transition_instruction(row, "EXPIRED", now, "VALID_UNTIL_HIT")

    def _apply_desired(self, now: datetime) -> None:
        for row in self.db.fetch_by_status(
            ("ACTIVE", "WARMING_UP", "PAUSED", "PENDING_APPROVAL")
        ):
            if row["desired_status"] == "REVOKED":
                self._transition_instruction(row, "REVOKED", now, "REVOKED")

    def _sync_tasks(self) -> None:
        rows = self.db.fetch_by_status(("ACTIVE", "WARMING_UP", "PAUSED"))
        active_keys: set[tuple[str, str]] = set()
        live_map: dict[tuple[str, str], set] = {}
        for row in rows:
            key = (row["symbol"], row["exec_timeframe"])
            active_keys.add(key)
            live_map.setdefault(key, set()).add((row["source"], row["instruction_id"]))
            self._register_timeframes(row["symbol"], row["exec_timeframe"], row["selection_timeframe"])
            task = self.tasks.get(key)
            if task is None:
                task = MonitoringTask(self, row["symbol"], row["exec_timeframe"],
                                      row["selection_timeframe"])
                self.tasks[key] = task
            sig_key = (row["source"], row["instruction_id"])
            if sig_key not in task.contributions:
                task.add_contribution(self._contribution(row))
            else:
                task.contributions[sig_key].update(self._contribution(row))
            if self._task_sig.get(key) != task.contribution_signature():
                self._task_sig[key] = task.contribution_signature()
                task.reseed_levels()
        for key in list(self.tasks):
            if key not in active_keys:
                task = self.tasks.pop(key)
                self._task_sig.pop(key, None)
                task.cancel_all("instruction_gone")
            else:
                task = self.tasks[key]
                for sig in list(task.contributions):
                    if sig not in live_map.get(key, set()):
                        task.cancel_for_instruction(*sig)
                        task.remove_contribution(*sig)
                if not task.contributions:
                    self.tasks.pop(key)
                    self._task_sig.pop(key, None)

    @staticmethod
    def _contribution(row: dict) -> dict:
        raw_cats = row["signal_categories"]
        try:
            cats = json.loads(raw_cats)
        except (TypeError, ValueError):
            cats = raw_cats
        raw_levels = json.loads(row["key_levels"] or "{}")
        levels: dict[str, float] = {}
        for key, value in raw_levels.items():
            levels[LEVEL_ALIASES.get(key, key)] = value
        return {
            "source": row["source"],
            "instruction_id": row["instruction_id"],
            "direction": row["direction"] or "both",
            "context_tag": row["context_tag"],
            "signal_categories": "ALL" if cats == "ALL" else set(cats),
            "key_levels": levels,
            "reason_code": row["reason_code"],
            "reason_note": row["reason_note"],
            "content_hash": row["content_hash"],
            "status": row["status"],
        }

    def _data_health(self, now: datetime) -> None:
        for (symbol, exec_tf), task in list(self.tasks.items()):
            clock = self.clocks.get(symbol)
            if clock is None or clock.last_seen is None:
                continue
            symbol_base, exchange = symbol.rsplit(".", 1)
            traded_minutes = trading_minutes_between(
                clock.last_seen, now, exchange, symbol_base
            )
            stale = traded_minutes > (
                TIMEFRAME_MINUTES[exec_tf] * self.cfg["freshness_interval_factor"]
            )
            for row in self.db.query(
                "SELECT * FROM timing_instruction WHERE symbol=? AND exec_timeframe=? "
                "AND status IN ('ACTIVE','PAUSED')",
                (symbol, exec_tf),
            ):
                if stale and row["status"] == "ACTIVE":
                    if self.cfg["tick_fallback_on_stale"] and self.tick_fallback_hooks:
                        for fn in self.tick_fallback_hooks:
                            fn(symbol)
                        task.data_mode = "tick_fallback"
                        self.db.update_instruction_engine(
                            row["source"], row["instruction_id"], "PAUSED",
                            "STALE_SWITCHED_TO_TICK_FALLBACK")
                        self.db.insert_instruction_event(
                            row["source"], row["instruction_id"],
                            row["producer_revision"], "STATUS_CHANGED",
                            "ACTIVE", "PAUSED", "engine", now_str(self.clock),
                            snapshot={"reason": "TICK_FALLBACK_ON"})
                        self.db.commit()
                    else:
                        self._transition_instruction(row, "PAUSED", now, "FRESHNESS_GATE")
                        task.cancel_all("data_pause")
                    sig = (row["source"], row["instruction_id"])
                    if task.contributions.get(sig):
                        task.contributions[sig]["status"] = "PAUSED"
                elif not stale and row["status"] == "PAUSED":
                    self._transition_instruction(row, "ACTIVE", now, "DATA_RESUMED")
                    sig = (row["source"], row["instruction_id"])
                    if task.contributions.get(sig):
                        task.contributions[sig]["status"] = "ACTIVE"

    def _transition_instruction(self, row: dict, to_status: str, now: datetime,
                                reason: str) -> None:
        from_status = row["status"]
        feedback = reason
        self.db.update_instruction_engine(
            row["source"], row["instruction_id"], to_status, feedback
        )
        self.db.insert_instruction_event(
            row["source"], row["instruction_id"], row["producer_revision"],
            "STATUS_CHANGED", from_status, to_status, "engine", now_str(self.clock),
            snapshot={"reason": reason},
        )
        self.db.commit()
        task = self.tasks.get((row["symbol"], row["exec_timeframe"]))
        if task is not None and to_status in ("REVOKED", "EXPIRED"):
            task.cancel_for_instruction(row["source"], row["instruction_id"])

    # ================= selection countdown (spec 4.1) =================

    def _on_selection_bar(self, symbol: str, sel_tf: str, sbar: BarData) -> None:
        rows = self.db.query(
            "SELECT * FROM timing_instruction WHERE symbol=? AND selection_timeframe=? "
            "AND status IN ('ACTIVE','WARMING_UP')",
            (symbol, sel_tf),
        )
        now = self.clock()
        for row in rows:
            needs_anchor = row["status"] == "WARMING_UP" or (
                row["status"] == "ACTIVE" and row["remaining_bars"] is None
            )
            if needs_anchor:
                task = self.tasks.get((symbol, row["exec_timeframe"]))
                if task is None or not task.ready:
                    continue
                remaining = row["valid_bars"] or self.cfg["default_valid_bars"]
                sel_m = TIMEFRAME_MINUTES[sel_tf]
                expires_bar = window_open(
                    int((sbar.datetime - datetime(1970, 1, 1)).total_seconds())
                    // (sel_m * 60) + remaining, sel_m
                ).strftime("%Y-%m-%d %H:%M:%S")
                self.db.update_instruction_engine(
                    row["source"], row["instruction_id"], "ACTIVE", "RUNNING",
                    remaining_bars=remaining, effective_from=now_str(self.clock),
                    anchor_bar=sbar.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                    expires_bar=expires_bar,
                )
                self.db.insert_instruction_event(
                    row["source"], row["instruction_id"], row["producer_revision"],
                    "STATUS_CHANGED", "WARMING_UP", "ACTIVE", "engine",
                    now_str(self.clock), snapshot={"reason": "WARMUP_DONE"},
                )
                self.db.commit()
                sig = (row["source"], row["instruction_id"])
                if task.contributions.get(sig):
                    task.contributions[sig]["status"] = "ACTIVE"
                continue
            remaining = (row["remaining_bars"] or 0) - 1
            self.db.set_remaining_bars(row["source"], row["instruction_id"], remaining)
            sel_m = TIMEFRAME_MINUTES[sel_tf]
            est = window_open(
                int((sbar.datetime - datetime(1970, 1, 1)).total_seconds())
                // (sel_m * 60) + remaining, sel_m
            ).strftime("%Y-%m-%d %H:%M:%S")
            self.db.update_instruction_engine(
                row["source"], row["instruction_id"], row["status"],
                row["feedback"] or "RUNNING",
                remaining_bars=remaining, expires_bar=est,
            )
            if remaining <= 0:
                self.db.commit()
                self._transition_instruction(row, "EXPIRED", now, "VALID_BARS_EXHAUSTED")
                continue
            self.db.commit()

    def on_task_ready(self, task: MonitoringTask) -> None:
        for (source, iid), row in task.contributions.items():
            if row["status"] == "ACTIVE":
                db_row = self.db.fetch_instruction(source, iid)
                if db_row and db_row["status"] == "WARMING_UP":
                    self.db.update_instruction_engine(
                        source, iid, "WARMING_UP", "WARMUP_DONE_WAITING_ANCHOR"
                    )
                    self.db.commit()

    # ================= alerts & outbox (spec 3.4 / 7) =================

    def next_alert_id(self) -> str:
        self._alert_seq += 1
        return f"TIM-{self.clock().strftime('%Y%m%d')}-{self._alert_seq:06d}"

    def _rule_confidence(self, task: MonitoringTask, alert: Alert) -> float:
        """规则打分（spec 10.1 前置版）：信号族基准 + K线质量 + 动能整洁度。"""
        from .structures import body_ratio, overlap_mean

        score = CONFIDENCE_BASE.get(alert.family, 0.5)
        bars = task.bars
        if bars and bars[-1].close_price > bars[-1].open_price:
            score += 0.05 if alert.direction == "long" else -0.05
        if bars and body_ratio(bars[-1]) >= 0.7:
            score += 0.10
        if bars and overlap_mean(bars, self.cfg["overlap_window"]) <= 0.5:
            score += 0.10
        return round(min(0.95, max(0.05, score)), 3)

    def emit_alert(self, task: MonitoringTask, alert: Alert,
                   event_type: str, from_lifecycle: str | None) -> None:
        payload = self._alert_payload(task, alert, event_type)
        keys = ";".join(alert.instruction_keys)
        ts = now_str(self.clock)
        self.db.insert_alert_event(
            alert.alert_id, event_type, from_lifecycle, alert.lifecycle, keys, payload, ts
        )
        self.db.insert_outbox(alert.alert_id, event_type, payload, ts)
        self.db.commit()

    def _alert_payload(self, task: MonitoringTask, alert: Alert, event_type: str) -> dict:
        conf = self._rule_confidence(task, alert)
        multi_tf = False
        for (sym, tf), other in self.tasks.items():
            if sym != task.symbol or tf == task.exec_tf:
                continue
            if any(a.lifecycle == "ARMED" and a.direction == alert.direction
                   for a in other.alerts.values()):
                multi_tf = True
                break
        if multi_tf:
            conf = round(min(0.95, conf + 0.10), 3)  # 决策 D2：多周期同向加成
        first = None
        for key in alert.instruction_keys:
            src, iid = key.split("|", 1)
            row = task.contributions.get((src, iid))
            if row is not None:
                first = row
                break
        return {
            "event_type": event_type,
            "schema_version": "1.0",
            "event_time": now_str(self.clock),
            "payload": {
                "event_id": alert.alert_id,
                "instrument": task.symbol,
                "exec_timeframe": task.exec_tf,
                "bar_time": alert.armed_bar_time.strftime("%Y-%m-%d %H:%M:%S"),
                "context_tag": alert.context_tag,
                "signal_family": alert.family,
                "signal_id": alert.signal_id,
                "direction": alert.direction,
                "order_type": alert.order_type,
                "trigger": alert.trigger,
                "stop": alert.stop,
                "targets": alert.targets,
                "invalidation": alert.invalidation,
                "lifecycle": alert.lifecycle,
                "expire_bars_exec": self.cfg["expire_bars_exec"],
                "confidence": conf,
                "multi_tf_confirmed": multi_tf,
                "gap_open": False,
                "data_mode": alert.data_mode,
                "source": (first or {}).get("source", ""),
                "instruction_ids": [k.split("|", 1)[1] for k in alert.instruction_keys],
                "admission_reason": {
                    "code": (first or {}).get("reason_code", ""),
                    "note": (first or {}).get("reason_note", ""),
                },
                "context_snapshot": {
                    "ema20": task.ema.value,
                    "atr14": task.atr.value,
                    "config_version": CONFIG_VERSION,
                },
                "extra": alert.extra,
            },
        }

    def register_delivery_handler(self, fn) -> None:
        self.delivery_handlers.append(fn)

    def deliver_pending(self, now: datetime | None = None) -> None:
        """FIFO per alert_id; stop batch on first failure (spec 5.5)."""
        if not self.delivery_handlers:
            return
        now = now or self.clock()
        for row in self.db.fetch_due_outbox(now):
            payload = json.loads(row["payload_json"])
            try:
                for fn in self.delivery_handlers:
                    fn(payload)
                self.db.mark_outbox_delivered(row["id"], now_str(self.clock))
            except Exception as exc:  # noqa: BLE001 - retry path must catch all
                attempts = row["attempts"] + 1
                if attempts >= self.cfg["outbox_max_attempts"]:
                    self.db.mark_outbox_retry(
                        row["id"], attempts, None, str(exc), failed=True
                    )
                else:
                    backoff = self.cfg["outbox_backoff_base_s"] * (2 ** (attempts - 1))
                    nxt = (now + timedelta(seconds=backoff)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    self.db.mark_outbox_retry(row["id"], attempts, nxt, str(exc))
                self.db.commit()
                return
        self.db.commit()

    # ================= timer =================

    def start(self) -> None:
        if self._running:
            return
        if self.run_mode == "REPLAY":
            raise RuntimeError("REPLAY 模式不运行调度线程：请手动逐根喂入K线")
        self._running = True

        def loop() -> None:
            import time as _time

            while self._running:
                try:
                    self.reconcile()
                except Exception:  # noqa: BLE001 - polling must never die
                    pass
                _time.sleep(self.cfg["poll_interval_s"])

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
